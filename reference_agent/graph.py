"""参考 Agent 的最小 LangGraph 状态图。"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class AgentState(TypedDict):
    message: str
    answer: str


def _respond(state: AgentState) -> AgentState:
    message = state.get("message", "").strip()
    answer = "你好，我是企业 IT 服务台助手。"
    if message:
        answer = f"已收到你的请求：{message}"
    return {**state, "answer": answer}


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("respond", _respond)
    builder.add_edge(START, "respond")
    builder.add_edge("respond", END)
    return builder.compile()
