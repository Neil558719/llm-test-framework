from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from qe_platform.feedback import FeedbackKind
from qe_platform.telemetry import build_trace_event
from qe_platform.telemetry.api import create_telemetry_app
from qe_platform.telemetry.settings import TelemetrySettings


HASH_KEY = "test-key"
INGEST_TOKEN = "ingest-token"


def safe_payload(trace_id: str = "trace-1", application: str = "service-desk") -> dict:
    trace = build_trace_event(
        trace_id,
        application,
        "private-user",
        "private-session",
        "private request",
        "private answer",
        HASH_KEY,
        tool_calls=[{"name": "create_ticket", "status": "succeeded", "arguments": {"secret": "x"}}],
        metadata={"environment": "test"},
        usage={"prompt_tokens": 3, "completion_tokens": 5},
        cost={"input": 0.01, "output": 0.02, "total": 0.03, "currency": "USD", "price_version": "p1"},
        model_version={"model": "mock-v1", "prompt": "prompt-v1"},
        latency={"total_ms": 12.5, "status": "succeeded"},
    )
    payload = trace.as_dict()
    payload["timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return payload


def client_for(tmp_path, *, repository=None) -> TestClient:
    settings = TelemetrySettings(str(tmp_path / "telemetry.db"), HASH_KEY, INGEST_TOKEN, 30)
    return TestClient(create_telemetry_app(settings, repository=repository))


def test_ingest_requires_token_and_get_never_returns_forbidden_fields(tmp_path):
    client = client_for(tmp_path)

    missing = client.post("/api/traces", json=safe_payload())
    assert missing.status_code == 401
    assert INGEST_TOKEN not in missing.text
    invalid = client.post(
        "/api/traces",
        headers={"X-QE-Telemetry-Token": "wrong-token"},
        json=safe_payload(),
    )
    assert invalid.status_code == 401
    assert "wrong-token" not in invalid.text

    created = client.post(
        "/api/traces",
        headers={"X-QE-Telemetry-Token": INGEST_TOKEN},
        json=safe_payload(),
    )
    assert created.status_code == 201

    stored = client.get("/api/traces/trace-1")
    assert stored.status_code == 200
    stored_text = json.dumps(stored.json())
    assert "answer" not in stored.json()
    assert "private answer" not in stored_text
    assert "arguments" not in stored_text


def test_trace_filters_bounds_and_malformed_payloads_are_safe(tmp_path):
    client = client_for(tmp_path)
    headers = {"X-QE-Telemetry-Token": INGEST_TOKEN}
    assert client.post("/api/traces", headers=headers, json=safe_payload("trace-1", "service-desk")).status_code == 201
    assert client.post("/api/traces", headers=headers, json=safe_payload("trace-2", "other-app")).status_code == 201

    listed = client.get("/api/traces", params={"application": "service-desk", "limit": 1})
    assert listed.status_code == 200
    assert [item["trace_id"] for item in listed.json()["traces"]] == ["trace-1"]

    assert client.get("/api/traces", params={"application": "service-desk", "limit": 101}).status_code == 400
    assert client.get("/api/traces", params={"application": "service-desk", "limit": "many"}).status_code == 400
    forbidden = safe_payload("trace-3")
    forbidden["metadata"] = {"authorization": "Bearer secret"}
    response = client.post("/api/traces", headers=headers, json=forbidden)
    assert response.status_code == 400
    assert "secret" not in response.text

    value_leak = safe_payload("trace-value-leak")
    value_leak["metadata"] = {"environment": "Bearer secret-token private request"}
    assert client.post("/api/traces", headers=headers, json=value_leak).status_code == 400


def test_feedback_accepts_only_declared_categories_and_safe_fields(tmp_path):
    client = client_for(tmp_path)
    headers = {"X-QE-Telemetry-Token": INGEST_TOKEN}
    assert client.post("/api/traces", headers=headers, json=safe_payload()).status_code == 201

    for category in FeedbackKind:
        created = client.post(
            "/api/traces/trace-1/feedback",
            json={"category": category.value, "reporter_id": "U1001", "source": "ui"},
        )
        assert created.status_code == 201
        assert created.json()["category"] == category.value
        assert "U1001" not in json.dumps(created.json())

    assert client.post("/api/traces/missing/feedback", json={"category": "correct", "reporter_id": "U1001", "source": "ui"}).status_code == 404
    assert client.post("/api/traces/trace-1/feedback", json={"category": "praise", "reporter_id": "U1001", "source": "ui"}).status_code == 400
    assert client.post("/api/traces/trace-1/feedback", json={"category": "correct", "reporter_id": "U1001", "source": "ui", "comment": "free text"}).status_code == 400
    assert client.post("/api/traces/trace-1/feedback", json={"category": "correct", "reporter_id": {"raw": "U1001"}, "source": "ui"}).status_code == 400

    listed = client.get("/api/feedback", params={"trace_id": "trace-1", "category": "inaccurate", "limit": 1})
    assert listed.status_code == 200
    assert listed.json()["feedback"][0]["category"] == "inaccurate"
    assert "free text" not in json.dumps(listed.json())


class BrokenRepository:
    def upsert_trace(self, trace):
        raise RuntimeError("database secret broke")

    def get_trace(self, trace_id, *, now=None):
        raise RuntimeError("database secret broke")

    def list_traces(self, query, *, now=None):
        raise RuntimeError("database secret broke")

    def add_feedback(self, value, trace_id):
        raise RuntimeError("database secret broke")

    def list_feedback(self, query, *, now=None):
        raise RuntimeError("database secret broke")

    def prune_expired(self, *, now):
        raise RuntimeError("database secret broke")


def test_unexpected_repository_errors_return_payload_free_500(tmp_path):
    client = client_for(tmp_path, repository=BrokenRepository())

    response = client.post(
        "/api/traces",
        headers={"X-QE-Telemetry-Token": INGEST_TOKEN},
        json=safe_payload(),
    )

    assert response.status_code == 500
    assert response.content == b""
    assert INGEST_TOKEN not in response.text
    assert "database secret" not in response.text
