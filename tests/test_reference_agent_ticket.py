"""故障工单流程契约测试。"""

from fastapi.testclient import TestClient

from reference_agent.app import create_app
from reference_agent.graph import build_graph
from reference_agent.services import (
    AssetService,
    FailureConfig,
    TicketService,
    UserService,
)


def _services(ticket_failure: FailureConfig | None = None):
    users = UserService(
        records={"U1001": {"user_id": "U1001", "name": "张三"}}
    )
    assets = AssetService(
        records={
            "PC-1001": {
                "asset_id": "PC-1001",
                "owner_id": "U1001",
                "status": "active",
            }
        }
    )
    tickets = TicketService(failure=ticket_failure)
    return users, assets, tickets


def _ticket_state(user_id: str = "U1001", session_id: str = "session-1"):
    return {
        "message": "VPN 无法连接，设备 PC-1001，请创建工单，优先级高",
        "answer": "",
        "sources": [],
        "user_id": user_id,
        "session_id": session_id,
        "tool_calls": [],
    }


def test_ticket_graph_validates_user_asset_and_creates_ticket_in_order():
    users, assets, tickets = _services()
    graph = build_graph(user_service=users, asset_service=assets, ticket_service=tickets)

    result = graph.invoke(_ticket_state())

    assert result["ticket_status"] == "created"
    assert "T-0001" in result["answer"]
    assert [call.name for call in result["tool_calls"]] == [
        "query_user",
        "query_asset",
        "create_ticket",
    ]
    assert result["tool_calls"][1].arguments == {"asset_id": "PC-1001"}
    assert result["tool_calls"][2].arguments["priority"] == "high"


def test_ticket_graph_stops_when_user_is_missing():
    users, assets, tickets = _services()
    graph = build_graph(user_service=users, asset_service=assets, ticket_service=tickets)

    result = graph.invoke(_ticket_state(user_id="missing"))

    assert result["ticket_status"] == "user_not_found"
    assert [call.name for call in result["tool_calls"]] == ["query_user"]
    assert tickets.list_tickets() == []


def test_ticket_graph_rejects_asset_owner_mismatch():
    users, _, tickets = _services()
    assets = AssetService(
        records={"PC-1001": {"asset_id": "PC-1001", "owner_id": "U2002"}}
    )
    graph = build_graph(user_service=users, asset_service=assets, ticket_service=tickets)

    result = graph.invoke(_ticket_state())

    assert result["ticket_status"] == "asset_forbidden"
    assert [call.name for call in result["tool_calls"]] == [
        "query_user",
        "query_asset",
    ]
    assert tickets.list_tickets() == []


def test_chat_api_returns_ticket_tool_calls_and_reuses_session_request():
    users, assets, tickets = _services()
    client = TestClient(
        create_app(
            ":memory:",
            user_service=users,
            asset_service=assets,
            ticket_service=tickets,
        )
    )
    request = {
        "message": "VPN 无法连接，设备 PC-1001，请创建工单，优先级高",
        "user_id": "U1001",
        "session_id": "session-1",
    }

    first = client.post("/api/chat", json=request).json()
    second = client.post("/api/chat", json=request).json()

    assert first["metadata"]["ticket_status"] == "created"
    assert [call["name"] for call in first["tool_calls"]] == [
        "query_user",
        "query_asset",
        "create_ticket",
    ]
    assert second["tool_calls"][-1]["result"]["ticket_id"] == "T-0001"
    assert len(tickets.list_tickets()) == 1


def test_chat_api_maps_ticket_service_failure_to_safe_response():
    users, assets, tickets = _services(
        FailureConfig(status_code=500, message="ticket database unavailable")
    )
    client = TestClient(
        create_app(
            ":memory:",
            user_service=users,
            asset_service=assets,
            ticket_service=tickets,
        )
    )

    response = client.post("/api/chat", json=_ticket_state())

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["ticket_status"] == "unavailable"
    assert "暂时无法创建" in body["answer"]
    assert body["tool_calls"][-1]["status"] == "failed"
    assert body["tool_calls"][-1]["error"] == "ticket database unavailable"
