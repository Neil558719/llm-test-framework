"""Regression coverage for Issue #41 using real SQLite connections."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import sqlite3

import pytest
from fastapi.testclient import TestClient

from reference_agent.app import create_app
from reference_agent.storage import SQLiteStore


@pytest.mark.parametrize("persistent", [False, True], ids=["memory", "file"])
def test_concurrent_session_writes_are_committed_and_readable(tmp_path, persistent):
    database = str(tmp_path / "sessions.db") if persistent else ":memory:"
    store = SQLiteStore(database)
    start = Barrier(8)

    def worker(worker_id):
        start.wait(timeout=10)
        for index in range(100):
            session_id = f"session-{worker_id}-{index}"
            user_id = f"user-{worker_id}"
            store.upsert_session(session_id, "initial-user")
            store.upsert_session(session_id, user_id)
            assert store.get_session(session_id) == {
                "session_id": session_id, "user_id": user_id,
            }

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(worker, range(8)))
        for worker_id in range(8):
            for index in range(100):
                session_id = f"session-{worker_id}-{index}"
                assert store.get_session(session_id) == {
                    "session_id": session_id, "user_id": f"user-{worker_id}",
                }
    finally:
        store.close()

    if persistent:
        reopened = SQLiteStore(database)
        try:
            assert reopened.get_session("session-7-99") == {
                "session_id": "session-7-99", "user_id": "user-7",
            }
        finally:
            reopened.close()


def test_failed_session_write_is_rolled_back_before_next_request():
    store = SQLiteStore(":memory:")
    try:
        # A real SQLite trigger fails after the row was written. RAISE(FAIL)
        # leaves that row in the transaction unless the store rolls it back.
        store._connection.execute(
            "CREATE TRIGGER reject_session AFTER INSERT ON sessions "
            "WHEN NEW.session_id = 'rejected' BEGIN "
            "SELECT RAISE(FAIL, 'injected write failure'); END"
        )
        with pytest.raises(sqlite3.IntegrityError, match="injected write failure"):
            store.upsert_session("rejected", "U1001")
        store.upsert_session("accepted", "U1002")
        assert store.get_session("rejected") is None
        assert store.get_session("accepted") == {
            "session_id": "accepted", "user_id": "U1002",
        }
    finally:
        store.close()


@pytest.mark.parametrize("endpoint", ["/api/chat", "/api/chat/stream"])
def test_concurrent_chat_requests_preserve_sessions(tmp_path, endpoint, monkeypatch):
    monkeypatch.setenv("REFERENCE_AGENT_MODEL_MODE", "mock")
    app = create_app(str(tmp_path / "api.db"))
    start = Barrier(4)

    def worker(worker_id):
        with TestClient(app, raise_server_exceptions=False) as client:
            start.wait(timeout=10)
            for index in range(20):
                session_id = f"api-{worker_id}-{index}"
                response = client.post(endpoint, json={
                    "message": "你好", "user_id": "U1001", "session_id": session_id,
                })
                assert response.status_code == 200, response.text
                if endpoint.endswith("/stream"):
                    import json
                    events = [json.loads(line[5:]) for line in response.text.splitlines()
                              if line.startswith("data:")]
                    completions = [event for event in events if event["type"] == "complete"]
                    assert len(completions) == 1
                    body = completions[0]["response"]
                else:
                    body = response.json()
                assert body["conversation_id"] == session_id
                assert body["trace_id"]
                stored = client.get(f"/api/sessions/{session_id}")
                assert stored.status_code == 200
                assert stored.json() == {"session_id": session_id, "user_id": "U1001"}

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(worker, range(4)))
    finally:
        app.state.store.close()
