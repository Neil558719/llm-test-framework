from __future__ import annotations

import json

from fastapi.testclient import TestClient

from qe_platform.telemetry.sink import TelemetrySink
from qe_platform.telemetry.sink import HttpTelemetrySink
from qe_platform.telemetry import build_trace_event
from reference_agent.app import create_app
from reference_agent.services import AssetService, TicketService, UserService


class RecordingTelemetrySink(TelemetrySink):
    def __init__(self) -> None:
        self.hash_key = "recording-hash-key"
        self.events = []

    def emit(self, event) -> None:
        self.events.append(event)


class FailingTelemetrySink(TelemetrySink):
    hash_key = "failing-hash-key"

    def emit(self, event) -> None:
        raise RuntimeError("sink unavailable with secret should stay internal")


def test_http_sink_returns_without_waiting_for_slow_network(monkeypatch):
    import time

    def slow_send(*args, **kwargs):
        time.sleep(0.4)

    monkeypatch.setattr("urllib.request.urlopen", slow_send)
    event = build_trace_event(
        "trace-slow", "reference-agent", "user", "session", "request", "answer", "hash",
        tool_calls=[], metadata={"environment": "test"}, usage={}, cost=None,
        model_version={}, latency={"status": "succeeded"},
    )
    sink = HttpTelemetrySink("http://telemetry.local/api/traces", "token", "hash", timeout=1)
    started = time.monotonic()
    sink.emit(event)
    assert time.monotonic() - started < 0.2


def test_chat_emits_one_sanitized_trace_event_after_response_envelope_exists():
    sink = RecordingTelemetrySink()
    client = TestClient(
        create_app(
            ":memory:",
            user_service=UserService({"U1001": {"user_id": "U1001", "name": "Private User"}}),
            asset_service=AssetService({"PC-1001": {"asset_id": "PC-1001", "owner_id": "U1001", "status": "active"}}),
            ticket_service=TicketService(),
            telemetry_sink=sink,
        )
    )
    request_text = "我的 VPN 故障影响财务系统，设备 PC-1001，私人备注 secret-payroll-42，请创建工单"

    response = client.post(
        "/api/chat",
        json={"message": request_text, "user_id": "U1001", "session_id": "telemetry-session-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(sink.events) == 1
    event = sink.events[0].as_dict()
    assert event["trace_id"] == body["trace_id"]
    assert event["usage"] == body["usage"]
    assert event["cost"] == body["cost"]
    assert event["model_version"]
    assert event["tool_calls"] == [
        {"name": "query_user", "status": "succeeded"},
        {"name": "query_asset", "status": "succeeded"},
        {"name": "create_ticket", "status": "succeeded"},
    ]
    serialized = json.dumps(event, ensure_ascii=False)
    assert request_text not in serialized
    assert body["answer"] not in serialized
    assert "PC-1001" not in serialized
    assert "secret-payroll-42" not in serialized
    assert "arguments" not in serialized
    assert "result" not in serialized


def test_sink_exception_does_not_change_chat_status_or_response_body():
    client = TestClient(create_app(":memory:", telemetry_sink=FailingTelemetrySink()))

    response = client.post(
        "/api/chat",
        json={"message": "你好", "user_id": "U1001", "session_id": "telemetry-session-2"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == "telemetry-session-2"
    assert body["trace_id"]
    assert body["answer"]
