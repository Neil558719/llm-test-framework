from __future__ import annotations

import textwrap

import pytest

from qe_platform.loadtest.gate_config import load_gate_config


def _write(tmp_path, body: str):
    path = tmp_path / "gate.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def test_gate_config_loads_defaults_and_merges_scenario_thresholds(tmp_path):
    path = _write(
        tmp_path,
        """
        id: m13
        target_url: http://localhost:8000
        fault_token_env: M13_TOKEN
        reports:
          json: reports/m13.json
          html: reports/m13.html
        defaults:
          requests: 4
          concurrency: 2
          timeout_seconds: 5
          user_id: U1001
        thresholds:
          max_error_rate: 0
          max_latency_p95_ms: 1000
        scenarios:
          - id: model-timeout
            protocol: http
            message: 如何使用 VPN？
            fault: {type: model_timeout}
            expect: {success: true, status_code: 200, fallback_reason: TimeoutError}
            recovery: true
            recovery_expect: {success: true, status_code: 200, knowledge_status: answered}
            thresholds: {max_latency_p95_ms: 1500}
        """,
    )

    config = load_gate_config(path)

    assert config.id == "m13"
    assert config.fault_token_env == "M13_TOKEN"
    assert config.json_report == "reports/m13.json"
    scenario = config.scenarios[0]
    assert scenario.load.requests == 4
    assert scenario.load.concurrency == 2
    assert scenario.load.message == "如何使用 VPN？"
    assert scenario.fault.type == "model_timeout"
    assert scenario.thresholds.max_error_rate == 0
    assert scenario.thresholds.max_latency_p95_ms == 1500
    assert scenario.expect.fallback_reason == "TimeoutError"
    assert scenario.recovery_expect.knowledge_status == "answered"


@pytest.mark.parametrize(
    "fragment,match",
    [
        ("fault_token: inline-secret", "unknown gate config fields"),
        ("unknown: value", "unknown gate config fields"),
        ("defaults:\n  unknown: value", "unknown defaults fields"),
        ("reports:\n  json: out.json\n  unknown: out", "unknown reports fields"),
        ("thresholds:\n  unknown: 1", "unknown threshold fields"),
    ],
)
def test_gate_config_rejects_unknown_top_level_and_nested_fields(
    tmp_path, fragment, match
):
    path = _write(
        tmp_path,
        f"""id: m13
target_url: http://localhost:8000
fault_token_env: M13_TOKEN
{fragment}
scenarios:
  - id: timeout
    message: VPN
    fault: {{type: model_timeout}}
    expect: {{success: true}}
""",
    )

    with pytest.raises(ValueError, match=match):
        load_gate_config(path)


def test_gate_config_rejects_unknown_scenario_and_expectation_fields(tmp_path):
    unknown_scenario = _write(
        tmp_path,
        """
        id: m13
        target_url: http://localhost:8000
        fault_token_env: M13_TOKEN
        scenarios:
          - id: timeout
            message: VPN
            fault: {type: model_timeout}
            expect: {success: true}
            typo: true
        """,
    )
    with pytest.raises(ValueError, match="unknown scenario fields"):
        load_gate_config(unknown_scenario)

    unknown_expectation = _write(
        tmp_path,
        """
        id: m13
        target_url: http://localhost:8000
        fault_token_env: M13_TOKEN
        scenarios:
          - id: timeout
            message: VPN
            fault: {type: model_timeout}
            expect: {success: true, private_context: secret}
        """,
    )
    with pytest.raises(ValueError, match="unknown expectation fields"):
        load_gate_config(unknown_expectation)


def test_gate_config_rejects_duplicate_scenario_ids(tmp_path):
    path = _write(
        tmp_path,
        """
        id: m13
        target_url: http://localhost:8000
        fault_token_env: M13_TOKEN
        scenarios:
          - id: duplicate
            message: VPN
            fault: {type: model_timeout}
            expect: {success: true}
          - id: duplicate
            message: VPN
            fault: {type: model_429}
            expect: {success: true}
        """,
    )

    with pytest.raises(ValueError, match="duplicate scenario id"):
        load_gate_config(path)


def test_gate_config_requires_sse_protocol_for_sse_interruption(tmp_path):
    path = _write(
        tmp_path,
        """
        id: m13
        target_url: http://localhost:8000
        fault_token_env: M13_TOKEN
        scenarios:
          - id: interrupted
            protocol: http
            message: VPN
            fault: {type: sse_interruption}
            expect: {success: false, error_type: stream_interrupted}
        """,
    )

    with pytest.raises(ValueError, match="requires protocol 'sse'"):
        load_gate_config(path)


@pytest.mark.parametrize("header", ["X-QE-Test-Token", "x-qe-fault"])
def test_gate_config_rejects_reserved_fault_headers_in_yaml(tmp_path, header):
    path = _write(
        tmp_path,
        f"""
        id: m13
        target_url: http://localhost:8000
        fault_token_env: M13_TOKEN
        defaults:
          headers: {{{header}: inline-secret}}
        scenarios:
          - id: timeout
            message: VPN
            fault: {{type: model_timeout}}
            expect: {{success: true}}
        """,
    )

    with pytest.raises(ValueError, match="reserved fault control header"):
        load_gate_config(path)


def test_gate_config_rejects_missing_or_invalid_required_values(tmp_path):
    for body, match in [
        ("{}", "id"),
        (
            "id: m13\ntarget_url: http://localhost:8000\nfault_token_env: 123\nscenarios: []",
            "fault_token_env",
        ),
        (
            "id: m13\ntarget_url: http://localhost:8000\nfault_token_env: M13-TOKEN\nscenarios: []",
            "fault_token_env",
        ),
        (
            "id: m13\ntarget_url: http://localhost:8000\nfault_token_env: M13_TOKEN\nscenarios: []",
            "at least one scenario",
        ),
    ]:
        with pytest.raises(ValueError, match=match):
            load_gate_config(_write(tmp_path, body))


@pytest.mark.parametrize(
    "fragment,match",
    [
        ("thresholds: []", "thresholds must be a mapping"),
        ("defaults:\n  headers: []", "headers must be a mapping"),
        (
            "scenarios:\n  - id: timeout\n    message: VPN\n    fault: {type: model_timeout}\n    expect: []",
            r"scenarios\[0\]\.expect must be a mapping",
        ),
    ],
)
def test_gate_config_rejects_falsey_non_mapping_nested_values(
    tmp_path, fragment, match
):
    scenarios = "" if fragment.startswith("scenarios:") else """
scenarios:
  - id: timeout
    message: VPN
    fault: {type: model_timeout}
    expect: {success: true}
"""
    path = _write(
        tmp_path,
        f"""id: m13
target_url: http://localhost:8000
fault_token_env: M13_TOKEN
{fragment}
{scenarios}
""",
    )

    with pytest.raises(ValueError, match=match):
        load_gate_config(path)
