"""Pure evaluators for load-test thresholds and sample expectations."""

from __future__ import annotations

from typing import Any, Callable, Iterable

from .gate_models import GateCheck, GateThresholds, SampleExpectation
from .models import LoadTestSummary, SampleResult


def _metric_check(
    name: str,
    stage: str,
    operator: str,
    expected: float,
    actual: float | None,
    unit: str,
    compare: Callable[[float, float], bool],
) -> GateCheck:
    if actual is None:
        return GateCheck(
            name,
            stage,
            operator,
            expected,
            None,
            unit,
            False,
            "configured metric is unavailable",
        )
    passed = compare(float(actual), float(expected))
    return GateCheck(
        name,
        stage,
        operator,
        expected,
        actual,
        unit,
        passed,
        f"actual {actual} {operator} expected {expected}" if passed else f"actual {actual} violates {operator} {expected}",
    )


def evaluate_thresholds(
    summary: LoadTestSummary,
    thresholds: GateThresholds,
    stage: str,
) -> list[GateCheck]:
    cost_per_success = (
        summary.cost_total / summary.succeeded
        if summary.cost_total is not None and summary.succeeded > 0
        else None
    )
    metrics: dict[str, tuple[float | None, str, str, Callable[[float, float], bool]]] = {
        "max_error_rate": (summary.error_rate, "ratio", "<=", lambda actual, limit: actual <= limit),
        "max_429_rate": (summary.rate_429, "ratio", "<=", lambda actual, limit: actual <= limit),
        "max_stream_interruption_rate": (
            summary.stream_interruption_rate,
            "ratio",
            "<=",
            lambda actual, limit: actual <= limit,
        ),
        "max_latency_p95_ms": (
            summary.latency_ms.get("p95"),
            "ms",
            "<=",
            lambda actual, limit: actual <= limit,
        ),
        "max_ttft_p95_ms": (
            summary.ttft_ms.get("p95"),
            "ms",
            "<=",
            lambda actual, limit: actual <= limit,
        ),
        "min_throughput_rps": (
            summary.throughput_rps,
            "requests/s",
            ">=",
            lambda actual, limit: actual >= limit,
        ),
        "max_cost_total": (
            summary.cost_total,
            summary.cost_currency or "cost",
            "<=",
            lambda actual, limit: actual <= limit,
        ),
        "max_cost_per_success": (
            cost_per_success,
            f"{summary.cost_currency or 'cost'}/success",
            "<=",
            lambda actual, limit: actual <= limit,
        ),
    }
    checks = []
    for name, expected in vars(thresholds).items():
        if expected is None:
            continue
        actual, unit, operator, compare = metrics[name]
        checks.append(
            _metric_check(
                name,
                stage,
                operator,
                float(expected),
                actual,
                unit,
                compare,
            )
        )
    return checks


def _distinct(values: Iterable[Any]) -> list[Any]:
    unique: dict[str, Any] = {}
    for value in values:
        unique[repr(value)] = value
    return sorted(unique.values(), key=lambda value: repr(value))


def _sample_check(
    name: str,
    stage: str,
    operator: str,
    expected: Any,
    values: list[Any],
    compare: Callable[[Any, Any], bool],
    unit: str = "",
) -> GateCheck:
    if not values:
        return GateCheck(
            name,
            stage,
            operator,
            expected,
            None,
            unit,
            False,
            "no samples were produced",
        )
    passed = all(compare(value, expected) for value in values)
    distinct = _distinct(values)
    actual: Any = distinct[0] if len(distinct) == 1 else distinct
    return GateCheck(
        name,
        stage,
        operator,
        expected,
        actual,
        unit,
        passed,
        "all samples matched" if passed else "one or more samples did not match",
    )


def evaluate_samples(
    samples: Iterable[SampleResult],
    expectation: SampleExpectation,
    stage: str,
) -> list[GateCheck]:
    values = list(samples)
    checks: list[GateCheck] = []
    direct = {
        "success": lambda sample: sample.success,
        "status_code": lambda sample: sample.status_code,
        "error_type": lambda sample: sample.error_type,
    }
    observed = (
        "fallback_reason",
        "knowledge_status",
        "ticket_status",
        "approval_status",
        "source_count",
    )
    for name, getter in direct.items():
        expected = getattr(expectation, name)
        if expected is not None:
            checks.append(
                _sample_check(
                    name,
                    stage,
                    "all ==",
                    expected,
                    [getter(sample) for sample in values],
                    lambda actual, wanted: actual == wanted,
                )
            )
    for name in observed:
        expected = getattr(expectation, name)
        if expected is not None:
            checks.append(
                _sample_check(
                    name,
                    stage,
                    "all ==",
                    expected,
                    [sample.observations.get(name) for sample in values],
                    lambda actual, wanted: actual == wanted,
                )
            )
    if expectation.min_failed_tools is not None:
        checks.append(
            _sample_check(
                "min_failed_tools",
                stage,
                "all >=",
                expectation.min_failed_tools,
                [sample.observations.get("failed_tool_count") for sample in values],
                lambda actual, wanted: isinstance(actual, int) and actual >= wanted,
                "tools",
            )
        )
    if expectation.min_duration_ms is not None:
        checks.append(
            _sample_check(
                "min_duration_ms",
                stage,
                "all >=",
                expectation.min_duration_ms,
                [sample.duration_ms for sample in values],
                lambda actual, wanted: actual >= wanted,
                "ms",
            )
        )
    return checks
