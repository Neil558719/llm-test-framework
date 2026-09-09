from __future__ import annotations

import json

import pytest

from qe_platform.quality_loop.models import ReleaseGatePolicy, parse_run_report
from qe_platform.reporting import RunReport


def _report_payload(**overrides):
    payload = {
        "run_id": "run-candidate",
        "started_at": "2026-09-09T00:00:00Z",
        "finished_at": "2026-09-09T00:00:02Z",
        "application": "reference-agent",
        "release_id": "alpha-23",
        "version": "8ce8a5f",
        "environment": "offline",
        "total": 2,
        "passed": 2,
        "failed": 0,
        "gate_passed": True,
        "scenarios": [
            {
                "scenario_id": "vpn-recovery-regression",
                "passed": True,
                "complete": True,
                "steps": [],
                "usage": {"total_tokens": 12},
                "cost": {"total": 0.12, "currency": "USD"},
                "latency_ms": 120,
            },
            {
                "scenario_id": "ticket-create-vpn",
                "passed": True,
                "complete": True,
                "steps": [],
                "usage": {"total_tokens": 8},
                "cost": {"total": 0.08, "currency": "USD"},
                "latency_ms": 80,
            },
        ],
    }
    payload.update(overrides)
    return payload


def test_run_report_metadata_is_optional_and_serialized():
    legacy = RunReport("legacy", "2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z", [])
    assert legacy.as_dict()["application"] == ""

    report = RunReport(
        "run-1",
        "2026-01-01T00:00:00Z",
        "2026-01-01T00:00:01Z",
        [],
        application="reference-agent",
        release_id="alpha-23",
        version="candidate",
        environment="offline",
    )
    serialized = report.as_dict()
    assert serialized["application"] == "reference-agent"
    assert serialized["release_id"] == "alpha-23"
    assert serialized["version"] == "candidate"
    assert serialized["environment"] == "offline"


def test_parse_run_report_calculates_counts_and_stable_scenario_ids():
    run = parse_run_report(_report_payload(), source_label="fixture")
    assert run.run_id == "run-candidate"
    assert run.total == 2
    assert run.passed == 2
    assert run.failed == 0
    assert run.scenario_ids == ("ticket-create-vpn", "vpn-recovery-regression")
    assert run.total_tokens == 20
    assert run.total_cost == pytest.approx(0.2)
    assert run.source_label == "fixture"


def test_parse_run_report_accepts_generated_rich_report_but_stores_only_aggregates():
    payload = _report_payload()
    payload["scenarios"][0]["steps"] = [{"response": {"answer": "raw answer must not persist"}, "user": "raw question"}]
    payload["scenarios"][0]["tool_calls"] = [{"name": "create_ticket", "arguments": {"secret": "private"}}]
    run = parse_run_report(payload, source_label="fixture")
    assert "raw answer" not in json.dumps(run.as_dict())


@pytest.mark.parametrize(
    "overrides",
    [
        {"run_id": ""},
        {"started_at": "not-a-timestamp"},
        {"total": 3},
        {"scenarios": [{"scenario_id": "secret", "request": "raw user question"}]},
        {"version": "Authorization: Bearer secret"},
    ],
)
def test_parse_run_report_rejects_invalid_or_sensitive_payloads(overrides):
    with pytest.raises(ValueError):
        parse_run_report(_report_payload(**overrides), source_label="fixture")


@pytest.mark.parametrize("value", [-0.1, "0", True])
def test_release_gate_policy_rejects_invalid_thresholds(value):
    with pytest.raises(ValueError):
        ReleaseGatePolicy(max_candidate_failure_rate=value)


def test_release_gate_policy_has_safe_defaults():
    policy = ReleaseGatePolicy()
    assert policy.max_candidate_failure_rate == 0.0
    assert policy.max_pass_rate_drop == 0.0
    assert policy.max_low_quality_rate_increase == 0.0
    assert policy.require_complete is True
