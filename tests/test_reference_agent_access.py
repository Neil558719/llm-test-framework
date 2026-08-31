"""软件权限申请与人工转接流程契约测试。"""

from fastapi.testclient import TestClient

from reference_agent.app import create_app
from reference_agent.graph import build_graph
from reference_agent.services import ApprovalService, FailureConfig, UserService


def _services(approval_failure=None):
    users = UserService(records={"U1001": {"user_id": "U1001", "name": "张三"}})
    approvals = ApprovalService(failure=approval_failure)
    return users, approvals


def _state(message, user_id="U1001", session_id="session-1"):
    return {
        "message": message,
        "answer": "",
        "sources": [],
        "user_id": user_id,
        "session_id": session_id,
        "tool_calls": [],
    }


def test_access_graph_creates_pending_approval_with_tool_calls():
    users, approvals = _services()
    graph = build_graph(user_service=users, approval_service=approvals)

    result = graph.invoke(_state("申请安装 VPN，理由是远程办公"))

    assert result["approval_status"] == "pending"
    assert "A-0001" in result["answer"]
    assert [call.name for call in result["tool_calls"]] == [
        "query_user",
        "create_approval",
    ]
    assert result["tool_calls"][-1].arguments["software"] == "VPN"


def test_access_graph_requests_missing_software_or_justification():
    users, approvals = _services()
    graph = build_graph(user_service=users, approval_service=approvals)

    result = graph.invoke(_state("申请权限"))

    assert result["approval_status"] == "needs_information"
    assert "软件名称" in result["answer"]
    assert [call.name for call in result["tool_calls"]] == ["query_user"]
    assert approvals.get_approval("A-0001") is None


def test_access_graph_requests_justification_when_software_is_present():
    users, approvals = _services()
    graph = build_graph(user_service=users, approval_service=approvals)

    result = graph.invoke(_state("申请安装 VPN"))

    assert result["approval_status"] == "needs_information"
    assert "申请理由" in result["answer"]


def test_access_graph_hands_off_restricted_software_without_creating_approval():
    users, approvals = _services()
    graph = build_graph(user_service=users, approval_service=approvals)

    result = graph.invoke(_state("申请访问 Admin Console，理由是排查生产问题"))

    assert result["approval_status"] == "handoff_required"
    assert "人工" in result["answer"]
    assert result["handoff_reason"] == "restricted_software"
    assert [call.name for call in result["tool_calls"]] == ["query_user"]
    assert approvals.get_approval("A-0001") is None


def test_access_graph_stops_when_user_is_missing():
    users, approvals = _services()
    graph = build_graph(user_service=users, approval_service=approvals)

    result = graph.invoke(_state("申请安装 VPN，理由是远程办公", user_id="missing"))

    assert result["approval_status"] == "user_not_found"
    assert [call.name for call in result["tool_calls"]] == ["query_user"]


def test_chat_api_reuses_access_approval_for_same_session():
    users, approvals = _services()
    client = TestClient(
        create_app(":memory:", user_service=users, approval_service=approvals)
    )
    request = {
        "message": "申请安装 VPN，理由是远程办公",
        "user_id": "U1001",
        "session_id": "session-1",
    }

    first = client.post("/api/chat", json=request).json()
    second = client.post("/api/chat", json=request).json()

    assert first["metadata"]["approval_status"] == "pending"
    assert second["tool_calls"][-1]["result"]["approval_id"] == "A-0001"


def test_chat_api_continues_access_request_after_information_is_added():
    users, approvals = _services()
    client = TestClient(
        create_app(":memory:", user_service=users, approval_service=approvals)
    )

    first = client.post(
        "/api/chat",
        json={"message": "申请安装 VPN", "user_id": "U1001", "session_id": "session-1"},
    ).json()
    second = client.post(
        "/api/chat",
        json={"message": "理由是远程办公", "user_id": "U1001", "session_id": "session-1"},
    ).json()

    assert first["metadata"]["approval_status"] == "needs_information"
    assert second["metadata"]["approval_status"] == "pending"
    assert second["tool_calls"][-1]["result"]["approval_id"] == "A-0001"


def test_chat_api_maps_approval_failure_to_safe_response():
    users, approvals = _services(
        FailureConfig(status_code=503, message="approval service down")
    )
    client = TestClient(
        create_app(":memory:", user_service=users, approval_service=approvals)
    )

    body = client.post(
        "/api/chat",
        json={"message": "申请安装 VPN，理由是远程办公", "user_id": "U1001"},
    ).json()

    assert body["metadata"]["approval_status"] == "unavailable"
    assert "暂时无法提交" in body["answer"]
    assert body["tool_calls"][-1]["status"] == "failed"


def test_chat_api_exposes_handoff_reason_for_restricted_software():
    users, approvals = _services()
    client = TestClient(
        create_app(":memory:", user_service=users, approval_service=approvals)
    )

    body = client.post(
        "/api/chat",
        json={
            "message": "申请访问 Admin Console，理由是排查生产问题",
            "user_id": "U1001",
        },
    ).json()

    assert body["metadata"]["approval_status"] == "handoff_required"
    assert body["metadata"]["handoff_reason"] == "restricted_software"
