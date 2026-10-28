from __future__ import annotations

import html
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from qe_platform.workflow_runner import ScenarioRunResult


@dataclass
class RunReport:
    run_id: str
    started_at: str
    finished_at: str
    scenarios: list[dict[str, Any]] = field(default_factory=list)
    application: str = ""
    release_id: str = ""
    version: str = ""
    environment: str = "offline"
    manifest: Any = None

    @property
    def complete(self) -> bool:
        return bool(self.scenarios) and all(item["complete"] for item in self.scenarios)

    @property
    def total(self) -> int:
        return len(self.scenarios)

    @property
    def passed(self) -> int:
        return sum(item["passed"] is True for item in self.scenarios)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def gate_passed(self) -> bool:
        return self.total > 0 and self.failed == 0 and all(item["complete"] for item in self.scenarios)

    @property
    def usage(self) -> dict[str, int]:
        values = [item.get("usage") or {} for item in self.scenarios]
        return {"prompt_tokens": sum(int(v.get("prompt_tokens", 0)) for v in values),
                "completion_tokens": sum(int(v.get("completion_tokens", 0)) for v in values),
                "total_tokens": sum(int(v.get("total_tokens", 0)) for v in values)}

    @property
    def cost(self) -> dict[str, Any] | None:
        values = [item.get("cost") for item in self.scenarios if item.get("cost")]
        if not values:
            return None
        currencies = {v.get("currency", "USD") for v in values}
        versions = {v.get("price_version", "") for v in values}
        return {"input": sum(float(v.get("input", 0)) for v in values),
                "output": sum(float(v.get("output", 0)) for v in values),
                "total": sum(float(v.get("total", 0)) for v in values),
                "currency": currencies.pop() if len(currencies) == 1 else "MIXED",
                "price_version": versions.pop() if len(versions) == 1 else "MIXED"}

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "application": self.application,
            "release_id": self.release_id,
            "version": self.version,
            "environment": self.environment,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "gate_passed": self.gate_passed,
            "usage": self.usage,
            "cost": self.cost,
            "scenarios": self.scenarios,
        }
        if self.manifest is not None:
            from .integrity import validate_v2_report
            payload.update(schema_version="qe-run-v2", manifest=self.manifest.as_dict(), complete=self.complete)
            proof = validate_v2_report(payload, self.manifest)
            payload.update(verification=proof["verification"], release_eligible=self.complete)
        else:
            payload.update(verification="legacy_unverified", release_eligible=False)
        return payload


def _scenario_payload(result: ScenarioRunResult) -> dict[str, Any]:
    payload = result.as_dict()
    payload["failed_assertions"] = [item for item in payload["final_assertions"] + [a for step in payload["steps"] for a in step["assertions"]] if not item["passed"]]
    payload["business_state_differences"] = [item for item in payload["failed_assertions"] if item.get("assertion_type") == "business_state"]
    return payload


def build_run_report(
    results: Iterable[ScenarioRunResult],
    *,
    run_id: str | None = None,
    application: str = "",
    release_id: str = "",
    version: str = "",
    environment: str = "offline",
    manifest: Any = None,
) -> RunReport:
    values = list(results)
    scenario_ids = [item.scenario_id for item in values]
    if len(scenario_ids) != len(set(scenario_ids)):
        raise ValueError("scenario IDs must be unique")
    started = min((item.started_at for item in values), default="")
    finished = max((item.finished_at for item in values), default="")
    report = RunReport(
        run_id or str(uuid.uuid4()),
        started,
        finished,
        [_scenario_payload(item) for item in values],
        application=application,
        release_id=release_id,
        version=version,
        environment=environment,
        manifest=manifest,
    )
    if manifest is not None:
        report.as_dict()
    return report


