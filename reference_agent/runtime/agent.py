from __future__ import annotations

import json
import time
import os
from typing import Any, Callable

from llmtest import LatencyMetrics, TokenUsage, ModelVersion
from llmtest.clients.base import extract_json

from .config import AgentModelConfig
from .providers import ModelProviderRegistry


class AgentRuntime:
    """LLM boundary; deterministic graph remains authoritative for business effects."""

    def __init__(self, graph: Any, config: AgentModelConfig | None = None, registry: ModelProviderRegistry | None = None):
        self.graph = graph
        self.registry = registry or ModelProviderRegistry.with_defaults()
        self.config = config or AgentModelConfig.from_env()
        self.client = None

    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        message = str(state.get("message", ""))
        metadata = {
            "model_mode": self.config.mode,
            "model_provider": self.config.provider,
            "model_name": self.config.model,
            "intent_source": "deterministic",
            "parameter_extraction_status": "fallback",
            "generation_status": "deterministic",
            "fallback_reason": "",
        }
        hints: dict[str, Any] = {}
        client = self.client or self.registry.create_client(self.config)
        usages = []
        try:
            raw = client.complete([{"role": "system", "content": "Return JSON only: {intent,parameters}."}, {"role": "user", "content": message}], temperature=self.config.temperature, max_tokens=self.config.max_tokens)
            if getattr(client, "last_usage", None):
                usages.append(client.last_usage)
            parsed = extract_json(raw)
            parsed = self._normalize_hints(parsed)
            if parsed is None:
                raise ValueError("invalid intent schema")
            hints = parsed
            metadata["intent_source"] = "model"
            metadata["parameter_extraction_status"] = "validated"
        except Exception as exc:  # model failures must not block deterministic service
            metadata["fallback_reason"] = type(exc).__name__
        result = self.graph.invoke({**state, **({"runtime_hints": hints} if hints else {})})
        if self.config.mode == "real":
            try:
                answer = client.complete([
                    {"role": "system", "content": "Answer the user using only the supplied business result. Do not invent actions or statuses."},
                    {"role": "user", "content": json.dumps({"message": message, "business_result": result.get("answer", "")}, ensure_ascii=False)},
                ], temperature=self.config.temperature, max_tokens=self.config.max_tokens)
                if answer.strip():
                    result["answer"] = answer.strip()
                    metadata["generation_status"] = "model"
                else:
                    metadata["generation_status"] = "fallback"
                    metadata["fallback_reason"] = "empty_generation"
            except Exception as exc:
                metadata["generation_status"] = "fallback"
                metadata["fallback_reason"] = type(exc).__name__
        result.setdefault("metadata", {}).update(metadata)
        if usages or getattr(client, "last_usage", None):
            if getattr(client, "last_usage", None) and not usages:
                usages.append(client.last_usage)
            result["metadata"]["usage"] = TokenUsage(sum(item.prompt_tokens for item in usages), sum(item.completion_tokens for item in usages)).as_dict()
        result["metadata"]["model_version"] = ModelVersion(
            self.config.provider, self.config.model or "",
            os.getenv("REFERENCE_AGENT_PROMPT_VERSION", "reference-agent-prompt-v1"),
            os.getenv("REFERENCE_AGENT_KNOWLEDGE_VERSION", "knowledge-base-v1"),
            os.getenv("REFERENCE_AGENT_TOOLS_VERSION", "reference-tools-v1"),
        ).as_dict()
        result["metadata"]["intent"] = hints.get("intent", "")
        result["metadata"]["latency_ms"] = (time.perf_counter() - started) * 1000.0
        return result

    @staticmethod
    def _normalize_hints(parsed: Any) -> dict[str, Any] | None:
        if not isinstance(parsed, dict):
            return None
        aliases = {
            "create_ticket": "ticket", "report_issue": "ticket", "故障工单": "ticket",
            "create_access_request": "access", "request_access": "access", "权限申请": "access",
            "qa": "knowledge", "question": "knowledge", "问答": "knowledge",
        }
        intent = str(parsed.get("intent", "")).strip().lower()
        intent = aliases.get(intent, intent)
        if intent not in {"knowledge", "ticket", "access", "unknown"}:
            return None
        raw_parameters = parsed.get("parameters", {})
        if not isinstance(raw_parameters, dict):
            return None
        parameters = dict(raw_parameters)
        if "asset_id" not in parameters and parameters.get("device"):
            parameters["asset_id"] = parameters["device"]
        issue = str(parameters.get("issue", ""))
        if "category" not in parameters and "vpn" in issue.lower():
            parameters["category"] = "vpn"
        return {"intent": intent, "parameters": parameters}
