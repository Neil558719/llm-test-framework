from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from .redaction import assert_sanitized_payload, fingerprint, sanitize_metadata


def _nonempty(name: str, value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be nonempty")


def _number(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return float(value)


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
    model_version: Mapping[str, str] = field(default_factory=dict)
    latency: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("trace_id", "application", "request_fingerprint", "answer_fingerprint", "user_fingerprint", "session_fingerprint"):
            _nonempty(name, getattr(self, name))
        _utc(self.timestamp)
        for name in ("request_length", "answer_length"):
            if isinstance(getattr(self, name), bool) or not isinstance(getattr(self, name), int) or getattr(self, name) < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        for name, value in self.usage.items():
            _number(f"usage.{name}", value)
        if self.cost is not None:
            for name, value in self.cost.items():
                if name in {"input", "output", "total"}:
                    _number(f"cost.{name}", value)
        for name, value in self.latency.items():
            if name.endswith("_ms"):
                _number(f"latency.{name}", value)
        assert_sanitized_payload(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id, "application": self.application, "timestamp": _timestamp(self.timestamp),
            "request_fingerprint": self.request_fingerprint, "answer_fingerprint": self.answer_fingerprint,
            "request_length": self.request_length, "answer_length": self.answer_length,
            "source": {"user_fingerprint": self.user_fingerprint, "session_fingerprint": self.session_fingerprint},
            "tool_calls": [tool.as_dict() for tool in self.tool_calls], "metadata": dict(self.metadata),
            "usage": dict(self.usage), "cost": None if self.cost is None else dict(self.cost),
            "model_version": dict(self.model_version), "latency": dict(self.latency),
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
    return TelemetryTrace(
        trace_id, application, datetime.now(timezone.utc), fingerprint(request_text, hash_key), fingerprint(answer_text, hash_key),
        len(request_text), len(answer_text), fingerprint(user_id, hash_key), fingerprint(session_id, hash_key), tuple(summaries),
        sanitize_metadata(metadata), dict(usage), None if cost is None else dict(cost), dict(model_version), dict(latency),
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
