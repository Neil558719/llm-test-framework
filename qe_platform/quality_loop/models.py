from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from qe_platform.telemetry.redaction import assert_sanitized_payload


def _text(value: Any, name: str, *, required: bool = True) -> str:
    if not isinstance(value, str) or (required and not value) or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be a safe nonempty string" if required else f"{name} must be a safe string")
    return value


def _utc(value: Any, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be an ISO-8601 UTC timestamp")
    return parsed.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _number(value: Any, name: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) < minimum:
        raise ValueError(f"{name} must be a finite number >= {minimum}")
    return float(value)


def _count(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _rate(value: Any, name: str) -> float:
    value = _number(value, name)
    if value > 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return value


@dataclass(frozen=True, slots=True)
class OfflineRun:
    run_id: str
    application: str
    release_id: str
    version: str
    environment: str
    source_label: str
    started_at: str
    finished_at: str
    total: int
    passed: int
    failed: int
    gate_passed: bool
    p95_latency_ms: float | None
    total_tokens: int
    total_cost: float
    scenario_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("run_id", "application", "release_id", "version", "environment", "source_label"):
            _text(getattr(self, name), name)
        start = _utc(self.started_at, "started_at")
        finish = _utc(self.finished_at, "finished_at")
        if finish < start:
            raise ValueError("finished_at must not precede started_at")
        total, passed, failed = (_count(getattr(self, name), name) for name in ("total", "passed", "failed"))
        if passed + failed != total:
            raise ValueError("passed + failed must equal total")
        if not isinstance(self.gate_passed, bool):
            raise ValueError("gate_passed must be boolean")
        if self.p95_latency_ms is not None:
            _number(self.p95_latency_ms, "p95_latency_ms")
        _count(self.total_tokens, "total_tokens")
        _number(self.total_cost, "total_cost")
        if not isinstance(self.scenario_ids, tuple) or not self.scenario_ids or len(set(self.scenario_ids)) != len(self.scenario_ids):
            raise ValueError("scenario_ids must be a nonempty tuple of unique IDs")
        if tuple(sorted(self.scenario_ids)) != self.scenario_ids or not all(isinstance(item, str) and item for item in self.scenario_ids):
            raise ValueError("scenario_ids must be sorted nonempty strings")

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "application": self.application,
            "release_id": self.release_id,
            "version": self.version,
            "environment": self.environment,
            "source_label": self.source_label,
            "started_at": _timestamp(_utc(self.started_at, "started_at")),
            "finished_at": _timestamp(_utc(self.finished_at, "finished_at")),
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "gate_passed": self.gate_passed,
            "p95_latency_ms": self.p95_latency_ms,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "scenario_ids": list(self.scenario_ids),
        }


@dataclass(frozen=True, slots=True)
class QualityLink:
    link_id: str
    trace_id: str
    feedback_id: str
    review_id: str
    promotion_id: str
    scenario_id: str
    offline_run_id: str
    created_at: str

    def __post_init__(self) -> None:
        for name in ("link_id", "trace_id", "feedback_id", "review_id", "promotion_id", "scenario_id", "offline_run_id"):
            _text(getattr(self, name), name)
        _utc(self.created_at, "created_at")

    def as_dict(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in ("link_id", "trace_id", "feedback_id", "review_id", "promotion_id", "scenario_id", "offline_run_id", "created_at")}


@dataclass(frozen=True, slots=True)
class TrendPoint:
    bucket: str
    application: str
    version: str
    online_trace_count: int
    feedback_count: int
    confirmed_low_quality_count: int
    low_quality_rate: float | None
    offline_run_count: int
    offline_pass_rate: float | None
    p95_latency_ms: float | None
    total_tokens: int
    total_cost: float

    def as_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class ReleaseGatePolicy:
    max_candidate_failure_rate: float = 0.0
    max_pass_rate_drop: float = 0.0
    max_low_quality_rate_increase: float = 0.0
    require_complete: bool = True
    application: str = ""
    release_id: str = ""

    def __post_init__(self) -> None:
        for name in ("max_candidate_failure_rate", "max_pass_rate_drop", "max_low_quality_rate_increase"):
            _rate(getattr(self, name), name)
        if not isinstance(self.require_complete, bool):
            raise ValueError("require_complete must be boolean")
        _text(self.application, "application", required=False)
        _text(self.release_id, "release_id", required=False)

    def as_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class ReleaseCheck:
    name: str
    actual: Any
    threshold: Any
    passed: bool
    message: str

    def __post_init__(self) -> None:
        _text(self.name, "name")
        if not isinstance(self.passed, bool):
            raise ValueError("passed must be boolean")
        _text(self.message, "message", required=False)

    def as_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class ReleaseValidation:
    validation_id: str
    baseline_run_id: str
    candidate_run_id: str
    policy: ReleaseGatePolicy
    passed: bool
    checks: tuple[ReleaseCheck, ...]
    linked_count: int
    created_at: str

    def __post_init__(self) -> None:
        for name in ("validation_id", "baseline_run_id", "candidate_run_id"):
            _text(getattr(self, name), name)
        if not isinstance(self.policy, ReleaseGatePolicy) or not isinstance(self.passed, bool):
            raise ValueError("invalid release validation policy or status")
        if not isinstance(self.checks, tuple) or not self.checks or not all(isinstance(item, ReleaseCheck) for item in self.checks):
            raise ValueError("checks must be a nonempty tuple of ReleaseCheck")
        _count(self.linked_count, "linked_count")
        _utc(self.created_at, "created_at")

    def as_dict(self) -> dict[str, Any]:
        return {
            "validation_id": self.validation_id,
            "baseline_run_id": self.baseline_run_id,
            "candidate_run_id": self.candidate_run_id,
            "policy": self.policy.as_dict(),
            "passed": self.passed,
            "checks": [item.as_dict() for item in self.checks],
            "linked_count": self.linked_count,
            "created_at": self.created_at,
        }


def _scenario_values(payload: Mapping[str, Any]) -> tuple[list[Mapping[str, Any]], tuple[str, ...]]:
    values = payload.get("scenarios")
    if not isinstance(values, list) or not values:
        raise ValueError("scenarios must be a nonempty list")
    rows: list[Mapping[str, Any]] = []
    ids: list[str] = []
    for item in values:
        if not isinstance(item, Mapping):
            raise ValueError("scenario entries must be mappings")
        scenario_id = _text(item.get("scenario_id"), "scenario_id")
        if scenario_id in ids:
            raise ValueError("scenario IDs must be unique")
        ids.append(scenario_id)
        rows.append(item)
    return rows, tuple(sorted(ids))


def parse_run_report(payload: Mapping[str, Any], source_label: str) -> OfflineRun:
    if not isinstance(payload, Mapping):
        raise ValueError("run report must be a mapping")
    assert_sanitized_payload(payload)
    required = ("run_id", "started_at", "finished_at", "application", "release_id", "version", "environment", "total", "passed", "failed", "gate_passed", "scenarios")
    if any(key not in payload for key in required):
        raise ValueError("run report is missing required fields")
    rows, scenario_ids = _scenario_values(payload)
    total = _count(payload["total"], "total")
    passed = _count(payload["passed"], "passed")
    failed = _count(payload["failed"], "failed")
    if total != len(rows) or passed != sum(item.get("passed") is True for item in rows) or failed != total - passed:
        raise ValueError("run report counts do not match scenarios")
    latencies = [_number(item["latency_ms"], "latency_ms") for item in rows if "latency_ms" in item]
    latencies.sort()
    p95 = None if not latencies else latencies[min(len(latencies) - 1, math.ceil(len(latencies) * 0.95) - 1)]
    tokens = 0
    cost = 0.0
    for item in rows:
        usage = item.get("usage") or {}
        if not isinstance(usage, Mapping):
            raise ValueError("scenario usage must be a mapping")
        tokens += _count(usage.get("total_tokens", int(usage.get("prompt_tokens", 0)) + int(usage.get("completion_tokens", 0))), "total_tokens")
        value = item.get("cost") or {}
        if not isinstance(value, Mapping):
            raise ValueError("scenario cost must be a mapping")
        cost += _number(value.get("total", 0), "cost.total")
    return OfflineRun(
        run_id=_text(payload["run_id"], "run_id"),
        application=_text(payload["application"], "application"),
        release_id=_text(payload["release_id"], "release_id"),
        version=_text(payload["version"], "version"),
        environment=_text(payload["environment"], "environment"),
        source_label=_text(source_label, "source_label"),
        started_at=_timestamp(_utc(payload["started_at"], "started_at")),
        finished_at=_timestamp(_utc(payload["finished_at"], "finished_at")),
        total=total,
        passed=passed,
        failed=failed,
        gate_passed=payload["gate_passed"] if isinstance(payload["gate_passed"], bool) else (_ for _ in ()).throw(ValueError("gate_passed must be boolean")),
        p95_latency_ms=p95,
        total_tokens=tokens,
        total_cost=cost,
        scenario_ids=scenario_ids,
    )
