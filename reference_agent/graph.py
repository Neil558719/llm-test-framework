"""参考 Agent 的最小 LangGraph 状态图。"""

from __future__ import annotations

import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from llmtest import ToolCall

from .services.assets import AssetService
from .services.approvals import ApprovalService
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
    approval_status: str
    handoff_reason: str


def _is_ticket_intent(message: str) -> bool:
    return any(keyword in message for keyword in ("报修", "创建工单", "提交工单")) or (
        "故障" in message and re.search(r"PC[-_][A-Za-z0-9]+", message, re.IGNORECASE) is not None
    )


def _is_access_intent(message: str) -> bool:
    return any(
        keyword in message
        for keyword in ("申请权限", "申请安装", "安装软件", "访问权限", "申请访问")
    )


def _extract_software(message: str) -> str:
    known = ("Admin Console", "VPN", "Slack", "Chrome", "生产数据库")
    lowered = message.lower()
    for software in known:
        if software.lower() in lowered:
            return software
    return ""


def _extract_justification(message: str) -> str:
    for marker in ("理由是", "因为", "用于"):
        if marker in message:
            value = message.split(marker, 1)[1].strip(" ：:，,。")
            if value:
                return value
    return ""


def _access_response(
    state: AgentState,
    user_service: UserService,
    approval_service: ApprovalService,
) -> AgentState:
    message = state.get("message", "").strip()
    calls: list[ToolCall] = []
    user_id = state.get("user_id", "test-user")
    try:
        user = user_service.get_user(user_id)
    except ServiceError as exc:
        calls.append(ToolCall("query_user", {"user_id": user_id}, status="failed", error=exc.message))
        return {**state, "answer": "用户服务暂时不可用，请稍后重试。", "tool_calls": calls, "approval_status": "unavailable"}
    calls.append(ToolCall("query_user", {"user_id": user_id}, result=user))
    if user is None:
        return {**state, "answer": "未找到当前用户信息，暂时无法申请权限。", "tool_calls": calls, "approval_status": "user_not_found"}

    hints = state.get("runtime_hints", {})
    parameters = hints.get("parameters", {}) if isinstance(hints, dict) else {}
    software = str(parameters.get("software") or _extract_software(message))
    justification = str(parameters.get("justification") or _extract_justification(message))
    if not software or not justification:
        missing = "软件名称" if not software else "申请理由"
        return {
            **state,
            "answer": f"请补充{missing}后再提交权限申请。",
            "tool_calls": calls,
            "approval_status": "needs_information",
        }
    if "人工" in message:
        return {
            **state,
            "answer": "已为你转接人工审批，请等待工作人员处理。",
            "tool_calls": calls,
            "approval_status": "handoff_required",
            "handoff_reason": "user_requested",
        }
    if software.lower() in {"admin console", "生产数据库".lower()}:
        return {
            **state,
            "answer": "该软件权限属于受限资源，已转接人工审批。",
            "tool_calls": calls,
            "approval_status": "handoff_required",
            "handoff_reason": "restricted_software",
        }

    arguments = {
        "user_id": user_id,
        "software": software,
        "justification": justification,
        "idempotency_key": f"{state.get('session_id', 'anonymous')}:{user_id}:{software.lower()}",
    }
    try:
        approval = approval_service.create_approval(**arguments)
    except ServiceError as exc:
        calls.append(ToolCall("create_approval", arguments, status="failed", error=exc.message))
        return {**state, "answer": "审批服务暂时无法提交申请，请稍后重试。", "tool_calls": calls, "approval_status": "unavailable"}
    calls.append(ToolCall("create_approval", arguments, result=approval))
    return {
        **state,
        "answer": f"权限申请已提交，审批单 {approval['approval_id']} 当前状态为 {approval['status']}。",
        "tool_calls": calls,
        "approval_status": approval["status"],
    }


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

    hints = state.get("runtime_hints", {})
    parameters = hints.get("parameters", {}) if isinstance(hints, dict) else {}
    asset_match = re.search(r"PC[-_][A-Za-z0-9]+", message, re.IGNORECASE)
    asset_id = str(parameters.get("asset_id") or (asset_match.group(0).upper().replace("_", "-") if asset_match else ""))
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

    priority = str(parameters.get("priority") or ("high" if any(word in message for word in ("高", "紧急", "严重")) else "normal"))
    category = str(parameters.get("category") or ("vpn" if "VPN" in message.upper() else "general"))
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
    approval_service: ApprovalService,
) -> AgentState:
    message = state.get("message", "").strip()
    hints = state.get("runtime_hints", {})
    hinted_intent = hints.get("intent") if isinstance(hints, dict) else None
    if hinted_intent == "access" or (not hinted_intent and _is_access_intent(message)):
        return _access_response(state, user_service, approval_service)
    if hinted_intent == "ticket" or (not hinted_intent and _is_ticket_intent(message)):
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
    approval_service: ApprovalService | None = None,
):
    knowledge_base = knowledge_base or KnowledgeBase()
    user_service = user_service or UserService()
    asset_service = asset_service or AssetService()
    ticket_service = ticket_service or TicketService()
    approval_service = approval_service or ApprovalService()
    builder = StateGraph(AgentState)
    builder.add_node(
        "respond",
        lambda state: _respond(
            state,
            knowledge_base,
            user_service,
            asset_service,
            ticket_service,
            approval_service,
        ),
    )
    builder.add_edge(START, "respond")
    builder.add_edge("respond", END)
    return builder.compile()
