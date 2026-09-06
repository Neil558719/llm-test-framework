from __future__ import annotations

import json
from dataclasses import replace

from qe_platform.loadtest.gate_models import (
    FaultSpec,
    GateCheck,
    GateExecutionError,
    GateScenarioConfig,
    GateScenarioResult,
    GateSuiteConfig,
    GateSuiteResult,
    GateThresholds,
    SampleExpectation,
)
from qe_platform.loadtest.gate_reporting import write_gate_reports
from qe_platform.loadtest.metrics import summarize
from qe_platform.loadtest.models import LoadTestConfig, LoadTestRun, SampleResult


def gate_result(tmp_path, *, passed: bool = False) -> GateSuiteResult:
    load = LoadTestConfig(
        target_url="http://test?api_key=query-secret",
        requests=1,
        message="private incident text",
        headers={
            "X-QE-Test-Token": "top-secret",
            "X-QE-Fault": '{"type":"model_timeout"}',
        },
        json_report="",
        html_report="",
    )
    fault_sample = SampleResult(
        True,
        120,
        None,
        status_code=200,
        trace_id="fault-trace",
        observations={"fallback_reason": "TimeoutError"},
    )
    recovery_sample = SampleResult(
        True,
        80,
        None,
        status_code=200,
        trace_id="recovery-trace",
        observations={"knowledge_status": "answered"},
    )
    fault_run = LoadTestRun(
        load,
        "fault-start",
        "fault-finish",
        [fault_sample],
        summarize([fault_sample], load, wall_time_ms=120),
    )
    recovery_load = LoadTestConfig(
        target_url="http://test?api_key=query-secret",
        requests=1,
        message="private incident text",
        json_report="",
        html_report="",
    )
    recovery_run = LoadTestRun(
        recovery_load,
        "recovery-start",
        "recovery-finish",
        [recovery_sample],
        summarize([recovery_sample], recovery_load, wall_time_ms=80),
    )
    thresholds = GateThresholds(max_latency_p95_ms=100)
    scenario_config = GateScenarioConfig(
        id="model-timeout",
        load=recovery_load,
        fault=FaultSpec("model_timeout"),
        expect=SampleExpectation(fallback_reason="TimeoutError"),
        recovery=True,
        recovery_expect=SampleExpectation(knowledge_status="answered"),
        thresholds=thresholds,
    )
    suite = GateSuiteConfig(
        id="m13",
        target_url="http://test?api_key=query-secret",
        fault_token_env="M13_TOKEN",
        json_report=str(tmp_path / "m13.json"),
        html_report=str(tmp_path / "m13.html"),
        thresholds=thresholds,
        scenarios=[scenario_config],
    )
    check = GateCheck(
        name="max_latency_p95_ms",
        stage="recovery",
        operator="<=",
        expected=100.0,
        actual=80.0 if passed else 120.0,
        unit="ms",
        passed=passed,
        reason="within limit" if passed else "actual 120 violates <= 100",
    )
    scenario = GateScenarioResult(
        scenario_id="model-timeout",
        fault_type="model_timeout",
        fault_run=fault_run,
        recovery_run=recovery_run,
        checks=[check],
    )
    return GateSuiteResult(suite, "suite-start", "suite-finish", [scenario])


def test_gate_reports_include_fault_recovery_checks_and_samples(tmp_path):
    result = gate_result(tmp_path)

    json_path, html_path = write_gate_reports(result)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    html = html_path.read_text(encoding="utf-8")
    assert payload["gate_passed"] is False
    assert payload["failed_checks"] == 1
    assert payload["scenarios"][0]["fault_type"] == "model_timeout"
    assert payload["scenarios"][0]["fault_run"]["summary"]["completed"] == 1
    assert payload["scenarios"][0]["recovery_run"]["summary"]["completed"] == 1
    assert payload["scenarios"][0]["checks"][0] == {
        "name": "max_latency_p95_ms",
        "stage": "recovery",
        "operator": "<=",
        "expected": 100.0,
        "actual": 120.0,
        "unit": "ms",
        "passed": False,
        "reason": "actual 120 violates <= 100",
    }
    for expected in (
        "M13 Quality Gate",
        "model-timeout",
        "model_timeout",
        "Fault phase",
        "Recovery phase",
        "max_latency_p95_ms",
        "fault-trace",
        "recovery-trace",
        "FAILED",
    ):
        assert expected in html


def test_gate_reports_do_not_leak_message_token_or_raw_fault_header(tmp_path):
    result = gate_result(tmp_path)

    json_path, html_path = write_gate_reports(result)

    combined = json_path.read_text(encoding="utf-8") + html_path.read_text(
        encoding="utf-8"
    )
    assert "private incident text" not in combined
    assert "top-secret" not in combined
    assert "query-secret" not in combined
    assert '{"type":"model_timeout"}' not in combined
    assert "[REDACTED]" in combined


def test_gate_reports_separate_phase_execution_errors(tmp_path):
    result = gate_result(tmp_path, passed=True)
    scenario = replace(
        result.scenarios[0],
        execution_errors=[GateExecutionError("fault", "RuntimeError")],
    )
    result = replace(result, scenarios=[scenario])

    json_path, html_path = write_gate_reports(result)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    html = html_path.read_text(encoding="utf-8")
    assert payload["execution_error_count"] == 1
    assert payload["scenarios"][0]["execution_errors"] == [
        {"stage": "fault", "error_type": "RuntimeError"}
    ]
    assert "Execution errors" in html
    assert "RuntimeError" in html