def write_json(report: RunReport, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target


def write_html(report: RunReport, path: str | Path) -> Path:
    snapshot = report.as_dict()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    def escaped(value):
        return html.escape(str(value))

    def json_value(value):
        return html.escape(json.dumps(value, ensure_ascii=False, sort_keys=True))

    for scenario in report.scenarios:
        status = "PASSED" if scenario["passed"] else "FAILED"
        failures = "<br>".join(html.escape(item.get("message", "")) for item in scenario["failed_assertions"]) or "-"
        tools = ", ".join(html.escape(item["name"]) for item in scenario["tool_calls"]) or "-"
        model = (scenario.get("model_versions") or [{}])[0].get("model", "-")
        usage = scenario.get("usage") or {}
        cost = scenario.get("cost") or {}
        differences = "".join(
            f"<li>{escaped(item.get('assertion_type', ''))} {escaped(item.get('path', ''))}: "
            f"expected <code>{json_value(item.get('expected'))}</code>; actual <code>{json_value(item.get('actual'))}</code></li>"
            for item in scenario["failed_assertions"]
        )
        quality = "".join(
            f"<li>{escaped(check['metric'])}{' (Judge rubric; not gold accuracy)' if check['metric'] == 'accuracy' else ''}: "
            f"{escaped(check['status'])}; required={escaped(check.get('required', True))}; "
            f"score={escaped(check.get('score'))}; threshold={escaped(check.get('threshold'))}; "
            f"reason={escaped(check.get('reason', ''))}; {escaped(check.get('message', ''))}; "
            f"provider={escaped(check.get('provider', ''))}; model={escaped(check.get('model', ''))}; "
            f"evaluator version={escaped(check.get('version', ''))}</li>"
            for check in scenario.get("quality_checks", [])
        )
        traces = ", ".join(escaped(step["response"].get("trace_id", "")) for step in scenario["steps"] if step.get("response")) or "-"
        execution = ('<p>Async execution (stage timings are not SUT latency):</p><pre>' + json_value(scenario['execution']) + '</pre>') if scenario.get('execution') is not None else ''
        details = f"<details><summary>Evidence</summary><p>Trace: {traces}</p><p>Complete: {escaped(scenario['complete'])}</p><p>Dialogue latency ms: {escaped(scenario.get('latency_ms'))}</p><ul>{differences}</ul><p>Quality</p><ul>{quality}</ul></details>"
        rows.append(f"<tr><td>{html.escape(scenario['scenario_id'])}</td><td>{status}</td><td>{tools}</td><td>{html.escape(model)}</td><td>{escaped(usage.get('total_tokens', '-'))}</td><td>{escaped(cost.get('total', '-'))}</td><td>{failures}{details}{execution}</td></tr>")
    body = "".join(rows)
    document = f"<!doctype html><html><head><meta charset='utf-8'><title>V1 Run Report</title><style>body{{font:15px system-ui;margin:2rem}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccc;padding:.5rem;text-align:left}}.ok{{color:green}}.bad{{color:#b00}}</style></head><body><h1>V1 API E2E Run Report</h1><p>Run: <code>{html.escape(report.run_id)}</code></p><p>Total: {report.total} | Passed: <span class='ok'>{report.passed}</span> | Failed: <span class='bad'>{report.failed}</span> | Gate: {str(report.gate_passed).lower()}</p><table><thead><tr><th>Scenario</th><th>Status</th><th>Tool calls</th><th>Model</th><th>Tokens</th><th>Cost</th><th>Failed assertions</th></tr></thead><tbody>{body}</tbody></table></body></html>"
    verification = html.escape(snapshot["verification"])
    eligibility = str(snapshot["release_eligible"]).lower()
    observation = str(report.gate_passed).lower()
    document = document.replace("<h1>V1 API E2E Run Report</h1>",
        f"<h1>API E2E Run Evidence</h1><p>Verification: {verification} | Release eligible: {eligibility} | Reported gate: {observation}</p>")
    target.write_text(document, encoding="utf-8")
    return target
