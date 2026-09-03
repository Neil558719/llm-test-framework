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
from llmtest.cost import PriceTable

from .graph import build_graph
from .services.assets import AssetService
from .services.approvals import ApprovalService
from .services.knowledge_base import KnowledgeBase
from .services.tickets import TicketService
from .services.users import UserService
from .storage import SQLiteStore
from .runtime import AgentModelConfig, ModelProviderRegistry
from .runtime.agent import AgentRuntime


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
    price_table: PriceTable | None = None,
    model_client: Any | None = None,
) -> FastAPI:
    database = database or os.getenv("REFERENCE_AGENT_DATABASE", "reference_agent.db")
    app = FastAPI(title="Reference IT Service Desk Agent")
    store = SQLiteStore(database)
    graph = build_graph(knowledge_base, user_service, asset_service, ticket_service, approval_service)
    registry = ModelProviderRegistry.with_defaults()
    app.state.model_registry = registry
    app.state.model_config = AgentModelConfig.from_env()
    app.state.runtime = AgentRuntime(graph, app.state.model_config, registry)
    if model_client is not None:
        app.state.runtime.client = model_client
    app.state.price_table = price_table or PriceTable.from_json(os.getenv("LLM_PRICING_TABLE"))
    app.state.store = store
    app.state.access_drafts = {}

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "reference-agent"}

    @app.get("/api/model-profiles")
    def model_profiles() -> dict[str, Any]:
        current = app.state.model_config
        return {"profiles": [{"name": p.name, "label": p.label, "mode": p.mode, "provider": p.provider, "base_url": p.base_url} for p in registry.profiles()], "current": current.as_public_dict()}

    @app.put("/api/model-profile")
    def set_model_profile(payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("profile", ""))
        try:
            profile = registry.resolve(name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        model = str(payload.get("model", ""))[:200]
        base_url = str(payload.get("base_url", profile.base_url))[:500]
        if profile.mode == "real" and not os.getenv("REFERENCE_AGENT_MODEL_API_KEY"):
            raise HTTPException(status_code=409, detail="server model API key is not configured")
        config = AgentModelConfig(profile=name, mode=profile.mode, provider=profile.provider, model=model, base_url=base_url, api_key=os.getenv("REFERENCE_AGENT_MODEL_API_KEY"))
        app.state.model_config = config
        app.state.runtime = AgentRuntime(graph, config, registry)
        return config.as_public_dict()

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
        result = app.state.runtime.invoke(
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
        envelope = ResponseEnvelope(
            answer=str(result["answer"]),
            conversation_id=session_id,
            trace_id=trace_id,
            sources=list(result.get("sources", [])),
            tool_calls=list(result.get("tool_calls", [])),
            latency=LatencyMetrics(),
            raw_response={"message": request.message},
            metadata={**result.get("metadata", {}),
                "service": "reference-agent",
                "knowledge_status": result.get("knowledge_status", "refused"),
                "ticket_status": result.get("ticket_status", ""),
                "approval_status": result.get("approval_status", ""),
                "handoff_reason": result.get("handoff_reason", ""),
            },
            usage=TokenUsage(int(result["metadata"]["usage"].get("prompt_tokens", 0)), int(result["metadata"]["usage"].get("completion_tokens", 0))) if result.get("metadata", {}).get("usage") else None,
            model_version=ModelVersion(
                provider=str(result["metadata"]["model_version"].get("provider", "")),
                model=str(result["metadata"]["model_version"].get("model", "")),
                prompt=str(result["metadata"]["model_version"].get("prompt", "")),
                knowledge_base=str(result["metadata"]["model_version"].get("knowledge_base", "")),
                tools=str(result["metadata"]["model_version"].get("tools", "")),
            ) if result.get("metadata", {}).get("model_version") else None,
        )
        if envelope.usage and envelope.model_version:
            envelope.cost = app.state.price_table.calculate(envelope.usage, provider=app.state.model_config.provider, model=envelope.model_version.model)
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
