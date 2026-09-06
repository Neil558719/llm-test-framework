from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from reference_agent.app import create_app
from reference_agent.faults import FaultControlSettings
from reference_agent.services import (
    ApprovalService,
    AssetService,
    KnowledgeBase,
    TicketService,
    UserService,
)


def _client(tmp_path, settings: FaultControlSettings | None = None) -> TestClient:
    app = create_app(
        str(tmp_path / "m13-agent.db"),
        knowledge_base=KnowledgeBase(
            [
                {
                    "document_id": "KB-VPN-001",
                    "title": "VPN 使用指引",
                    "content": "VPN Client 用于远程办公访问企业资源。",
                }
            ]
        ),
        user_service=UserService(
            {"U1001": {"user_id": "U1001", "name": "Test User"}}
        ),
        asset_service=AssetService(
            {
                "PC-1001": {
                    "asset_id": "PC-1001",
                    "owner_id": "U1001",
                    "status": "active",
                }
            }
        ),
        ticket_service=TicketService(),
        approval_service=ApprovalService(),
        fault_settings=settings or FaultControlSettings(True, "secret"),
    )
    return TestClient(app)


def _headers(fault_type: str, **parameters) -> dict[str, str]:
    return {
        "X-QE-Test-Token": "secret",
        "X-QE-Fault": json.dumps({"type": fault_type, **parameters}),
    }


def _knowledge_body(session_id: str) -> dict[str, str]:
    return {
        "message": "如何使用 VPN？",
        "user_id": "U1001",
        "session_id": session_id,
    }


def _ticket_body(session_id: str) -> dict[str, str]:
    return {
        "message": "VPN 故障，设备编号 PC-1001，请创建工单",
        "user_id": "U1001",
        "session_id": session_id,
    }


def test_chat_response_does_not_echo_the_user_message(tmp_path):
    client = _client(tmp_path)
    body = _knowledge_body("no-message-echo")

    response = client.post("/api/chat", json=body)

    assert response.status_code == 200
    assert response.json()["raw_response"] == {}
    assert body["message"] not in response.text


@pytest.mark.parametrize(
    "fault_type,fallback_reason",
    [("model_timeout", "TimeoutError"), ("model_429", "ModelRateLimitError")],
)
def test_model_fault_falls_back_and_next_request_recovers(
    tmp_path, fault_type, fallback_reason
):
    client = _client(tmp_path)

    injected = client.post(
        "/api/chat",
        headers=_headers(fault_type),
        json=_knowledge_body(f"{fault_type}-fault"),
    )
    recovered = client.post(
        "/api/chat", json=_knowledge_body(f"{fault_type}-recovery")
    )

    assert injected.status_code == 200
    assert injected.json()["metadata"]["fallback_reason"] == fallback_reason
    assert injected.json()["metadata"]["knowledge_status"] == "answered"
    assert recovered.status_code == 200
    assert recovered.json()["metadata"]["knowledge_status"] == "answered"
    assert recovered.json()["metadata"]["fallback_reason"] == "ValueError"


def test_downstream_5xx_returns_stable_business_failure_and_recovers(tmp_path):
    client = _client(tmp_path)

    injected = client.post(
        "/api/chat",
        headers=_headers("downstream_5xx", target="ticket", status_code=500),
        json=_ticket_body("downstream-fault"),
    )
    recovered = client.post("/api/chat", json=_ticket_body("downstream-recovery"))

    assert injected.status_code == 200
    assert injected.json()["metadata"]["ticket_status"] == "unavailable"
    failed_call = injected.json()["tool_calls"][-1]
    assert failed_call["name"] == "create_ticket"
    assert failed_call["status"] == "failed"
    assert "injected downstream_5xx" in failed_call["error"]
    assert recovered.status_code == 200
    assert recovered.json()["metadata"]["ticket_status"] == "created"


