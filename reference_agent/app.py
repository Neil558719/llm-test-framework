"""参考 Agent 的 FastAPI 应用入口。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from llmtest import LatencyMetrics, ResponseEnvelope

from .graph import build_graph
from .services.assets import AssetService
from .services.knowledge_base import KnowledgeBase
from .services.tickets import TicketService
from .services.users import UserService
from .storage import SQLiteStore


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    user_id: str = Field(default="test-user", min_length=1)
    session_id: str | None = None


def create_app(
    database: str = "reference_agent.db",
    knowledge_base: KnowledgeBase | None = None,
    user_service: UserService | None = None,
    asset_service: AssetService | None = None,
    ticket_service: TicketService | None = None,
) -> FastAPI:
    app = FastAPI(title="Reference IT Service Desk Agent")
    store = SQLiteStore(database)
    graph = build_graph(knowledge_base, user_service, asset_service, ticket_service)
    app.state.store = store

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "reference-agent"}

    @app.post("/api/chat")
    def chat(request: ChatRequest) -> dict[str, Any]:
        session_id = request.session_id or str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        store.upsert_session(session_id, request.user_id)
        result = graph.invoke(
            {
                "message": request.message,
                "answer": "",
                "sources": [],
                "user_id": request.user_id,
                "session_id": session_id,
                "tool_calls": [],
            }
        )
        envelope = ResponseEnvelope(
            answer=str(result["answer"]),
            conversation_id=session_id,
            trace_id=trace_id,
            sources=list(result.get("sources", [])),
            tool_calls=list(result.get("tool_calls", [])),
            latency=LatencyMetrics(),
            raw_response={"message": request.message},
            metadata={
                "service": "reference-agent",
                "knowledge_status": result.get("knowledge_status", "refused"),
                "ticket_status": result.get("ticket_status", ""),
            },
        )
        return envelope.as_dict()

    return app
