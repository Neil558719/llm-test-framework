"""Data contracts for fault, SLA/SLO, recovery, and cost gates."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

from .models import LoadTestConfig, LoadTestRun


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


_FAULT_TYPES = {
    "model_timeout",
    "model_429",
    "downstream_5xx",
    "tool_slow_response",
    "knowledge_unavailable",
    "sse_interruption",
    "database_error",
}
_TOOL_TARGETS = {"user", "asset", "ticket", "approval"}


@dataclass(frozen=True)
class FaultSpec:
    type: str
    target: str = ""
    status_code: Optional[int] = None
    delay_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.type, str) or self.type not in _FAULT_TYPES:
            raise ValueError(f"unsupported fault type: {self.type}")
        if self.type in {"downstream_5xx", "tool_slow_response"}:
            if self.target not in _TOOL_TARGETS:
                raise ValueError(
                    f"target must be one of: {', '.join(sorted(_TOOL_TARGETS))}"
                )
        elif self.target:
            raise ValueError(f"target is not allowed for {self.type}")
        if self.type == "downstream_5xx":
            value = 503 if self.status_code is None else self.status_code
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 500 <= value <= 599
            ):
                raise ValueError("status_code must be an integer from 500 to 599")
            object.__setattr__(self, "status_code", value)
        elif self.status_code is not None:
            raise ValueError(f"status_code is not allowed for {self.type}")
        if self.type == "tool_slow_response":
            if (
                isinstance(self.delay_seconds, bool)
                or not isinstance(self.delay_seconds, (int, float))
                or not math.isfinite(float(self.delay_seconds))
                or not 0 < float(self.delay_seconds) <= 5
            ):
                raise ValueError("delay_seconds must be greater than 0 and at most 5")
            object.__setattr__(self, "delay_seconds", float(self.delay_seconds))
        elif self.delay_seconds != 0:
            raise ValueError(f"delay_seconds is not allowed for {self.type}")

    def as_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"type": self.type}
        if self.target:
            value["target"] = self.target
        if self.status_code is not None:
            value["status_code"] = self.status_code
        if self.delay_seconds:
            value["delay_seconds"] = self.delay_seconds
        return value


@dataclass(frozen=True)
class GateScenarioConfig:
    id: str
    load: LoadTestConfig
    fault: FaultSpec
    expect: SampleExpectation
    recovery: bool = True
    recovery_expect: SampleExpectation = field(
        default_factory=lambda: SampleExpectation(success=True, status_code=200)
    )
    thresholds: GateThresholds = field(default_factory=GateThresholds)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("scenario id must be a non-empty string")
        if not isinstance(self.recovery, bool):
            raise ValueError("recovery must be a boolean")
        if self.fault.type == "sse_interruption" and self.load.protocol != "sse":
            raise ValueError("sse_interruption requires protocol 'sse'")


@dataclass(frozen=True)
class GateSuiteConfig:
    id: str
    target_url: str
    fault_token_env: str
    json_report: str
    html_report: str
    thresholds: GateThresholds
    scenarios: list[GateScenarioConfig]

    def as_public_dict(self) -> dict[str, Any]:
        public_target = (
            self.scenarios[0].load.as_public_dict()["target_url"]
            if self.scenarios
            else "[UNAVAILABLE]"
        )
        return {
            "id": self.id,
            "target_url": public_target,
            "fault_token_env": self.fault_token_env,
            "reports": {"json": self.json_report, "html": self.html_report},
            "thresholds": self.thresholds.as_dict(),
            "scenario_ids": [scenario.id for scenario in self.scenarios],
        }


@dataclass(frozen=True)
class GateScenarioResult:
    scenario_id: str
    fault_type: str
    fault_run: LoadTestRun
    recovery_run: Optional[LoadTestRun]
    checks: list[GateCheck]

    @property
    def gate_passed(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)

    @property
    def failed_checks(self) -> int:
        return sum(not check.passed for check in self.checks)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "fault_type": self.fault_type,
            "gate_passed": self.gate_passed,
            "failed_checks": self.failed_checks,
            "fault_run": self.fault_run.as_dict(),
            "recovery_run": (
                self.recovery_run.as_dict() if self.recovery_run is not None else None
            ),
            "checks": [check.as_dict() for check in self.checks],
        }


@dataclass(frozen=True)
class GateSuiteResult:
    config: GateSuiteConfig
    started_at: str
    finished_at: str
    scenarios: list[GateScenarioResult]

    @property
    def gate_passed(self) -> bool:
        return bool(self.scenarios) and all(item.gate_passed for item in self.scenarios)

    @property
    def failed_checks(self) -> int:
        return sum(item.failed_checks for item in self.scenarios)

    @property
    def passed_scenarios(self) -> int:
        return sum(item.gate_passed for item in self.scenarios)

    def as_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.as_public_dict(),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_scenarios": len(self.scenarios),
            "passed_scenarios": self.passed_scenarios,
            "failed_scenarios": len(self.scenarios) - self.passed_scenarios,
            "failed_checks": self.failed_checks,
            "gate_passed": self.gate_passed,
            "scenarios": [scenario.as_dict() for scenario in self.scenarios],
        }
