from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from qe_platform.loadtest import gate_cli
from qe_platform.loadtest.gate_models import GateExecutionError
from test_loadtest_gate_reporting import gate_result


class _Runner:
    result = None
    error: Exception | None = None

    def __init__(self, config):
        self.config = config

    async def run(self):
        if self.error is not None:
            raise self.error
        return self.result


def _patch_success(monkeypatch, result):
    _Runner.result = result
    _Runner.error = None
    monkeypatch.setattr(gate_cli, "load_gate_config", lambda _: result.config)
    monkeypatch.setattr(gate_cli, "GateSuiteRunner", _Runner)
    monkeypatch.setattr(
        gate_cli,
        "write_gate_reports",
        lambda _: (Path(result.config.json_report), Path(result.config.html_report)),
    )


def test_gate_cli_returns_zero_when_all_checks_pass(tmp_path, monkeypatch, capsys):
    result = gate_result(tmp_path, passed=True)
    _patch_success(monkeypatch, result)

    exit_code = gate_cli.main([str(tmp_path / "gate.yaml")])

    assert exit_code == 0
    assert "Gate passed" in capsys.readouterr().out


def test_gate_cli_returns_three_when_checks_fail(tmp_path, monkeypatch, capsys):
    result = gate_result(tmp_path, passed=False)
    _patch_success(monkeypatch, result)

    exit_code = gate_cli.main([str(tmp_path / "gate.yaml")])

    assert exit_code == 3
    captured = capsys.readouterr()
    assert "Gate failed" in captured.err
    assert "1 checks failed" in captured.err
    assert "Traceback" not in captured.err


def test_gate_cli_returns_two_for_configuration_error(tmp_path, monkeypatch, capsys):
    def invalid(_):
        raise ValueError("bad gate config")

    monkeypatch.setattr(gate_cli, "load_gate_config", invalid)

    assert gate_cli.main([str(tmp_path / "gate.yaml")]) == 2
    captured = capsys.readouterr()
    assert "Configuration error: bad gate config" in captured.err
    assert "Traceback" not in captured.err


def test_gate_cli_returns_two_when_fault_token_environment_is_missing(
    tmp_path, monkeypatch, capsys
):
    result = gate_result(tmp_path, passed=True)
    _patch_success(monkeypatch, result)
    _Runner.error = ValueError("fault token environment variable is missing: M13_TOKEN")

    assert gate_cli.main([str(tmp_path / "gate.yaml")]) == 2
    captured = capsys.readouterr()
    assert "M13_TOKEN" in captured.err
    assert "Traceback" not in captured.err


def test_gate_cli_returns_one_for_execution_or_report_errors(
    tmp_path, monkeypatch, capsys
):
    result = gate_result(tmp_path, passed=True)
    _patch_success(monkeypatch, result)
    _Runner.error = RuntimeError("network setup failed")

    assert gate_cli.main([str(tmp_path / "gate.yaml")]) == 1
    first = capsys.readouterr()
    assert "Gate execution error: network setup failed" in first.err

    _patch_success(monkeypatch, result)

    def report_error(_):
        raise OSError("disk full")

    monkeypatch.setattr(gate_cli, "write_gate_reports", report_error)
    assert gate_cli.main([str(tmp_path / "gate.yaml")]) == 1
    second = capsys.readouterr()
    assert "Gate execution error: disk full" in second.err
    assert "Traceback" not in first.err + second.err


def test_gate_cli_returns_one_after_writing_phase_execution_error_report(
    tmp_path, monkeypatch, capsys
):
    result = gate_result(tmp_path, passed=True)
    scenario = replace(
        result.scenarios[0],
        execution_errors=[GateExecutionError("fault", "RuntimeError")],
    )
    result = replace(result, scenarios=[scenario])
    writes = []
    _Runner.result = result
    _Runner.error = None
    monkeypatch.setattr(gate_cli, "load_gate_config", lambda _: result.config)
    monkeypatch.setattr(gate_cli, "GateSuiteRunner", _Runner)
    monkeypatch.setattr(
        gate_cli,
        "write_gate_reports",
        lambda value: writes.append(value)
        or (Path(value.config.json_report), Path(value.config.html_report)),
    )

    assert gate_cli.main([str(tmp_path / "gate.yaml")]) == 1
    assert writes == [result]
    captured = capsys.readouterr()
    assert "1 phase execution error" in captured.err
