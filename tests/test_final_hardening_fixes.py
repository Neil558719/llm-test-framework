from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from qe_platform.auth.dependencies import AuthRuntime
from qe_platform.auth.session import SessionStore
from qe_platform.ops import backup_database, restore_database, readiness
from reference_agent.app import create_app
from reference_agent.services import UserService
from reference_agent.storage import SQLiteStore


def production_app(tmp_path):
    sessions = SessionStore(tmp_path / "auth.db")
    runtime = AuthRuntime(session_store=sessions, verifier=None, environment="production")
    app = create_app(str(tmp_path / "agent.db"), auth_runtime=runtime,
                     user_service=UserService({"U1001": {"user_id": "U1001", "name": "User"}}))
    return app, sessions


@pytest.mark.parametrize("route", ["/api/chat", "/api/chat/stream"])
def test_production_chat_requires_identity_csrf_and_binds_session_owner(tmp_path, route):
    app, sessions = production_app(tmp_path)
    client = TestClient(app)
    payload = {"message": "VPN", "user_id": "victim", "session_id": "owned-session"}
    assert client.post("/api/login", json={"user_id": "victim"}).status_code == 403
    assert client.post(route, json=payload).status_code == 401
    session = sessions.create("U1001", {"viewer"}, csrf_token="safe-test-csrf")
    client.cookies.set("qe_session", session.session_id)
    assert client.post(route, json=payload).status_code == 403
    assert client.post(route, json=payload, headers={"X-CSRF-Token": "safe-test-csrf"}).status_code == 200
    assert app.state.store.get_session("owned-session")["user_id"] == "U1001"
    other = sessions.create("other", {"viewer"}, csrf_token="safe-test-csrf")
    client.cookies.set("qe_session", other.session_id)
    assert client.post(route, json=payload, headers={"X-CSRF-Token": "safe-test-csrf"}).status_code == 403
    assert client.get("/api/sessions/owned-session").status_code == 403


def test_file_only_model_key_is_used_by_authenticated_update(tmp_path, monkeypatch):
    secret = tmp_path / "model-key"
    secret.write_text("ephemeral-model-fixture", encoding="utf-8")
    monkeypatch.delenv("REFERENCE_AGENT_MODEL_API_KEY", raising=False)
    monkeypatch.setenv("REFERENCE_AGENT_MODEL_API_KEY_FILE", str(secret))
    app, sessions = production_app(tmp_path)
    client = TestClient(app)
    session = sessions.create("admin", {"admin"}, csrf_token="csrf")
    client.cookies.set("qe_session", session.session_id)
    response = client.put("/api/model-profile", json={"profile": "deepseek-official"}, headers={"X-CSRF-Token": "csrf"})
    assert response.status_code == 200
    assert app.state.model_config.api_key == "ephemeral-model-fixture"
    assert "ephemeral-model-fixture" not in response.text


def test_approval_retains_result_without_raw_justification_in_any_artifact(tmp_path):
    source = tmp_path / "agent.db"
    store = SQLiteStore(source)
    sentinel = "sensitive-approval-sentinel-do-not-retain"
    approval = store.create_approval("U1001", "VPN", sentinel, "request-1")
    assert approval["status"] == "pending"
    backup = tmp_path / "backup.db"
    backup_database(source, backup)
    report = json.dumps(approval).encode()
    assert sentinel.encode() not in report
    for path in tmp_path.iterdir():
        if path.is_file():
            assert sentinel.encode() not in path.read_bytes(), path.name
    store.close()
    reopened = SQLiteStore(source)
    assert reopened.create_approval("U1001", "VPN", "other", "request-1") == approval
    reopened.close()


@pytest.mark.parametrize("first,second", [
    ("申请权限，理由是 sensitive-draft-sentinel", "VPN"),
    ("申请安装 VPN", "理由是 sensitive-draft-sentinel"),
])
def test_access_draft_preserves_safe_slots_over_restart(tmp_path, first, second):
    path = tmp_path / "agent.db"
    users = UserService({"U1001": {"user_id": "U1001", "name": "User"}})
    app = create_app(str(path), user_service=users)
    payload = {"user_id": "U1001", "session_id": "draft", "message": first}
    assert TestClient(app).post("/api/chat", json=payload).json()["metadata"]["approval_status"] == "needs_information"
    app.state.store.close()
    app = create_app(str(path), user_service=users)
    payload["message"] = "请继续"
    assert TestClient(app).post("/api/chat", json=payload).json()["metadata"]["approval_status"] == "needs_information"
    app.state.store.close()
    app = create_app(str(path), user_service=users)
    payload["message"] = second
    assert TestClient(app).post("/api/chat", json=payload).json()["metadata"]["approval_status"] == "pending"
    for artifact in tmp_path.iterdir():
        assert b"sensitive-draft-sentinel" not in artifact.read_bytes()
    app.state.store.close()


