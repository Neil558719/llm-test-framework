from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import urlsplit


_CAPABILITY_STATUSES = {"supported", "conditional", "unsupported"}


@dataclass(frozen=True)
class DifyCapability:
    key: str
    status: str
    description: str

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("Dify capability key is required")
        if self.status not in _CAPABILITY_STATUSES:
            raise ValueError("Dify capability status is invalid")
        if not self.description:
            raise ValueError("Dify capability description is required")

    def as_dict(self) -> dict[str, str]:
        return {"status": self.status, "description": self.description}


@dataclass(frozen=True)
class DifyCapabilityMatrix:
    capabilities: tuple[DifyCapability, ...]

    def __post_init__(self) -> None:
        keys = [item.key for item in self.capabilities]
        if len(keys) != len(set(keys)):
            raise ValueError("Dify capability keys must be unique")

    def as_dict(self) -> dict[str, dict[str, str]]:
        return {item.key: item.as_dict() for item in self.capabilities}


DIFY_CHAT_CAPABILITY_MATRIX = DifyCapabilityMatrix(
    capabilities=(
        DifyCapability("chat_blocking", "supported", "Dify Chat blocking messages are adapted to the platform response protocol."),
        DifyCapability("conversation_continuation", "supported", "A Dify conversation ID is reused only for the same platform user and session."),
        DifyCapability("retrieval_resources", "conditional", "Retrieved text is exposed only when Dify returns retriever_resources."),
        DifyCapability("authentication_errors", "supported", "Bearer authentication and sanitized transport or HTTP error classification are tested."),
        DifyCapability("tool_calls", "unsupported", "Dify Chat tool calls are not observable through this adapter protocol."),
        DifyCapability("usage_cost_model_version", "unsupported", "Blocking Chat responses do not provide a stable complete usage, cost, or model-version contract."),
        DifyCapability("streaming_ttft", "unsupported", "This compatibility adapter only supports blocking responses and does not collect TTFT."),
        DifyCapability("workflow_completion_files_multimodal", "unsupported", "Workflow, Completion, file, and multimodal APIs are outside this Chat compatibility scope."),
    )
)


@dataclass(frozen=True)
class DifyAdapterConfig:
    base_url: str
    api_key: str
    inputs: Mapping[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        base_url = self.base_url.strip().rstrip("/")
        if not base_url:
            raise ValueError("DIFY_BASE_URL is required")
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("DIFY_BASE_URL must be an absolute HTTP URL")
        if not self.api_key.strip():
            raise ValueError("DIFY_API_KEY is required")
        if not isinstance(self.inputs, Mapping):
            raise ValueError("DIFY_INPUTS_JSON must be an object")
        try:
            timeout_seconds = float(self.timeout_seconds)
        except (TypeError, ValueError) as exc:
            raise ValueError("DIFY_TIMEOUT_SECONDS must be a positive number") from exc
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("DIFY_TIMEOUT_SECONDS must be a positive number")
        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(self, "api_key", self.api_key.strip())
        object.__setattr__(self, "inputs", MappingProxyType(dict(self.inputs)))
        object.__setattr__(self, "timeout_seconds", timeout_seconds)

    @classmethod
    def from_environment(cls) -> "DifyAdapterConfig":
        raw_inputs = os.environ.get("DIFY_INPUTS_JSON", "").strip()
        if not raw_inputs:
            inputs: Mapping[str, Any] = {}
        else:
            try:
                inputs = json.loads(raw_inputs)
            except json.JSONDecodeError as exc:
                raise ValueError("DIFY_INPUTS_JSON must be valid JSON object") from exc
            if not isinstance(inputs, dict):
                raise ValueError("DIFY_INPUTS_JSON must be an object")
        return cls(
            base_url=os.environ.get("DIFY_BASE_URL", ""),
            api_key=os.environ.get("DIFY_API_KEY", ""),
            inputs=inputs,
            timeout_seconds=os.environ.get("DIFY_TIMEOUT_SECONDS", "30"),
        )