def test_tool_slow_response_is_measured_and_does_not_persist(tmp_path):
    client = _client(tmp_path)

    started = time.perf_counter()
    injected = client.post(
        "/api/chat",
        headers=_headers(
            "tool_slow_response", target="asset", delay_seconds=0.05
        ),
        json=_ticket_body("slow-fault"),
    )
    elapsed = time.perf_counter() - started
    recovered = client.post("/api/chat", json=_ticket_body("slow-recovery"))

    assert injected.status_code == 200
    assert injected.json()["metadata"]["ticket_status"] == "created"
    assert elapsed >= 0.045
    assert recovered.status_code == 200
    assert recovered.json()["metadata"]["ticket_status"] == "created"


def test_knowledge_unavailable_has_no_sources_and_recovers(tmp_path):
    client = _client(tmp_path)

    injected = client.post(
        "/api/chat",
        headers=_headers("knowledge_unavailable"),
        json=_knowledge_body("knowledge-fault"),
    )
    recovered = client.post(
        "/api/chat", json=_knowledge_body("knowledge-recovery")
    )

    assert injected.status_code == 200
    assert injected.json()["metadata"]["knowledge_status"] == "unavailable"
    assert injected.json()["sources"] == []
    assert recovered.status_code == 200
    assert recovered.json()["metadata"]["knowledge_status"] == "answered"
    assert recovered.json()["sources"] == ["KB-VPN-001"]


def test_sse_interruption_ends_before_complete_and_next_stream_recovers(tmp_path):
    client = _client(tmp_path)

    injected = client.post(
        "/api/chat/stream",
        headers=_headers("sse_interruption"),
        json=_knowledge_body("sse-fault"),
    )
    recovered = client.post(
        "/api/chat/stream", json=_knowledge_body("sse-recovery")
    )

    injected_events = [
        json.loads(line.removeprefix("data: "))
        for line in injected.text.splitlines()
        if line.startswith("data: ")
    ]
    recovered_events = [
        json.loads(line.removeprefix("data: "))
        for line in recovered.text.splitlines()
        if line.startswith("data: ")
    ]
    assert injected.status_code == 200
    assert [event["type"] for event in injected_events] == ["start"]
    assert recovered.status_code == 200
    assert recovered_events[-1]["type"] == "complete"


def test_database_error_returns_503_without_session_pollution_and_recovers(tmp_path):
    client = _client(tmp_path)

    injected = client.post(
        "/api/chat",
        headers=_headers("database_error"),
        json=_knowledge_body("database-fault"),
    )
    missing = client.get("/api/sessions/database-fault")
    recovered = client.post(
        "/api/chat", json=_knowledge_body("database-recovery")
    )
    stored = client.get("/api/sessions/database-recovery")

    assert injected.status_code == 503
    assert missing.status_code == 404
    assert recovered.status_code == 200
    assert stored.status_code == 200
    assert stored.json()["user_id"] == "U1001"


@pytest.mark.parametrize(
    "settings,headers,expected_status",
    [
        (
            FaultControlSettings(False, ""),
            _headers("model_timeout"),
            403,
        ),
        (
            FaultControlSettings(True, "secret"),
            {
                "X-QE-Test-Token": "wrong",
                "X-QE-Fault": '{"type":"model_timeout"}',
            },
            403,
        ),
        (
            FaultControlSettings(True, "secret"),
            {"X-QE-Test-Token": "secret", "X-QE-Fault": "{"},
            400,
        ),
    ],
)
def test_chat_endpoint_maps_fault_control_errors_before_writing_session(
    tmp_path, settings, headers, expected_status
):
    client = _client(tmp_path, settings)

    response = client.post(
        "/api/chat", headers=headers, json=_knowledge_body("rejected-fault")
    )

    assert response.status_code == expected_status
    assert client.get("/api/sessions/rejected-fault").status_code == 404


def test_concurrent_fault_and_normal_requests_remain_isolated(tmp_path):
    client = _client(tmp_path)

    def send(index: int) -> tuple[bool, str]:
        injected = index % 2 == 0
        response = client.post(
            "/api/chat",
            headers=_headers("knowledge_unavailable") if injected else {},
            json=_knowledge_body(f"isolated-{index}"),
        )
        return injected, response.json()["metadata"]["knowledge_status"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(send, range(40)))

    assert all(status == ("unavailable" if injected else "answered") for injected, status in results)
