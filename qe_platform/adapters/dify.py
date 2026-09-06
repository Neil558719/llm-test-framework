from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from types import MappingProxyType
from threading import Lock
from time import perf_counter
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from llmtest import LatencyMetrics, ResponseEnvelope

from .base import ApplicationAdapterError


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


def _required_string(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(name)
    return value


def _optional_string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _extract_sources(payload: Mapping[str, Any]) -> list[str]:
    resources = payload.get("retriever_resources")
    if resources is None:
        metadata = payload.get("metadata")
        resources = metadata.get("retriever_resources") if isinstance(metadata, Mapping) else None
    if not isinstance(resources, list):
        return []
    sources = []
    for resource in resources:
        if not isinstance(resource, Mapping):
            continue
        for name in ("content", "segment_content", "segment"):
            content = resource.get(name)
            if isinstance(content, str) and content:
                sources.append(content)
                break
    return sources


def _safe_metadata(payload: Mapping[str, Any], source_count: int) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    message_id = _optional_string(payload.get("message_id"))
    if message_id:
        metadata["dify_message_id"] = message_id
    if source_count:
        metadata["dify_retriever_resource_count"] = source_count
    return metadata


class DifyChatAdapter:
    def __init__(self, config: DifyAdapterConfig):
        self.config = config
        self._conversation_ids: dict[tuple[str, str], str] = {}
        self._conversation_lock = Lock()

    @classmethod
    def from_environment(cls) -> "DifyChatAdapter":
        return cls(DifyAdapterConfig.from_environment())

    def send(self, message: str, *, user_id: str, session_id: str) -> ResponseEnvelope:
        key = (user_id, session_id)
        payload: dict[str, Any] = {
            "inputs": dict(self.config.inputs),
            "query": message,
            "response_mode": "blocking",
            "user": user_id,
        }
        with self._conversation_lock:
            conversation_id = self._conversation_ids.get(key)
        if conversation_id:
            payload["conversation_id"] = conversation_id
        started = perf_counter()
        data = self._post_json(payload)
        elapsed_ms = (perf_counter() - started) * 1000
        try:
            answer = _required_string(data, "answer")
            next_conversation_id = _required_string(data, "conversation_id")
        except ValueError as exc:
            raise ApplicationAdapterError("Dify returned invalid response", 200) from exc
        sources = _extract_sources(data)
        with self._conversation_lock:
            self._conversation_ids[key] = next_conversation_id
        return ResponseEnvelope(
            answer=answer,
            sources=sources,
            conversation_id=next_conversation_id,
            trace_id=_optional_string(data.get("message_id")),
            latency=LatencyMetrics(total_ms=elapsed_ms),
            raw_response={},
            metadata=_safe_metadata(data, len(sources)),
        )

    def _post_json(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        request = Request(
            "%s/chat-messages" % self.config.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": "Bearer %s" % self.config.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                status_code = response.getcode()
                body = response.read()
        except HTTPError as exc:
            raise ApplicationAdapterError("Dify API returned HTTP %s" % exc.code, exc.code) from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise ApplicationAdapterError("Dify request failed") from exc
        if status_code < 200 or status_code >= 300:
            raise ApplicationAdapterError("Dify API returned HTTP %s" % status_code, status_code)
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApplicationAdapterError("Dify returned invalid JSON", status_code) from exc
        if not isinstance(data, Mapping):
            raise ApplicationAdapterError("Dify returned invalid JSON", status_code)
        return data
