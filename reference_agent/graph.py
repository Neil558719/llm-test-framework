"""参考 Agent 的最小 LangGraph 状态图。"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .services.common import ServiceError
from .services.knowledge_base import KnowledgeBase


class AgentState(TypedDict):
    message: str
    answer: str
    sources: list[str]
    knowledge_status: str
    error: dict[str, object]


def _respond(state: AgentState, knowledge_base: KnowledgeBase) -> AgentState:
    message = state.get("message", "").strip()
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


def build_graph(knowledge_base: KnowledgeBase | None = None):
    knowledge_base = knowledge_base or KnowledgeBase()
    builder = StateGraph(AgentState)
    builder.add_node("respond", lambda state: _respond(state, knowledge_base))
    builder.add_edge(START, "respond")
    builder.add_edge("respond", END)
    return builder.compile()
