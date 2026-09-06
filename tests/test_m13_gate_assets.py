from __future__ import annotations

from pathlib import Path

import yaml

from qe_platform.loadtest.gate_config import load_gate_config


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FAULTS = {
    "model_timeout",
    "model_429",
    "downstream_5xx",
    "tool_slow_response",
    "knowledge_unavailable",
    "sse_interruption",
    "database_error",
}


def test_fixed_gate_matrix_covers_every_required_fault_and_recovery():
    config = load_gate_config(ROOT / "configs/m13-reference-agent-gate.yaml")

    assert {scenario.fault.type for scenario in config.scenarios} == REQUIRED_FAULTS
    assert len(config.scenarios) == 7
    assert all(scenario.recovery for scenario in config.scenarios)
    assert all(scenario.recovery_expect.success is True for scenario in config.scenarios)
    assert all(scenario.recovery_expect.status_code == 200 for scenario in config.scenarios)
    assert all(scenario.thresholds.max_error_rate == 0 for scenario in config.scenarios)
    assert all(scenario.thresholds.max_cost_total == 0 for scenario in config.scenarios)


def test_fixed_gate_matrix_has_specific_observable_fault_outcomes():
    config = load_gate_config(ROOT / "configs/m13-reference-agent-gate.yaml")
    scenarios = {scenario.fault.type: scenario for scenario in config.scenarios}

    assert scenarios["model_timeout"].expect.fallback_reason == "TimeoutError"
    assert scenarios["model_429"].expect.fallback_reason == "ModelRateLimitError"
    assert scenarios["downstream_5xx"].expect.ticket_status == "unavailable"
    assert scenarios["downstream_5xx"].expect.min_failed_tools == 1
    assert scenarios["tool_slow_response"].expect.min_duration_ms == 45
    assert scenarios["knowledge_unavailable"].expect.knowledge_status == "unavailable"
    assert scenarios["knowledge_unavailable"].expect.source_count == 0
    assert scenarios["sse_interruption"].load.protocol == "sse"
    assert scenarios["sse_interruption"].expect.error_type == "stream_interrupted"
    assert scenarios["database_error"].expect.status_code == 503


def test_compose_can_supply_fault_security_and_versioned_mock_pricing():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    environment = compose["services"]["reference-agent"]["environment"]

    assert "REFERENCE_AGENT_TEST_FAULTS_ENABLED" in environment
    assert "REFERENCE_AGENT_TEST_FAULT_TOKEN" in environment
    assert "LLM_PRICING_TABLE" in environment


def test_workflow_runs_network_gate_and_always_uploads_reports():
    workflow = yaml.load(
        (ROOT / ".github/workflows/loadtest.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    job = workflow["jobs"]["m13-quality-gate"]
    steps = job["steps"]
    by_name = {step.get("name", ""): step for step in steps}

    assert job["env"]["REFERENCE_AGENT_TEST_FAULTS_ENABLED"] == "true"
    assert job["env"]["REFERENCE_AGENT_TEST_FAULT_TOKEN"].startswith("ci-")
    assert "mock/mock" in job["env"]["LLM_PRICING_TABLE"]
    assert any("uvicorn" in step.get("run", "") for step in steps)
    assert any("/api/health" in step.get("run", "") for step in steps)
    assert any(
        "qe_platform.loadtest.gate_cli" in step.get("run", "") for step in steps
    )
    upload = by_name["Upload milestone 13 gate reports"]
    assert upload["if"] == "always()"
    assert "reports/m13-gate.json" in upload["with"]["path"]
    assert "reports/m13-gate.html" in upload["with"]["path"]
