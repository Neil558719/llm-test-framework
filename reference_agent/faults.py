"""Authenticated, request-scoped fault primitives for test deployments."""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from hmac import compare_digest
from typing import Any, Mapping

from .services.common import ServiceError


_SIMPLE_TYPES = {
    "model_timeout",
    "model_429",
    "knowledge_unavailable",
    "sse_interruption",
    "database_error",
}
_TOOL_TARGETS = {"user", "asset", "ticket", "approval"}


class FaultControlError(RuntimeError):
    """A client-visible fault-control validation or authorization error."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class InjectedDatabaseError(RuntimeError):
    """A controlled database failure raised before a real transaction starts."""


class ModelRateLimitError(RuntimeError):
    """A controlled model-provider rate-limit response."""

    status_code = 429


@dataclass(frozen=True)
class FaultProfile:
    """Validated fault behavior for one chat request."""

    type: str
    target: str = ""
    status_code: int | None = None
    delay_seconds: float = 0.0

    @classmethod
    def from_json(cls, raw_fault: str) -> "FaultProfile":
        try:
            payload = json.loads(raw_fault)
        except (json.JSONDecodeError, TypeError) as exc:
            raise FaultControlError(400, "X-QE-Fault must contain valid JSON") from exc
        if not isinstance(payload, Mapping):
            raise FaultControlError(400, "X-QE-Fault must be a JSON object")
        if not all(isinstance(key, str) for key in payload):
            raise FaultControlError(400, "fault profile keys must be strings")

        fault_type = payload.get("type")
        if not isinstance(fault_type, str):
            raise FaultControlError(400, "fault type must be a string")
        supported = _SIMPLE_TYPES | {"downstream_5xx", "tool_slow_response"}
        if fault_type not in supported:
            raise FaultControlError(400, f"unsupported fault type: {fault_type}")

        allowed = {"type"}
        if fault_type == "downstream_5xx":
            allowed |= {"target", "status_code"}
        elif fault_type == "tool_slow_response":
            allowed |= {"target", "delay_seconds"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            if fault_type in _SIMPLE_TYPES:
                raise FaultControlError(
                    400,
                    f"unknown parameters are not allowed for {fault_type}: {', '.join(unknown)}",
                )
            raise FaultControlError(400, f"unknown fault profile fields: {', '.join(unknown)}")

        if fault_type in _SIMPLE_TYPES:
            return cls(type=fault_type)

        target = payload.get("target")
        if not isinstance(target, str) or target not in _TOOL_TARGETS:
            raise FaultControlError(
                400,
                f"target must be one of: {', '.join(sorted(_TOOL_TARGETS))}",
            )

        if fault_type == "downstream_5xx":
            status_code = payload.get("status_code", 503)
            if (
                isinstance(status_code, bool)
                or not isinstance(status_code, int)
                or not 500 <= status_code <= 599
            ):
                raise FaultControlError(400, "status_code must be an integer from 500 to 599")
            return cls(type=fault_type, target=target, status_code=status_code)

        delay_seconds = payload.get("delay_seconds")
        if (
            isinstance(delay_seconds, bool)
            or not isinstance(delay_seconds, (int, float))
            or not math.isfinite(float(delay_seconds))
            or not 0 < float(delay_seconds) <= 5
        ):
            raise FaultControlError(400, "delay_seconds must be greater than 0 and at most 5")
        return cls(
            type=fault_type,
            target=target,
            delay_seconds=float(delay_seconds),
        )

    def before_database(self) -> None:
        if self.type == "database_error":
            raise InjectedDatabaseError("injected database_error before session write")

    def before_model(self) -> None:
        if self.type == "model_timeout":
            raise TimeoutError("injected model_timeout")
        if self.type == "model_429":
            raise ModelRateLimitError("injected model_429")

    def before_service(self, name: str) -> None:
        if self.type == "knowledge_unavailable" and name == "knowledge":
            raise ServiceError(503, "injected knowledge_unavailable")
        if self.type == "downstream_5xx" and name == self.target:
            raise ServiceError(
                int(self.status_code or 503),
                f"injected downstream_5xx for {name}",
            )
        if self.type == "tool_slow_response" and name == self.target:
            time.sleep(self.delay_seconds)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": self.type}
        if self.target:
            payload["target"] = self.target
        if self.status_code is not None:
            payload["status_code"] = self.status_code
        if self.delay_seconds:
            payload["delay_seconds"] = self.delay_seconds
        return payload


@dataclass(frozen=True)
class FaultControlSettings:
    """Server-side authorization settings for test fault requests."""

    enabled: bool = False
    token: str = ""

    @classmethod
    def from_env(cls) -> "FaultControlSettings":
        enabled = os.getenv("REFERENCE_AGENT_TEST_FAULTS_ENABLED", "").strip().lower()
        is_enabled = enabled in {"1", "true", "yes", "on"}
        token = os.getenv("REFERENCE_AGENT_TEST_FAULT_TOKEN", "").strip()
        if is_enabled and not token:
            raise RuntimeError(
                "REFERENCE_AGENT_TEST_FAULT_TOKEN must be configured when test faults are enabled"
            )
        return cls(enabled=is_enabled, token=token)

    def resolve(
        self,
        token: str | None,
        raw_fault: str | None,
    ) -> FaultProfile | None:
        if raw_fault is None:
            return None
        if (
            not self.enabled
            or not token
            or not self.token
            or not compare_digest(token, self.token)
        ):
            raise FaultControlError(403, "test fault credentials rejected")
        return FaultProfile.from_json(raw_fault)
