from __future__ import annotations

from dataclasses import replace

import pytest

from qe_platform.loadtest.gate_models import GateThresholds, SampleExpectation
from qe_platform.loadtest.gates import evaluate_samples, evaluate_thresholds
from qe_platform.loadtest.models import LoadTestSummary, SampleResult


def _summary(**changes) -> LoadTestSummary:
    base = LoadTestSummary(
        requested=4,
        completed=4,
        succeeded=4,
        failed=0,
        wall_time_ms=1000,
        throughput_rps=4.0,
        error_rate=0.0,
        rate_429=0.0,
        stream_interruption_rate=0.0,
        latency_ms={"p50": 50.0, "p95": 100.0, "p99": 120.0},
        ttft_ms={"p50": 10.0, "p95": 20.0, "p99": 25.0},
        status_codes={"200": 4},
        errors={},
        prompt_tokens=40,
        completion_tokens=20,
        total_tokens=60,
        cost_total=0.4,
        cost_currency="USD",
        price_version="p1",
    )
    return replace(base, **changes)


def test_thresholds_accept_every_exact_boundary():
    checks = evaluate_thresholds(
        _summary(),
        GateThresholds(
            max_error_rate=0.0,
            max_429_rate=0.0,
            max_stream_interruption_rate=0.0,
            max_latency_p95_ms=100.0,
            max_ttft_p95_ms=20.0,
            min_throughput_rps=4.0,
            max_cost_total=0.4,
            max_cost_per_success=0.1,
        ),
        "recovery",
    )

    assert len(checks) == 8
    assert all(check.passed for check in checks)
    assert {check.stage for check in checks} == {"recovery"}


@pytest.mark.parametrize(
    "thresholds,summary,check_name",
    [
        (GateThresholds(max_error_rate=0.1), _summary(error_rate=0.11), "max_error_rate"),
        (GateThresholds(max_429_rate=0.1), _summary(rate_429=0.11), "max_429_rate"),
        (
            GateThresholds(max_stream_interruption_rate=0.1),
            _summary(stream_interruption_rate=0.11),
            "max_stream_interruption_rate",
        ),
        (
            GateThresholds(max_latency_p95_ms=99),
            _summary(),
            "max_latency_p95_ms",
        ),
        (
            GateThresholds(max_ttft_p95_ms=19),
            _summary(),
            "max_ttft_p95_ms",
        ),
        (
            GateThresholds(min_throughput_rps=4.1),
            _summary(),
            "min_throughput_rps",
        ),
        (GateThresholds(max_cost_total=0.39), _summary(), "max_cost_total"),
        (
            GateThresholds(max_cost_per_success=0.09),
            _summary(),
            "max_cost_per_success",
        ),
    ],
)
def test_each_threshold_fails_on_the_wrong_side(thresholds, summary, check_name):
    checks = evaluate_thresholds(summary, thresholds, "fault")

    assert len(checks) == 1
    assert checks[0].name == check_name
    assert checks[0].passed is False
    assert checks[0].actual is not None


def test_configured_missing_ttft_and_cost_metrics_fail_closed():
    checks = evaluate_thresholds(
        _summary(
            succeeded=0,
            ttft_ms={"p50": None, "p95": None, "p99": None},
            cost_total=None,
            cost_currency="MIXED",
        ),
        GateThresholds(max_ttft_p95_ms=50, max_cost_total=1, max_cost_per_success=1),
        "fault",
    )

    assert len(checks) == 3
    assert all(check.passed is False for check in checks)
    assert all(check.actual is None for check in checks)
    assert all("unavailable" in check.reason for check in checks)


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"max_error_rate": -0.1}, "max_error_rate"),
        ({"max_429_rate": 1.1}, "max_429_rate"),
        ({"max_stream_interruption_rate": float("nan")}, "max_stream_interruption_rate"),
        ({"max_latency_p95_ms": -1}, "max_latency_p95_ms"),
        ({"max_ttft_p95_ms": True}, "max_ttft_p95_ms"),
        ({"min_throughput_rps": -1}, "min_throughput_rps"),
        ({"max_cost_total": -0.01}, "max_cost_total"),
        ({"max_cost_per_success": "cheap"}, "max_cost_per_success"),
    ],
)
def test_threshold_models_reject_invalid_ranges_and_types(kwargs, match):
    with pytest.raises(ValueError, match=match):
        GateThresholds(**kwargs)


def test_sample_expectations_check_all_samples_and_allowed_observations():
    samples = [
        SampleResult(
            True,
            55,
            None,
            status_code=200,
            observations={
                "fallback_reason": "TimeoutError",
                "knowledge_status": "answered",
                "ticket_status": "",
                "approval_status": "",
                "source_count": 1,
                "failed_tool_count": 0,
            },
        ),
        SampleResult(
            True,
            60,
            None,
            status_code=200,
            observations={
                "fallback_reason": "TimeoutError",
                "knowledge_status": "answered",
                "ticket_status": "",
                "approval_status": "",
                "source_count": 1,
                "failed_tool_count": 0,
            },
        ),
    ]
    expectation = SampleExpectation(
        success=True,
        status_code=200,
        fallback_reason="TimeoutError",
        knowledge_status="answered",
        source_count=1,
        min_failed_tools=0,
        min_duration_ms=50,
    )

    checks = evaluate_samples(samples, expectation, "fault")

    assert len(checks) == 7
    assert all(check.passed for check in checks)


def test_sample_expectation_reports_mixed_values_as_failure():
    samples = [
        SampleResult(False, 10, None, status_code=503, error_type="http_error"),
        SampleResult(False, 12, None, status_code=500, error_type="http_error"),
    ]

    checks = evaluate_samples(
        samples,
        SampleExpectation(success=False, status_code=503, error_type="http_error"),
        "fault",
    )

    assert [check.passed for check in checks] == [True, False, True]
    assert checks[1].actual == [500, 503]


def test_sample_expectation_fails_when_no_samples_exist():
    checks = evaluate_samples([], SampleExpectation(success=True), "recovery")

    assert len(checks) == 1
    assert checks[0].passed is False
    assert checks[0].actual is None
    assert "no samples" in checks[0].reason