@pytest.mark.parametrize("damage", ["DROP TABLE tickets", "UPDATE schema_meta SET version=999", "PRAGMA query_only=ON"])
def test_readiness_rejects_missing_schema_new_schema_and_unwritable_repository(tmp_path, damage):
    app = create_app(str(tmp_path / "agent.db"))
    app.state.store._connection.execute(damage)
    assert TestClient(app).get("/api/health/ready").status_code == 503
    assert TestClient(app).get("/api/health/live").status_code == 200


def test_auth_store_participates_in_migrations_backup_restore_and_readiness(tmp_path):
    path = tmp_path / "auth.db"
    sessions = SessionStore(path)
    session = sessions.create("user", {"viewer"}, csrf_token="csrf")
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("SELECT version FROM schema_meta WHERE component='auth'").fetchone()[0] >= 1
    with sessions._connect() as configured:
        assert configured.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert configured.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    backup = tmp_path / "backup.db"
    result = backup_database(path, backup)
    assert "auth" in result.schema_versions
    restored = tmp_path / "restored.db"
    restore_database(backup, restored, result.schema_versions)
    assert SessionStore(restored).get(session.session_id).subject == "user"
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE schema_meta SET version=999 WHERE component='auth'")
    assert readiness({"auth": sessions}).ready is False
    with pytest.raises(RuntimeError, match="newer"):
        SessionStore(path)


def test_reference_readiness_requires_configured_auth_database_and_idp(tmp_path):
    app, sessions = production_app(tmp_path)
    assert TestClient(app).get("/api/health/ready").status_code == 503


def test_auth_session_endpoint_reports_mode_identity_and_logout(tmp_path):
    app, sessions = production_app(tmp_path)
    client = TestClient(app)
    assert client.get("/auth/session").json() == {"environment": "production", "authenticated": False}
    session = sessions.create("U1001", {"viewer"}, csrf_token="csrf")
    client.cookies.set("qe_session", session.session_id)
    data = client.get("/auth/session").json()
    assert data["subject"] == "U1001"
    assert data["csrf_cookie_name"] == "qe_session_csrf"
    assert client.post("/auth/logout", headers={"X-CSRF-Token": "csrf"}).status_code == 204
    assert client.get("/auth/session").json()["authenticated"] is False


def test_http_metrics_observe_auth_failure_and_reference_operation_without_labels(tmp_path):
    app, sessions = production_app(tmp_path)
    client = TestClient(app)
    client.post("/api/chat", json={"message": "never-label-this-prompt"})
    session = sessions.create("admin", {"admin"}, csrf_token="csrf")
    client.cookies.set("qe_session", session.session_id)
    client.post("/api/chat", json={"message": "VPN"}, headers={"X-CSRF-Token": "csrf"})
    data = client.get("/api/metrics").json()
    assert data["counters"]["auth_failures_total"] > 0
    assert data["counters"]["reference_requests_total"] > 0
    assert data["latencies"]["reference_request_latency_ms"]["count"] > 0
    assert "never-label-this-prompt" not in json.dumps(data)


def test_ops_migration_quality_and_database_failures_emit_bounded_metrics(tmp_path):
    from qe_platform.ops import metrics
    from qe_platform.storage import Migration, MigrationRunner
    from qe_platform.quality_loop.engine import validate_release
    from qe_platform.quality_loop.storage import SQLiteQualityRepository
    from qe_platform.quality_loop.models import ReleaseGatePolicy
    registry = getattr(metrics, "PROCESS_METRICS", None)
    assert registry is not None
    before = registry.snapshot()["counters"]
    store = SQLiteStore(tmp_path / "agent.db")
    backup_database(tmp_path / "agent.db", tmp_path / "backup.db")
    restore_database(tmp_path / "backup.db", tmp_path / "restored.db", {"reference_agent": 2})
    conn = sqlite3.connect(":memory:")
    def broken(connection):
        connection.execute("INSERT INTO missing_table VALUES(1)")
    with pytest.raises(sqlite3.Error):
        MigrationRunner(conn, "test", [Migration(1, broken)]).apply()
    quality = SQLiteQualityRepository(tmp_path / "quality.db")
    with pytest.raises(KeyError):
        validate_release(quality, "missing", "missing", ReleaseGatePolicy())
    store._connection.execute("PRAGMA query_only=ON")
    with pytest.raises(sqlite3.Error):
        store.upsert_session("s", "u")
    after = registry.snapshot()
    for name in ("backup_total", "restore_total", "migration_failures_total", "quality_gate_failures_total", "database_failures_total"):
        assert after["counters"][name] > before.get(name, 0)
    for name in ("backup_latency_ms", "restore_latency_ms", "migration_latency_ms", "quality_gate_latency_ms"):
        assert after["latencies"][name]["count"] > 0
    store.close()
    quality.close()
    conn.close()


