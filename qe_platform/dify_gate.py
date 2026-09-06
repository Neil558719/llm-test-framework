from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from qe_platform.adapters import DIFY_CHAT_CAPABILITY_MATRIX, DifyAdapterConfig, DifyChatAdapter
from qe_platform.reporting import build_run_report
from qe_platform.scenarios import load_scenarios
from qe_platform.workflow_runner import ScenarioRunner, ScenarioRunResult


def _redact_assertion(item: dict[str, Any]) -> dict[str, Any]:
    result = dict(item)
    if "expected" in result:
        result["expected"] = "[REDACTED]"
    if "actual" in result:
        result["actual"] = "[REDACTED]"
    return result


def _redact_scenario(item: dict[str, Any]) -> dict[str, Any]:
    scenario = dict(item)
    steps = []
    for step in scenario.get("steps", []):
        safe_step = dict(step)
        safe_step["user"] = "[REDACTED]"
        response = safe_step.get("response")
        if isinstance(response, dict):
            safe_response = dict(response)
            safe_response["answer"] = "[REDACTED]"
            safe_response["sources"] = ["[REDACTED]"] * len(safe_response.get("sources") or [])
            safe_response["raw_response"] = {}
            safe_response["tool_calls"] = []
            safe_step["response"] = safe_response
        safe_step["assertions"] = [_redact_assertion(value) for value in safe_step.get("assertions", [])]
        steps.append(safe_step)
    scenario["steps"] = steps
    scenario["tool_calls"] = []
    scenario["final_assertions"] = [_redact_assertion(value) for value in scenario.get("final_assertions", [])]
    scenario["failed_assertions"] = [_redact_assertion(value) for value in scenario.get("failed_assertions", [])]
    scenario["business_state_differences"] = [_redact_assertion(value) for value in scenario.get("business_state_differences", [])]
    return scenario


def build_dify_report(results: Iterable[ScenarioRunResult]) -> dict[str, Any]:
    run_report = build_run_report(results).as_dict()
    capabilities = DIFY_CHAT_CAPABILITY_MATRIX.as_dict()
    return {
        **run_report,
        "capabilities": capabilities,
        "limitations": {
            key: value["description"]
            for key, value in capabilities.items()
            if value["status"] != "supported"
        },
        "scenarios": [_redact_scenario(value) for value in run_report["scenarios"]],
    }


def _write_json(payload: dict[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target


def _write_html(payload: dict[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    capability_rows = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td></tr>"
        % (html.escape(key), html.escape(value["status"]), html.escape(value["description"]))
        for key, value in payload["capabilities"].items()
    )
    scenario_rows = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td></tr>"
        % (
            html.escape(str(value["scenario_id"])),
            "PASSED" if value["passed"] else "FAILED",
            "complete" if value["complete"] else "incomplete",
        )
        for value in payload["scenarios"]
    )
    document = """<!doctype html><html><head><meta charset='utf-8'><title>Dify Compatibility Report</title><style>body{font:15px system-ui;margin:2rem}table{border-collapse:collapse;width:100%%;margin-bottom:1.5rem}th,td{border:1px solid #ccc;padding:.5rem;text-align:left}</style></head><body><h1>Dify Chat Compatibility Report</h1><p>Total: %s | Passed: %s | Failed: %s | Gate: %s</p><h2>Capability matrix</h2><table><thead><tr><th>Capability</th><th>Status</th><th>Description</th></tr></thead><tbody>%s</tbody></table><h2>Scenario results</h2><table><thead><tr><th>Scenario</th><th>Status</th><th>Execution</th></tr></thead><tbody>%s</tbody></table></body></html>""" % (
        payload["total"],
        payload["passed"],
        payload["failed"],
        str(payload["gate_passed"]).lower(),
        capability_rows,
        scenario_rows,
    )
    target.write_text(document, encoding="utf-8")
    return target


def run_gate(
    *,
    asset_dir: str | Path,
    config: DifyAdapterConfig,
    json_path: str | Path,
    html_path: str | Path,
) -> int:
    try:
        scenarios = load_scenarios(asset_dir)
        results = [ScenarioRunner(lambda _setup: DifyChatAdapter(config)).run(item) for item in scenarios]
        payload = build_dify_report(results)
        _write_json(payload, json_path)
        _write_html(payload, html_path)
    except Exception:
        return 1
    if payload["gate_passed"]:
        return 0
    if any(not item["complete"] for item in payload["scenarios"]):
        return 1
    return 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Dify Chat compatibility scenarios")
    parser.add_argument("--assets", default="qe_platform/scenarios/assets/dify")
    parser.add_argument("--json", dest="json_path", default="reports/dify-compatibility.json")
    parser.add_argument("--html", dest="html_path", default="reports/dify-compatibility.html")
    args = parser.parse_args(argv)
    try:
        config = DifyAdapterConfig.from_environment()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return run_gate(asset_dir=args.assets, config=config, json_path=args.json_path, html_path=args.html_path)


if __name__ == "__main__":
    sys.exit(main())
