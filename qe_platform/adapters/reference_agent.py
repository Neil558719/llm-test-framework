from __future__ import annotations

from typing import Any, Mapping

from fastapi.testclient import TestClient

from llmtest import LatencyMetrics, ResponseEnvelope, TokenUsage, ToolCall
from reference_agent.app import create_app
from reference_agent.services import ApprovalService, AssetService, FailureConfig, KnowledgeBase, TicketService, UserService
from qe_platform.scenarios import SetupSpec

from .base import ApplicationAdapterError


def _failure(setup: SetupSpec, name: str) -> FailureConfig:
    raw = setup.failures.get(name, {})
    return FailureConfig(raw.get("status_code"), raw.get("message", ""), raw.get("delay_seconds", 0.0))


def _records(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {str(item[key]): item for item in items}


class ReferenceAgentAdapter:
    def __init__(self, client: Any):
        self.client = client

    @classmethod
    def from_setup(cls, setup: SetupSpec) -> "ReferenceAgentAdapter":
        app = create_app(
            ":memory:",
            knowledge_base=KnowledgeBase(setup.knowledge, _failure(setup, "knowledge")),
            user_service=UserService(_records(setup.users, "user_id"), _failure(setup, "user")),
            asset_service=AssetService(_records(setup.assets, "asset_id"), _failure(setup, "asset")),
            ticket_service=TicketService(_failure(setup, "ticket")),
            approval_service=ApprovalService(_failure(setup, "approval")),
        )
        return cls(TestClient(app))

    def send(self, message: str, *, user_id: str, session_id: str) -> ResponseEnvelope:
        response = self.client.post("/api/chat", json={"message": message, "user_id": user_id, "session_id": session_id})
        if response.status_code < 200 or response.status_code >= 300:
            raise ApplicationAdapterError(f"application returned HTTP {response.status_code}", response.status_code)
        try:
            body = response.json()
            if not isinstance(body, Mapping):
                raise ValueError("response is not an object")
            calls = [ToolCall(call["name"], call.get("arguments", {}), call.get("result"), call.get("status", "succeeded"), call.get("error", "")) for call in body.get("tool_calls", [])]
            usage_raw = body.get("usage")
            usage = TokenUsage(usage_raw.get("prompt_tokens", 0), usage_raw.get("completion_tokens", 0)) if isinstance(usage_raw, Mapping) else None
            latency_raw = body.get("latency")
            latency = LatencyMetrics(latency_raw.get("total_ms", 0.0), latency_raw.get("ttft_ms")) if isinstance(latency_raw, Mapping) else None
            return ResponseEnvelope(str(body.get("answer", "")), list(body.get("sources", [])), calls, str(body.get("conversation_id", "")), str(body.get("trace_id", "")), usage, latency, dict(body.get("raw_response", {})), dict(body.get("metadata", {})))
        except (KeyError, TypeError, ValueError) as exc:
            raise ApplicationAdapterError("application returned invalid JSON response", response.status_code) from exc
