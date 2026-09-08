from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping

from .redaction import VersionFingerprint, assert_sanitized_payload, fingerprint, sanitize_metadata


def _nonempty(name: str, value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be nonempty")


def _number(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return float(value)


def _fingerprint(name: str, value: str) -> None:
    _nonempty(name, value)
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower()):
        raise ValueError(f"{name} must be a SHA-256 hexadecimal fingerprint")


def _mapping(name: str, value: Mapping[str, Any], allowed: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be a string-keyed mapping")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"unknown {name} fields: {', '.join(unknown)}")
    return MappingProxyType(dict(value))


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("timestamp must be UTC")
    return value


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ToolSummary:
    name: str
    status: str

    def __post_init__(self) -> None:
        _nonempty("tool name", self.name)
        _nonempty("tool status", self.status)

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status}


@dataclass(frozen=True)
class TelemetryTrace:
    trace_id: str
    application: str
    timestamp: datetime
    request_fingerprint: str
    answer_fingerprint: str
    request_length: int
    answer_length: int
    user_fingerprint: str
    session_fingerprint: str
    tool_calls: tuple[ToolSummary, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    usage: Mapping[str, int] = field(default_factory=dict)
    cost: Mapping[str, Any] | None = None
    model_version: Mapping[str, VersionFingerprint] = field(default_factory=dict)
    latency: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("trace_id", "application"):
            _nonempty(name, getattr(self, name))
        for name in ("request_fingerprint", "answer_fingerprint", "user_fingerprint", "session_fingerprint"):
            _fingerprint(name, getattr(self, name))
        _utc(self.timestamp)
        for name in ("request_length", "answer_length"):
            if isinstance(getattr(self, name), bool) or not isinstance(getattr(self, name), int) or getattr(self, name) < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        usage = _mapping("usage", self.usage, {"prompt_tokens", "completion_tokens", "total_tokens"})
        for name, value in usage.items():
            _number(f"usage.{name}", value)
        cost = None
        if self.cost is not None:
            cost = _mapping("cost", self.cost, {"input", "output", "total", "input_cost", "output_cost", "total_cost", "currency", "price_version"})
            for name, value in cost.items():
                if name in {"input", "output", "total", "input_cost", "output_cost", "total_cost"}:
                    _number(f"cost.{name}", value)
                elif not isinstance(value, str):
                    raise ValueError(f"cost.{name} must be a string")
        model_version = _mapping("model_version", self.model_version, {"provider", "model", "prompt", "knowledge_base", "tools", "prompt_version", "knowledge_base_version", "tool_schema_version"})
        for name, value in model_version.items():
            if type(value) is not VersionFingerprint:
                raise ValueError(f"model_version.{name} requires a provenance-bearing fingerprint")
        latency = _mapping("latency", self.latency, {"total_ms", "ttft_ms", "status"})
        for name, value in latency.items():
            if name in {"total_ms", "ttft_ms"}:
                _number(f"latency.{name}", value)
            elif not isinstance(value, str) or not value:
                raise ValueError("latency.status must be nonempty")
        metadata = MappingProxyType(sanitize_metadata(self.metadata))
        tools = tuple(self.tool_calls)
        if not all(isinstance(tool, ToolSummary) for tool in tools):
            raise ValueError("tool_calls must contain ToolSummary values")
        object.__setattr__(self, "usage", usage)
        object.__setattr__(self, "cost", cost)
        object.__setattr__(self, "model_version", model_version)
        object.__setattr__(self, "latency", latency)
        object.__setattr__(self, "metadata", metadata)
        object.__setattr__(self, "tool_calls", tools)
        assert_sanitized_payload(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id, "application": self.application, "timestamp": _timestamp(self.timestamp),
            "request_fingerprint": self.request_fingerprint, "answer_fingerprint": self.answer_fingerprint,
            "request_length": self.request_length, "answer_length": self.answer_length,
            "source": {"user_fingerprint": self.user_fingerprint, "session_fingerprint": self.session_fingerprint},
            "tool_calls": [tool.as_dict() for tool in self.tool_calls], "metadata": dict(self.metadata),
            "usage": dict(self.usage), "cost": None if self.cost is None else dict(self.cost),
            "model_version": {key: value.digest for key, value in self.model_version.items()}, "latency": dict(self.latency),
        }


def build_trace_event(trace_id: str, application: str, user_id: str, session_id: str, request_text: str, answer_text: str, hash_key: str, *, tool_calls: list[Mapping[str, Any]], metadata: Mapping[str, Any], usage: Mapping[str, int], cost: Mapping[str, Any] | None, model_version: Mapping[str, str], latency: Mapping[str, Any]) -> TelemetryTrace:
    for name, value in {"trace_id": trace_id, "application": application, "user_id": user_id, "session_id": session_id, "request_text": request_text, "answer_text": answer_text}.items():
        _nonempty(name, value)
    if not isinstance(tool_calls, list):
        raise ValueError("tool_calls must be a list")
    summaries = []
    for tool in tool_calls:
        if not isinstance(tool, Mapping):
            raise ValueError("tool call must be a mapping")
        summaries.append(ToolSummary(str(tool.get("name", "")), str(tool.get("status", ""))))
    if not isinstance(model_version, Mapping) or not all(isinstance(key, str) and isinstance(value, str) for key, value in model_version.items()):
        raise ValueError("model_version must be a string mapping")
    version_fingerprints = {key: VersionFingerprint(value, hash_key) for key, value in model_version.items()}
    return TelemetryTrace(
        trace_id, application, datetime.now(timezone.utc), fingerprint(request_text, hash_key), fingerprint(answer_text, hash_key),
        len(request_text), len(answer_text), fingerprint(user_id, hash_key), fingerprint(session_id, hash_key), tuple(summaries),
        sanitize_metadata(metadata), dict(usage), None if cost is None else dict(cost), version_fingerprints, dict(latency),
    )


@dataclass(frozen=True)
class TelemetryQuery:
    application: str = ""
    trace_id: str = ""

    def __post_init__(self) -> None:
        if not self.application and not self.trace_id:
            raise ValueError("a telemetry query needs a filter")

    def as_dict(self) -> dict[str, str]:
        return {key: value for key, value in {"application": self.application, "trace_id": self.trace_id}.items() if value}
