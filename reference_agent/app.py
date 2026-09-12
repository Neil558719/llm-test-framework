"""参考 Agent 的 FastAPI 应用入口。"""

from __future__ import annotations

import uuid
import os
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from llmtest import LatencyMetrics, ResponseEnvelope, ModelVersion, CostMetrics, TokenUsage
from llmtest.cost import PriceTable
from qe_platform.telemetry import build_trace_event
from qe_platform.telemetry.sink import TelemetrySink, telemetry_sink_from_environment
from qe_platform.auth.dependencies import AuthRuntime, install_auth_routes
from qe_platform.ops import readiness
from qe_platform.ops.metrics import PROCESS_METRICS, install_http_metrics
from qe_platform.production.secrets import SecretSource

from .graph import build_graph
from .privacy import access_slots, draft_message
from .services.assets import AssetService
from .services.approvals import ApprovalService
from .services.knowledge_base import KnowledgeBase
from .services.tickets import TicketService
from .services.users import UserService
from .storage import SQLiteStore
from .runtime import AgentModelConfig, ModelProviderRegistry
from .runtime.agent import AgentRuntime
from .faults import (
    FaultControlError,
    FaultControlSettings,
    FaultProfile,
    InjectedDatabaseError,
)


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
    fault_settings: FaultControlSettings | None = None,
    *,
    telemetry_sink: TelemetrySink | None = None,
    auth_runtime: AuthRuntime | None = None,
) -> FastAPI:
    database = database or os.getenv("REFERENCE_AGENT_DATABASE", "reference_agent.db")
    app = FastAPI(title="Reference IT Service Desk Agent")
    store = SQLiteStore(database)
    ticket_service = ticket_service or TicketService(repository=store)
    approval_service = approval_service or ApprovalService(repository=store)
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
    app.state.fault_settings = fault_settings or FaultControlSettings.from_env()
    app.state.telemetry_sink = telemetry_sink or telemetry_sink_from_environment()
    app.state.auth_runtime = auth_runtime or AuthRuntime.from_environment()
    app.state.metrics = PROCESS_METRICS
    install_http_metrics(app, "reference")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "reference-agent"}

    @app.get("/api/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok", "service": "reference-agent"}

    @app.get("/api/health/ready")
    def health_ready() -> JSONResponse:
        bundle = {"database": store, **app.state.auth_runtime.readiness_bundle()}
        if not app.state.auth_runtime.development_mode:
            bundle["configuration"] = lambda: bool(app.state.model_config.as_public_dict()["configured"])
        result = readiness(bundle)
        payload = {"status": "ready" if result.ready else "not_ready", "service": "reference-agent", "checks": dict(result.checks)}
        return JSONResponse(payload, status_code=200 if result.ready else 503)

    @app.get("/api/metrics")
    def metrics(request: Request) -> dict[str, Any]:
        app.state.auth_runtime.require(request, "admin")
        return app.state.metrics.snapshot()

    @app.get("/api/model-profiles")
    def model_profiles() -> dict[str, Any]:
        current = app.state.model_config
        return {"profiles": [{"name": p.name, "label": p.label, "mode": p.mode, "provider": p.provider, "base_url": p.base_url} for p in registry.profiles()], "current": current.as_public_dict()}

    @app.put("/api/model-profile")
    def set_model_profile(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        app.state.auth_runtime.require(request, "admin")
        app.state.auth_runtime.require_csrf(request)
        name = str(payload.get("profile", ""))
        try:
            profile = registry.resolve(name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        model = str(payload.get("model", ""))[:200]
        base_url = str(payload.get("base_url", profile.base_url))[:500]
        try:
            api_key = SecretSource.from_environment(os.environ).get("REFERENCE_AGENT_MODEL_API_KEY")
        except ValueError:
            raise HTTPException(status_code=409, detail="server model API key is not configured") from None
        if profile.mode == "real" and not api_key:
            raise HTTPException(status_code=409, detail="server model API key is not configured")
        config = AgentModelConfig(profile=name, mode=profile.mode, provider=profile.provider, model=model, base_url=base_url, api_key=api_key)
        app.state.model_config = config
        app.state.runtime = AgentRuntime(graph, config, registry)
        return config.as_public_dict()

    @app.post("/api/login")
    def login(request: LoginRequest) -> dict[str, str]:
        if not app.state.auth_runtime.development_mode:
            raise HTTPException(status_code=403, detail="forbidden")
        session_id = str(uuid.uuid4())
        store.upsert_session(session_id, request.user_id)
        return {"session_id": session_id, "user_id": request.user_id}

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str, request: Request) -> dict[str, str]:
        principal = app.state.auth_runtime.require(request)
        session = store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        if not app.state.auth_runtime.development_mode and session["user_id"] != principal.subject:
            raise HTTPException(status_code=403, detail="forbidden")
        return session

    def _resolve_fault(
        token: str | None,
        raw_fault: str | None,
    ) -> FaultProfile | None:
        try:
            return app.state.fault_settings.resolve(token, raw_fault)
        except FaultControlError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    def _run_chat(
        request: ChatRequest,
        fault: FaultProfile | None = None,
    ) -> dict[str, Any]:
        session_id = request.session_id or str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        try:
            if fault is not None:
                fault.before_database()
        except InjectedDatabaseError as exc:
            raise HTTPException(status_code=503, detail="database temporarily unavailable") from exc
        store.upsert_session(session_id, request.user_id)
        draft = store.get_access_draft(session_id)
        effective_message = f"{draft} {request.message}".strip() if draft else request.message
        result = app.state.runtime.invoke(
            {
                "message": effective_message,
                "answer": "",
                "sources": [],
                "user_id": request.user_id,
                "session_id": session_id,
                "tool_calls": [],
                "fault": fault,
            }
        )
        if result.get("approval_status") == "needs_information":
            store.upsert_access_draft(session_id, draft_message(access_slots(effective_message)))
        else:
            store.delete_access_draft(session_id)
        for call in result.get("tool_calls", []):
            if call.name == "create_approval":
                if "justification" in call.arguments:
                    call.arguments = {**call.arguments, "justification": "provided" if call.arguments["justification"] else ""}
                if isinstance(call.result, dict) and "justification" in call.result:
                    call.result = {**call.result, "justification": "provided" if call.result["justification"] else ""}
        envelope = ResponseEnvelope(
            answer=str(result["answer"]),
            conversation_id=session_id,
            trace_id=trace_id,
            sources=list(result.get("sources", [])),
            tool_calls=list(result.get("tool_calls", [])),
            latency=LatencyMetrics(),
            raw_response={},
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
        response = envelope.as_dict()
        _emit_telemetry(request, effective_message, envelope)
        return response

    def _emit_telemetry(
        request: ChatRequest,
        effective_message: str,
        envelope: ResponseEnvelope,
    ) -> None:
        sink = app.state.telemetry_sink
        if not getattr(sink, "enabled", True):
            return
        try:
            usage = envelope.usage.as_dict() if envelope.usage else {}
            cost = envelope.cost.as_dict() if envelope.cost else None
            model_version = {
                key: value
                for key, value in (envelope.model_version.as_dict() if envelope.model_version else {}).items()
                if value
            }
            latency = {"status": "succeeded"}
            if envelope.latency:
                latency["total_ms"] = envelope.latency.total_ms
                if envelope.latency.ttft_ms is not None:
                    latency["ttft_ms"] = envelope.latency.ttft_ms
            event = build_trace_event(
                envelope.trace_id,
                "reference-agent",
                request.user_id,
                envelope.conversation_id,
                effective_message,
                envelope.answer,
                sink.hash_key,
                tool_calls=[{"name": call.name, "status": call.status} for call in envelope.tool_calls],
                metadata={"environment": "reference-agent"},
                usage=usage,
                cost=cost,
                model_version=model_version,
                latency=latency,
            )
            sink.emit(event)
        except Exception:
            return

    def _bind_identity(payload: ChatRequest, request: Request) -> ChatRequest:
        auth = app.state.auth_runtime
        principal = auth.require(request, "viewer")
        auth.require_csrf(request)
        if auth.development_mode:
            return payload
        session_id = payload.session_id or str(uuid.uuid4())
        if not store.claim_session(session_id, principal.subject):
            raise HTTPException(status_code=403, detail="forbidden")
        return payload.model_copy(update={"user_id": principal.subject, "session_id": session_id})

    @app.post("/api/chat")
    def chat(
        request: ChatRequest,
        http_request: Request,
        x_qe_test_token: str | None = Header(default=None, alias="X-QE-Test-Token"),
        x_qe_fault: str | None = Header(default=None, alias="X-QE-Fault"),
    ) -> dict[str, Any]:
        request = _bind_identity(request, http_request)
        return _run_chat(request, _resolve_fault(x_qe_test_token, x_qe_fault))

    @app.post("/api/chat/stream")
    def chat_stream(
        request: ChatRequest,
        http_request: Request,
        x_qe_test_token: str | None = Header(default=None, alias="X-QE-Test-Token"),
        x_qe_fault: str | None = Header(default=None, alias="X-QE-Fault"),
    ) -> StreamingResponse:
        request = _bind_identity(request, http_request)
        fault = _resolve_fault(x_qe_test_token, x_qe_fault)
        response = _run_chat(request, fault)

        def events():
            yield f"data: {json.dumps({'type': 'start', 'conversation_id': response['conversation_id']})}\n\n"
            if fault is not None and fault.type == "sse_interruption":
                return
            answer = response["answer"]
            for index in range(0, len(answer), 24):
                yield f"data: {json.dumps({'type': 'chunk', 'text': answer[index:index + 24]})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'response': response}, ensure_ascii=False)}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    install_auth_routes(app, app.state.auth_runtime)
    app.mount("/", StaticFiles(directory=Path(__file__).parent / "web", html=True), name="web")

    return app
