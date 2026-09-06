from __future__ import annotations

import asyncio

import httpx
import pytest

from qe_platform.loadtest.gate_models import (
    FaultSpec,
    GateScenarioConfig,
    GateSuiteConfig,
    GateThresholds,
    SampleExpectation,
)
from qe_platform.loadtest.gate_runner import GateSuiteRunner
from qe_platform.loadtest.metrics import summarize
from qe_platform.loadtest.models import LoadTestConfig, LoadTestRun, SampleResult
from reference_agent.app import create_app
from reference_agent.faults import FaultControlSettings
from reference_agent.services import KnowledgeBase


def _app(tmp_path):
    return create_app(
        str(tmp_path / "gate-runner.db"),
        knowledge_base=KnowledgeBase(
            [
                {
                    "document_id": "KB-VPN-001",
                    "title": "VPN 指引",
                    "content": "VPN 用于远程办公。",
                }
            ]
        ),
        fault_settings=FaultControlSettings(True, "secret"),
    )


def _suite(tmp_path, scenarios):
    return GateSuiteConfig(
        id="m13",
        target_url="http://test",
        fault_token_env="M13_TOKEN",
        json_report=str(tmp_path / "gate.json"),
        html_report=str(tmp_path / "gate.html"),
        thresholds=GateThresholds(max_error_rate=0, max_latency_p95_ms=1000),
        scenarios=scenarios,
    )


def _load(message="如何使用 VPN？", protocol="http"):
    return LoadTestConfig(
        target_url="http://test",
        protocol=protocol,
        requests=2,
        concurrency=2,
        message=message,
        json_report="",
        html_report="",
    )


def test_gate_runner_executes_fault_then_recovery_for_every_scenario(tmp_path):
    app = _app(tmp_path)
    client_phases = []

    def client_factory(**kwargs):
        client_phases.append("fault" if "X-QE-Fault" in kwargs["headers"] else "recovery")
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            **kwargs,
        )

    scenarios = [
        GateScenarioConfig(
            id="model-timeout",
            load=_load(),
            fault=FaultSpec("model_timeout"),
            expect=SampleExpectation(
                success=True, status_code=200, fallback_reason="TimeoutError"
            ),
            recovery=True,
            recovery_expect=SampleExpectation(
                success=True, status_code=200, knowledge_status="answered"
            ),
            thresholds=GateThresholds(max_error_rate=0, max_latency_p95_ms=1000),
        ),
        GateScenarioConfig(
            id="database-error",
            load=_load(),
            fault=FaultSpec("database_error"),
            expect=SampleExpectation(
                success=False, status_code=503, error_type="http_error"
            ),
            recovery=True,
            recovery_expect=SampleExpectation(
                success=True, status_code=200, knowledge_status="answered"
            ),
            thresholds=GateThresholds(max_error_rate=0, max_latency_p95_ms=1000),
        ),
    ]

    result = asyncio.run(
        GateSuiteRunner(
            _suite(tmp_path, scenarios),
            client_factory=client_factory,
            environ={"M13_TOKEN": "secret"},
        ).run()
    )

    assert client_phases == ["fault", "recovery", "fault", "recovery", "recovery"]
    assert [item.scenario_id for item in result.scenarios] == [
        "model-timeout",
        "database-error",
    ]
    assert result.gate_passed is True
    assert result.failed_checks == 0
    assert all(item.recovery_run is not None for item in result.scenarios)
    database_checks = [
        check
        for check in result.scenarios[1].checks
        if check.name == "database_recovery_session_count"
    ]
    assert len(database_checks) == 1
    assert database_checks[0].expected == 2
    assert database_checks[0].actual == 2
    assert database_checks[0].passed is True


