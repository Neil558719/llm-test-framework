"""参考 Agent 的 FastAPI 应用入口。"""

from __future__ import annotations

import uuid
import os
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from llmtest import LatencyMetrics, ResponseEnvelope, ModelVersion, CostMetrics, TokenUsage
from llmtest.config import Config
from llmtest.cost import PriceTable

from .graph import build_graph
from .services.assets import AssetService
from .services.approvals import ApprovalService
from .services.knowledge_base import KnowledgeBase
from .services.tickets import TicketService
from .services.users import UserService
from .storage import SQLiteStore


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    user_id: str = Field(default="test-user", min_length=1)
    session_id: str | None = None


class LoginRequest(BaseModel):
    user_id: str = Field(min_length=1)


def create_app(
    database: str | None = None,
    knowledge_base: KnowledgeBase | None = None,
    user_service: UserService | None = None,
    asset_service: AssetService | None = None,
    ticket_service: TicketService | None = None,
    approval_service: ApprovalService | None = None,
    model_client: Any | None = None,
    price_table: PriceTable | None = None,
) -> FastAPI:
    database = database or os.getenv("REFERENCE_AGENT_DATABASE", "reference_agent.db")
    app = FastAPI(title="Reference IT Service Desk Agent")
    store = SQLiteStore(database)
    graph = build_graph(knowledge_base, user_service, asset_service, ticket_service, approval_service)
    # Keep the self-contained reference application offline by default.  A real
    # client is an explicit deployment choice, independent from llmtest's judge.
    app_config = Config.from_env(mode=os.getenv("REFERENCE_AGENT_MODEL_MODE", "mock"))
    # The reference Agent must only report observations from model execution
    # owned by its runtime. It never invokes the evaluation client as a side effect.
    client = model_client
    prices = price_table or PriceTable.from_json(app_config.pricing_table)
    app.state.store = store
    app.state.access_drafts = {}

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "reference-agent"}

    @app.post("/api/login")
    def login(request: LoginRequest) -> dict[str, str]:
        session_id = str(uuid.uuid4())
        store.upsert_session(session_id, request.user_id)
        return {"session_id": session_id, "user_id": request.user_id}

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str) -> dict[str, str]:
        session = store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        return session

    def _run_chat(request: ChatRequest) -> dict[str, Any]:
        session_id = request.session_id or str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        store.upsert_session(session_id, request.user_id)
        draft = app.state.access_drafts.get(session_id, "")
        effective_message = f"{draft} {request.message}".strip() if draft else request.message
        result = graph.invoke(
            {
                "message": effective_message,
                "answer": "",
                "sources": [],
                "user_id": request.user_id,
                "session_id": session_id,
                "tool_calls": [],
            }
        )
        if result.get("approval_status") == "needs_information":
            app.state.access_drafts[session_id] = effective_message
        else:
            app.state.access_drafts.pop(session_id, None)
        observed_version = getattr(client, "last_model_version", ModelVersion(
            app_config.provider if app_config.mode == "real" else "mock",
            app_config.model or ("reference-agent" if app_config.mode == "real" else "mock-v1"),
        ))
        observed_version = ModelVersion(
            provider=observed_version.provider, model=observed_version.model,
            prompt=os.getenv("REFERENCE_AGENT_PROMPT_VERSION", "reference-agent-prompt-v1"),
            knowledge_base=os.getenv("REFERENCE_AGENT_KNOWLEDGE_VERSION", "knowledge-base-v1"),
            tools=os.getenv("REFERENCE_AGENT_TOOLS_VERSION", "reference-tools-v1"),
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
                "approval_status": result.get("approval_status", ""),
                "handoff_reason": result.get("handoff_reason", ""),
            },
            usage=getattr(client, "last_usage", None) if client is not None else None,
            model_version=observed_version,
        )
        pricing_provider = envelope.model_version.provider if client is not None else app_config.provider
        envelope.cost = prices.calculate(envelope.usage, provider=pricing_provider, model=envelope.model_version.model) if envelope.usage and envelope.model_version else None
        return envelope.as_dict()

    @app.post("/api/chat")
    def chat(request: ChatRequest) -> dict[str, Any]:
        return _run_chat(request)

    @app.post("/api/chat/stream")
    def chat_stream(request: ChatRequest) -> StreamingResponse:
        response = _run_chat(request)

        def events():
            yield f"data: {json.dumps({'type': 'start', 'conversation_id': response['conversation_id']})}\n\n"
            answer = response["answer"]
            for index in range(0, len(answer), 24):
                yield f"data: {json.dumps({'type': 'chunk', 'text': answer[index:index + 24]})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'response': response}, ensure_ascii=False)}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    app.mount("/", StaticFiles(directory=Path(__file__).parent / "web", html=True), name="web")

    return app
