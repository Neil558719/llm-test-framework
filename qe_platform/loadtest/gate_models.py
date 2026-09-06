"""Data contracts for fault, SLA/SLO, recovery, and cost gates."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional


def _number(name: str, value: Any, *, maximum: float | None = None) -> None:
    if value is None:
        return
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0
        or (maximum is not None and float(value) > maximum)
    ):
        suffix = f" between 0 and {maximum:g}" if maximum is not None else " non-negative"
        raise ValueError(f"{name} must be{suffix}")


@dataclass(frozen=True)
class GateThresholds:
    max_error_rate: Optional[float] = None
    max_429_rate: Optional[float] = None
    max_stream_interruption_rate: Optional[float] = None
    max_latency_p95_ms: Optional[float] = None
    max_ttft_p95_ms: Optional[float] = None
    min_throughput_rps: Optional[float] = None
    max_cost_total: Optional[float] = None
    max_cost_per_success: Optional[float] = None

    def __post_init__(self) -> None:
        for name in (
            "max_error_rate",
            "max_429_rate",
            "max_stream_interruption_rate",
        ):
            _number(name, getattr(self, name), maximum=1)
        for name in (
            "max_latency_p95_ms",
            "max_ttft_p95_ms",
            "min_throughput_rps",
            "max_cost_total",
            "max_cost_per_success",
        ):
            _number(name, getattr(self, name))

    def as_dict(self) -> dict[str, float]:
        return {
            name: float(value)
            for name, value in vars(self).items()
            if value is not None
        }


@dataclass(frozen=True)
class SampleExpectation:
    success: Optional[bool] = None
    status_code: Optional[int] = None
    error_type: Optional[str] = None
    fallback_reason: Optional[str] = None
    knowledge_status: Optional[str] = None
    ticket_status: Optional[str] = None
    approval_status: Optional[str] = None
    source_count: Optional[int] = None
    min_failed_tools: Optional[int] = None
    min_duration_ms: Optional[float] = None

    def __post_init__(self) -> None:
        if self.success is not None and not isinstance(self.success, bool):
            raise ValueError("success must be a boolean")
        if self.status_code is not None and (
            isinstance(self.status_code, bool)
            or not isinstance(self.status_code, int)
            or not 100 <= self.status_code <= 599
        ):
            raise ValueError("status_code must be an integer from 100 to 599")
        for name in (
            "error_type",
            "fallback_reason",
            "knowledge_status",
            "ticket_status",
            "approval_status",
        ):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{name} must be a string")
        for name in ("source_count", "min_failed_tools"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{name} must be a non-negative integer")
        _number("min_duration_ms", self.min_duration_ms)

    def as_dict(self) -> dict[str, Any]:
        return {name: value for name, value in vars(self).items() if value is not None}


@dataclass(frozen=True)
class GateCheck:
    name: str
    stage: str
    operator: str
    expected: Any
    actual: Any
    unit: str
    passed: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "stage": self.stage,
            "operator": self.operator,
            "expected": self.expected,
            "actual": self.actual,
            "unit": self.unit,
            "passed": self.passed,
            "reason": self.reason,
        }