def test_chat_approval_observations_do_not_export_raw_justification(tmp_path):
    app = create_app(str(tmp_path / "agent.db"), user_service=UserService({"U1001": {"user_id": "U1001"}}))
    response = TestClient(app).post("/api/chat", json={"user_id": "U1001", "message": "申请安装 VPN，理由是 private-observation-sentinel"})
    assert response.json()["metadata"]["approval_status"] == "pending"
    assert "private-observation-sentinel" not in response.text
    app.state.store.close()


def test_production_readiness_rejects_incomplete_model_configuration(tmp_path):
    from reference_agent.runtime.config import AgentModelConfig
    from tests.test_production_hardening_contract import _production_runtime
    runtime, _ = _production_runtime(tmp_path)
    app = create_app(str(tmp_path / "agent.db"), auth_runtime=runtime)
    assert TestClient(app).get("/api/health/ready").status_code == 200
    app.state.model_config = AgentModelConfig(mode="real", provider="openai")
    assert TestClient(app).get("/api/health/ready").status_code == 503
    app.state.store.close()


def test_existing_approval_content_is_scrubbed_by_versioned_migration(tmp_path):
    from qe_platform.storage import MigrationRunner
    from reference_agent.storage import _MIGRATIONS
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    MigrationRunner(conn, "reference_agent", [_MIGRATIONS[0]]).apply()
    conn.execute("INSERT INTO approvals VALUES ('A-0001','U1001','VPN','legacy-sensitive-approval','pending','a')")
    conn.commit()
    conn.close()
    migrated = SQLiteStore(path)
    assert migrated.get_approval("A-0001")["justification"] == "provided"
    backup_database(path, tmp_path / "backup.db")
    for artifact in tmp_path.iterdir():
        assert b"legacy-sensitive-approval" not in artifact.read_bytes()
    migrated.close()


def test_quality_gate_denial_is_counted_as_an_outcome(tmp_path):
    from qe_platform.ops.metrics import PROCESS_METRICS
    from qe_platform.quality_loop.engine import validate_release
    from qe_platform.quality_loop.models import ReleaseGatePolicy
    from tests.test_quality_loop_engine import _setup_database
    from tests.test_telemetry_storage import utc
    quality, baseline, candidate = _setup_database(tmp_path)
    before = PROCESS_METRICS.snapshot()["counters"].get("quality_gate_denied_total", 0)
    result = validate_release(quality, baseline.run_id, candidate.run_id, ReleaseGatePolicy(application="different"), now=utc("2026-09-01T00:00:00+00:00"))
    assert result.passed is False
    assert PROCESS_METRICS.snapshot()["counters"].get("quality_gate_denied_total", 0) == before + 1
    quality.close()


def test_concurrent_principals_cannot_claim_the_same_new_business_session(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    app, sessions = production_app(tmp_path)
    barrier = Barrier(2)
    original_get = app.state.store.get_session
    def simultaneous_reads(session_id):
        result = original_get(session_id)
        barrier.wait(timeout=5)
        return result
    monkeypatch.setattr(app.state.store, "get_session", simultaneous_reads)
    clients = []
    for subject in ("U1001", "another-user"):
        session = sessions.create(subject, {"viewer"}, csrf_token="csrf")
        client = TestClient(app)
        client.cookies.set("qe_session", session.session_id)
        clients.append(client)
    def chat(client):
        return client.post("/api/chat", json={"session_id": "contested", "message": "VPN"}, headers={"X-CSRF-Token": "csrf"}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(chat, clients))
    assert sorted(statuses) == [200, 403]
    app.state.store.close()


@pytest.mark.parametrize("dependency", ["auth_database", "identity_provider"])
def test_ready_fails_for_a_lost_configured_auth_dependency(tmp_path, dependency, monkeypatch):
    from tests.test_production_hardening_contract import _production_runtime
    from qe_platform.telemetry.api import create_telemetry_app
    from qe_platform.telemetry.settings import TelemetrySettings
    runtime, _ = _production_runtime(tmp_path)
    agent = create_app(str(tmp_path / "agent.db"), auth_runtime=runtime)
    telemetry = create_telemetry_app(TelemetrySettings(str(tmp_path / "telemetry.db"), "hash", "ingest"), auth_runtime=runtime)
    assert TestClient(agent).get("/api/health/ready").status_code == 200
    assert TestClient(telemetry).get("/api/health/ready").status_code == 200
    if dependency == "auth_database":
        with sqlite3.connect(tmp_path / "auth.db") as connection:
            connection.execute("DROP TABLE auth_sessions")
    else:
        def unavailable():
            raise RuntimeError("private-idp-failure-detail")
        monkeypatch.setattr(runtime.metadata_client, "get_jwks", unavailable)
    for app in (agent, telemetry):
        response = TestClient(app).get("/api/health/ready")
        assert response.status_code == 503
        assert response.json()["checks"][dependency] == "unavailable"
        assert "private-idp-failure-detail" not in response.text
    agent.state.store.close()
