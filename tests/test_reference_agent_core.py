"""参考 IT 服务台 Agent 骨架的最小行为契约。"""

from fastapi.testclient import TestClient

from reference_agent.app import create_app
from reference_agent.storage import SQLiteStore


def test_health_endpoint_reports_reference_agent_ready():
    client = TestClient(create_app(":memory:"))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "reference-agent"}


def test_sqlite_store_round_trips_session_metadata():
    store = SQLiteStore(":memory:")

    store.upsert_session("session-1", "U1001")

    assert store.get_session("session-1") == {
        "session_id": "session-1",
        "user_id": "U1001",
    }


def test_chat_skeleton_returns_compatible_envelope_fields():
    client = TestClient(create_app(":memory:"))

    response = client.post(
        "/api/chat",
        json={"message": "你好", "user_id": "U1001", "session_id": "session-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"]
    assert body["conversation_id"] == "session-1"
    assert body["trace_id"]
    assert body["tool_calls"] == []
    assert body["sources"] == []
