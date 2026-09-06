"""Strict YAML loader for milestone 13 gate suites."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

import yaml

from .gate_models import (
    FaultSpec,
    GateScenarioConfig,
    GateSuiteConfig,
    GateThresholds,
    SampleExpectation,
)
from .models import LoadTestConfig


_TOP_LEVEL = {
    "id",
    "target_url",
    "fault_token_env",
    "reports",
    "defaults",
    "thresholds",
    "scenarios",
}
_LOAD_FIELDS = {
    "protocol",
    "requests",
    "duration_seconds",
    "concurrency",
    "warmup_requests",
    "timeout_seconds",
    "user_id",
    "message",
    "headers",
}
_SCENARIO_FIELDS = _LOAD_FIELDS | {
    "id",
    "fault",
    "expect",
    "recovery",
    "recovery_expect",
    "thresholds",
}
_FAULT_FIELDS = {"type", "target", "status_code", "delay_seconds"}
_THRESHOLD_FIELDS = set(GateThresholds.__dataclass_fields__)
_EXPECTATION_FIELDS = set(SampleExpectation.__dataclass_fields__)
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be a mapping with string keys")
    return dict(value)


def _reject_unknown(value: Mapping[str, Any], allowed: set[str], name: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"unknown {name} fields: {', '.join(unknown)}")


def _non_empty_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _thresholds(raw: Any, name: str) -> GateThresholds:
    value = _mapping({} if raw is None else raw, name)
    _reject_unknown(value, _THRESHOLD_FIELDS, "threshold")
    return GateThresholds(**value)


def _expectation(raw: Any, name: str) -> SampleExpectation:
    value = _mapping({} if raw is None else raw, name)
    _reject_unknown(value, _EXPECTATION_FIELDS, "expectation")
    return SampleExpectation(**value)


def _fault(raw: Any) -> FaultSpec:
    value = _mapping(raw, "fault")
    _reject_unknown(value, _FAULT_FIELDS, "fault")
    try:
        return FaultSpec(**value)
    except TypeError as exc:
        raise ValueError(f"invalid fault: {exc}") from exc


def _headers(raw: Any) -> dict[str, str]:
    value = _mapping({} if raw is None else raw, "headers")
    if not all(isinstance(item, str) for item in value.values()):
        raise ValueError("headers must be a string mapping")
    reserved = {"x-qe-test-token", "x-qe-fault"}
    if any(key.lower() in reserved for key in value):
        raise ValueError("reserved fault control header cannot be configured in YAML")
    return value


def load_gate_config(path: str | Path) -> GateSuiteConfig:
    try:
        loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot load gate config: {exc}") from exc
    raw = _mapping(loaded, "gate config")
    _reject_unknown(raw, _TOP_LEVEL, "gate config")

    suite_id = _non_empty_text(raw.get("id"), "id")
    target_url = _non_empty_text(raw.get("target_url"), "target_url")
    token_env = _non_empty_text(raw.get("fault_token_env"), "fault_token_env")
    if _ENV_NAME.fullmatch(token_env) is None:
        raise ValueError("fault_token_env must be a valid environment variable name")

    reports = _mapping(raw.get("reports", {}), "reports")
    _reject_unknown(reports, {"json", "html"}, "reports")
    json_report = _non_empty_text(reports.get("json", "reports/m13-gate.json"), "reports.json")
    html_report = _non_empty_text(reports.get("html", "reports/m13-gate.html"), "reports.html")

    defaults = _mapping(raw.get("defaults", {}), "defaults")
    _reject_unknown(defaults, _LOAD_FIELDS, "defaults")
    if "headers" in defaults:
        defaults["headers"] = _headers(defaults["headers"])
    suite_thresholds = _thresholds(raw.get("thresholds", {}), "thresholds")

    raw_scenarios = raw.get("scenarios")
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise ValueError("gate config must contain at least one scenario")
    scenarios: list[GateScenarioConfig] = []
    seen: set[str] = set()
    for index, raw_scenario in enumerate(raw_scenarios):
        scenario = _mapping(raw_scenario, f"scenarios[{index}]")
        _reject_unknown(scenario, _SCENARIO_FIELDS, "scenario")
        scenario_id = _non_empty_text(scenario.get("id"), f"scenarios[{index}].id")
        if scenario_id in seen:
            raise ValueError(f"duplicate scenario id: {scenario_id}")
        seen.add(scenario_id)

        load_values = {**defaults}
        load_values.update({key: scenario[key] for key in _LOAD_FIELDS if key in scenario})
        if "duration_seconds" in scenario and "requests" not in scenario:
            load_values["requests"] = None
        elif "duration_seconds" in defaults and "requests" not in defaults:
            load_values["requests"] = None
        if "headers" in load_values:
            load_values["headers"] = _headers(load_values["headers"])
        load_values.update(
            {
                "target_url": target_url,
                "json_report": "",
                "html_report": "",
            }
        )
        try:
            load = LoadTestConfig(**load_values)
        except TypeError as exc:
            raise ValueError(f"invalid scenario {scenario_id}: {exc}") from exc

        local_threshold_values = _mapping(
            scenario.get("thresholds", {}),
            f"scenarios[{index}].thresholds",
        )
        _reject_unknown(local_threshold_values, _THRESHOLD_FIELDS, "threshold")
        merged_thresholds = GateThresholds(
            **{**suite_thresholds.as_dict(), **local_threshold_values}
        )
        recovery = scenario.get("recovery", True)
        if not isinstance(recovery, bool):
            raise ValueError(f"scenarios[{index}].recovery must be a boolean")
        scenarios.append(
            GateScenarioConfig(
                id=scenario_id,
                load=load,
                fault=_fault(scenario.get("fault")),
                expect=_expectation(scenario.get("expect"), f"scenarios[{index}].expect"),
                recovery=recovery,
                recovery_expect=_expectation(
                    scenario.get(
                        "recovery_expect", {"success": True, "status_code": 200}
                    ),
                    f"scenarios[{index}].recovery_expect",
                ),
                thresholds=merged_thresholds,
            )
        )

    return GateSuiteConfig(
        id=suite_id,
        target_url=target_url,
        fault_token_env=token_env,
        json_report=json_report,
        html_report=html_report,
        thresholds=suite_thresholds,
        scenarios=scenarios,
    )
