from __future__ import annotations

import json

from fastapi.testclient import TestClient

from reference_agent.deployment import create_deployment_app


def test_demo_login_creates_session_and_session_endpoint_returns_it():
    client = TestClient(create_deployment_app())

    login = client.post("/api/login", json={"user_id": "U1001"})

    assert login.status_code == 200
    body = login.json()
    assert body["user_id"] == "U1001"
    assert body["session_id"]
    session = client.get(f"/api/sessions/{body['session_id']}")
    assert session.status_code == 200
    assert session.json() == {"session_id": body["session_id"], "user_id": "U1001"}


def test_chat_stream_emits_sse_completion_with_response_envelope():
    client = TestClient(create_deployment_app())

    response = client.post(
        "/api/chat/stream",
        json={"message": "如何使用 VPN？", "user_id": "U1001", "session_id": "stream-1"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(line.removeprefix("data: ")) for line in response.text.splitlines() if line.startswith("data: ")]
    assert events[0]["type"] == "start"
    assert events[-1]["type"] == "complete"
    assert events[-1]["response"]["conversation_id"] == "stream-1"
    assert events[-1]["response"]["trace_id"]
    assert events[-1]["response"]["answer"]


def test_chat_stream_returns_stable_error_event_for_unavailable_knowledge_base():
    from reference_agent.services import FailureConfig, KnowledgeBase
    from reference_agent.app import create_app

    client = TestClient(create_app(":memory:", knowledge_base=KnowledgeBase([], FailureConfig(status_code=503, message="down"))))

    response = client.post("/api/chat/stream", json={"message": "VPN 帮助", "user_id": "U1001"})

    assert response.status_code == 200
    events = [json.loads(line.removeprefix("data: ")) for line in response.text.splitlines() if line.startswith("data: ")]
    assert events[-1]["type"] == "complete"
    assert events[-1]["response"]["metadata"]["knowledge_status"] == "unavailable"

