from __future__ import annotations

import json
import time
from typing import Any, Callable

from llmtest import LatencyMetrics
from llmtest.clients.base import extract_json

from .config import AgentModelConfig
from .providers import ModelProviderRegistry


class AgentRuntime:
    """LLM boundary; deterministic graph remains authoritative for business effects."""

    def __init__(self, graph: Any, config: AgentModelConfig | None = None, registry: ModelProviderRegistry | None = None):
        self.graph = graph
        self.registry = registry or ModelProviderRegistry.with_defaults()
        self.config = config or AgentModelConfig.from_env()
        self.client = self.registry.create_client(self.config)

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
        try:
            raw = self.client.complete([{"role": "system", "content": "Return JSON only: {intent,parameters}."}, {"role": "user", "content": message}], temperature=self.config.temperature, max_tokens=self.config.max_tokens)
            parsed = extract_json(raw)
            if not isinstance(parsed, dict) or parsed.get("intent") not in {"knowledge", "ticket", "access", "unknown"}:
                raise ValueError("invalid intent schema")
            hints = parsed
            metadata["intent_source"] = "model"
            metadata["parameter_extraction_status"] = "validated"
        except Exception as exc:  # model failures must not block deterministic service
            metadata["fallback_reason"] = type(exc).__name__
        result = self.graph.invoke({**state, **({"runtime_hints": hints} if hints else {})})
        if self.config.mode == "real":
            try:
                answer = self.client.complete([
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
        result["metadata"]["intent"] = hints.get("intent", "")
        result["metadata"]["latency_ms"] = (time.perf_counter() - started) * 1000.0
        return result