def test_gate_runner_continues_after_a_failed_expectation(tmp_path):
    app = _app(tmp_path)

    def client_factory(**kwargs):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            **kwargs,
        )

    scenarios = [
        GateScenarioConfig(
            id="wrong-expectation",
            load=_load(),
            fault=FaultSpec("model_timeout"),
            expect=SampleExpectation(fallback_reason="wrong"),
            recovery=True,
            recovery_expect=SampleExpectation(success=True),
            thresholds=GateThresholds(max_error_rate=0),
        ),
        GateScenarioConfig(
            id="still-runs",
            load=_load(),
            fault=FaultSpec("knowledge_unavailable"),
            expect=SampleExpectation(knowledge_status="unavailable"),
            recovery=True,
            recovery_expect=SampleExpectation(knowledge_status="answered"),
            thresholds=GateThresholds(max_error_rate=0),
        ),
    ]

    result = asyncio.run(
        GateSuiteRunner(
            _suite(tmp_path, scenarios),
            client_factory=client_factory,
            environ={"M13_TOKEN": "secret"},
        ).run()
    )

    assert len(result.scenarios) == 2
    assert result.scenarios[0].gate_passed is False
    assert result.scenarios[1].gate_passed is True
    assert result.gate_passed is False


def test_gate_runner_rejects_missing_fault_token_before_requests(tmp_path):
    scenario = GateScenarioConfig(
        id="timeout",
        load=_load(),
        fault=FaultSpec("model_timeout"),
        expect=SampleExpectation(success=True),
        recovery=True,
        recovery_expect=SampleExpectation(success=True),
        thresholds=GateThresholds(max_error_rate=0),
    )

    with pytest.raises(ValueError, match="M13_TOKEN"):
        asyncio.run(GateSuiteRunner(_suite(tmp_path, [scenario]), environ={}).run())


def test_database_recovery_requires_unique_persisted_sessions(tmp_path):
    app = _app(tmp_path)
    app.state.store.upsert_session("duplicate", "U1001")

    def client_factory(**kwargs):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            **kwargs,
        )

    load = _load()
    samples = [
        SampleResult(True, 10, None, status_code=200, conversation_id="duplicate"),
        SampleResult(True, 12, None, status_code=200, conversation_id="duplicate"),
    ]
    run = LoadTestRun(
        load,
        "start",
        "finish",
        samples,
        summarize(samples, load, wall_time_ms=12),
    )
    runner = GateSuiteRunner(
        _suite(tmp_path, []),
        client_factory=client_factory,
        environ={"M13_TOKEN": "secret"},
    )

    check = asyncio.run(runner._verify_database_recovery(load, run))

    assert check.expected == 2
    assert check.actual == 1
    assert check.passed is False


def test_phase_execution_error_still_runs_recovery_and_remaining_scenarios(tmp_path):
    app = _app(tmp_path)
    calls = []

    def client_factory(**kwargs):
        phase = "fault" if "X-QE-Fault" in kwargs["headers"] else "recovery"
        calls.append(phase)
        if len(calls) == 1:
            raise RuntimeError("client construction failed")
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            **kwargs,
        )

    scenarios = [
        GateScenarioConfig(
            id="first",
            load=_load(),
            fault=FaultSpec("model_timeout"),
            expect=SampleExpectation(success=True),
            recovery=True,
            recovery_expect=SampleExpectation(success=True),
            thresholds=GateThresholds(max_error_rate=0),
        ),
        GateScenarioConfig(
            id="second",
            load=_load(),
            fault=FaultSpec("knowledge_unavailable"),
            expect=SampleExpectation(knowledge_status="unavailable"),
            recovery=True,
            recovery_expect=SampleExpectation(knowledge_status="answered"),
            thresholds=GateThresholds(max_error_rate=0),
        ),
    ]

    result = asyncio.run(
        GateSuiteRunner(
            _suite(tmp_path, scenarios),
            client_factory=client_factory,
            environ={"M13_TOKEN": "secret"},
        ).run()
    )

    assert calls == ["fault", "recovery", "fault", "recovery"]
    assert len(result.scenarios) == 2
    assert result.scenarios[0].execution_errors[0].stage == "fault"
    assert result.scenarios[0].execution_errors[0].error_type == "RuntimeError"
    assert result.scenarios[0].recovery_run is not None
    assert result.scenarios[1].gate_passed is True
    assert result.execution_error_count == 1
    assert result.gate_passed is False
