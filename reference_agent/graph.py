"""参考 Agent 的最小 LangGraph 状态图。"""

from __future__ import annotations

import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from llmtest import ToolCall

from .services.assets import AssetService
from .services.common import ServiceError
from .services.knowledge_base import KnowledgeBase
from .services.tickets import TicketService
from .services.users import UserService


class AgentState(TypedDict):
    message: str
    answer: str
    sources: list[str]
    knowledge_status: str
    error: dict[str, object]
    user_id: str
    session_id: str
    tool_calls: list[ToolCall]
    ticket_status: str


def _is_ticket_intent(message: str) -> bool:
    return any(keyword in message for keyword in ("报修", "创建工单", "提交工单")) or (
        "故障" in message and re.search(r"PC[-_][A-Za-z0-9]+", message, re.IGNORECASE) is not None
    )


def _ticket_response(
    state: AgentState,
    user_service: UserService,
    asset_service: AssetService,
    ticket_service: TicketService,
) -> AgentState:
    message = state.get("message", "").strip()
    calls: list[ToolCall] = []
    user_id = state.get("user_id", "test-user")
    try:
        user = user_service.get_user(user_id)
    except ServiceError as exc:
        calls.append(ToolCall("query_user", {"user_id": user_id}, status="failed", error=exc.message))
        return {**state, "answer": "用户服务暂时不可用，请稍后重试。", "tool_calls": calls, "ticket_status": "unavailable"}
    calls.append(ToolCall("query_user", {"user_id": user_id}, result=user))
    if user is None:
        return {**state, "answer": "未找到当前用户信息，暂时无法创建工单。", "tool_calls": calls, "ticket_status": "user_not_found"}

    asset_match = re.search(r"PC[-_][A-Za-z0-9]+", message, re.IGNORECASE)
    asset_id = asset_match.group(0).upper().replace("_", "-") if asset_match else ""
    if not asset_id:
        return {**state, "answer": "请提供设备编号后再创建工单。", "tool_calls": calls, "ticket_status": "asset_required"}
    try:
        asset = asset_service.get_asset(asset_id)
    except ServiceError as exc:
        calls.append(ToolCall("query_asset", {"asset_id": asset_id}, status="failed", error=exc.message))
        return {**state, "answer": "资产服务暂时不可用，请稍后重试。", "tool_calls": calls, "ticket_status": "unavailable"}
    calls.append(ToolCall("query_asset", {"asset_id": asset_id}, result=asset))
    if asset is None:
        return {**state, "answer": "未找到该设备，暂时无法创建工单。", "tool_calls": calls, "ticket_status": "asset_not_found"}
    if asset.get("owner_id") != user_id:
        return {**state, "answer": "该设备不属于当前用户，无法创建工单。", "tool_calls": calls, "ticket_status": "asset_forbidden"}

    priority = "high" if any(word in message for word in ("高", "紧急", "严重")) else "normal"
    category = "vpn" if "VPN" in message.upper() else "general"
    arguments = {
        "user_id": user_id,
        "asset_id": asset_id,
        "category": category,
        "priority": priority,
        "idempotency_key": f"{state.get('session_id', 'anonymous')}:{asset_id}:{category}",
    }
    try:
        ticket = ticket_service.create_ticket(**arguments)
    except ServiceError as exc:
        calls.append(ToolCall("create_ticket", arguments, status="failed", error=exc.message))
        return {**state, "answer": "工单服务暂时无法创建工单，请稍后重试。", "tool_calls": calls, "ticket_status": "unavailable"}
    calls.append(ToolCall("create_ticket", arguments, result=ticket))
    return {
        **state,
        "answer": f"工单 {ticket['ticket_id']} 已创建，当前状态为 {ticket['status']}。",
        "tool_calls": calls,
        "ticket_status": ticket["status"],
    }


def _respond(
    state: AgentState,
    knowledge_base: KnowledgeBase,
    user_service: UserService,
    asset_service: AssetService,
    ticket_service: TicketService,
) -> AgentState:
    message = state.get("message", "").strip()
    if _is_ticket_intent(message):
        return _ticket_response(state, user_service, asset_service, ticket_service)
    if not message:
        return {**state, "answer": "请输入需要查询的 IT 问题。", "sources": [], "knowledge_status": "refused"}
    try:
        matches = knowledge_base.search(message, limit=1)
    except ServiceError as exc:
        return {
            **state,
            "answer": "知识库服务暂时不可用，请稍后重试。",
            "sources": [],
            "knowledge_status": "unavailable",
            "error": {"status_code": exc.status_code, "message": exc.message},
        }
    if not matches:
        return {
            **state,
            "answer": "抱歉，知识库中没有找到相关信息，我无法可靠回答。",
            "sources": [],
            "knowledge_status": "refused",
        }
    match = matches[0]
    return {
        **state,
        "answer": f"根据《{match['title']}》：{match['content']}",
        "sources": [str(match["document_id"])],
        "knowledge_status": "answered",
    }


def build_graph(
    knowledge_base: KnowledgeBase | None = None,
    user_service: UserService | None = None,
    asset_service: AssetService | None = None,
    ticket_service: TicketService | None = None,
):
    knowledge_base = knowledge_base or KnowledgeBase()
    user_service = user_service or UserService()
    asset_service = asset_service or AssetService()
    ticket_service = ticket_service or TicketService()
    builder = StateGraph(AgentState)
    builder.add_node(
        "respond",
        lambda state: _respond(
            state, knowledge_base, user_service, asset_service, ticket_service
        ),
    )
    builder.add_edge(START, "respond")
    builder.add_edge("respond", END)
    return builder.compile()
