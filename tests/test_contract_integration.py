from llmtest import ResponseEnvelope

from qe_platform.contracts import (
    ToolContract,
    assert_business_state,
    assert_tool_contract,
    assert_tool_order,
)
from reference_agent.graph import build_graph
from reference_agent.services import (
    ApprovalService,
    AssetService,
    TicketService,
    UserService,
)


def _users():
    return UserService(records={"U1001": {"user_id": "U1001", "name": "张三"}})


def test_ticket_agent_calls_satisfy_public_contracts_and_business_state():
    graph = build_graph(
        user_service=_users(),
        asset_service=AssetService(records={"PC-1001": {"asset_id": "PC-1001", "owner_id": "U1001"}}),
        ticket_service=TicketService(),
    )
    result = graph.invoke({"message": "VPN 故障，设备 PC-1001，请创建工单", "answer": "", "sources": [], "user_id": "U1001", "session_id": "m7-ticket", "tool_calls": []})
    envelope = ResponseEnvelope(answer=result["answer"], tool_calls=result["tool_calls"], metadata={"ticket_status": result["ticket_status"]})

    assert_tool_order(envelope.tool_calls, ["query_user", "query_asset", "create_ticket"])
    assert_tool_contract(envelope.tool_calls[2], ToolContract("create_ticket", {"type": "object", "required": ["user_id", "asset_id", "category", "priority", "idempotency_key"]}, {"type": "object", "required": ["ticket_id", "status"]}), call_index=2)
    assert_business_state(envelope, "metadata.ticket_status", "created")
    assert_business_state(envelope, "tool_calls[2].result.status", "created")


def test_access_agent_calls_satisfy_public_contracts_and_business_state():
    graph = build_graph(user_service=_users(), approval_service=ApprovalService())
    result = graph.invoke({"message": "申请安装 VPN，理由是远程办公", "answer": "", "sources": [], "user_id": "U1001", "session_id": "m7-access", "tool_calls": []})
    envelope = ResponseEnvelope(answer=result["answer"], tool_calls=result["tool_calls"], metadata={"approval_status": result["approval_status"]})

    assert_tool_order(envelope.tool_calls, ["query_user", "create_approval"])
    assert_business_state(envelope, "metadata.approval_status", "pending")
    assert_business_state(envelope, "tool_calls[1].result.status", "pending")
