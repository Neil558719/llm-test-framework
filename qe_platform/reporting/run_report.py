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

    def as_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "started_at": self.started_at, "finished_at": self.finished_at, "total": self.total, "passed": self.passed, "failed": self.failed, "gate_passed": self.gate_passed, "scenarios": self.scenarios}


def _scenario_payload(result: ScenarioRunResult) -> dict[str, Any]:
    payload = result.as_dict()
    payload["failed_assertions"] = [item for item in payload["final_assertions"] + [a for step in payload["steps"] for a in step["assertions"]] if not item["passed"]]
    payload["business_state_differences"] = [item for item in payload["failed_assertions"] if item.get("assertion_type") == "business_state"]
    return payload


def build_run_report(results: Iterable[ScenarioRunResult], *, run_id: str | None = None) -> RunReport:
    values = list(results)
    started = min((item.started_at for item in values), default="")
    finished = max((item.finished_at for item in values), default="")
    return RunReport(run_id or str(uuid.uuid4()), started, finished, [_scenario_payload(item) for item in values])


def write_json(report: RunReport, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target


def write_html(report: RunReport, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for scenario in report.scenarios:
        status = "PASSED" if scenario["passed"] else "FAILED"
        failures = "<br>".join(html.escape(item.get("message", "")) for item in scenario["failed_assertions"]) or "-"
        tools = ", ".join(html.escape(item["name"]) for item in scenario["tool_calls"]) or "-"
        rows.append(f"<tr><td>{html.escape(scenario['scenario_id'])}</td><td>{status}</td><td>{tools}</td><td>{failures}</td></tr>")
    body = "".join(rows)
    document = f"<!doctype html><html><head><meta charset='utf-8'><title>V1 Run Report</title><style>body{{font:15px system-ui;margin:2rem}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccc;padding:.5rem;text-align:left}}.ok{{color:green}}.bad{{color:#b00}}</style></head><body><h1>V1 API E2E Run Report</h1><p>Run: <code>{html.escape(report.run_id)}</code></p><p>Total: {report.total} | Passed: <span class='ok'>{report.passed}</span> | Failed: <span class='bad'>{report.failed}</span> | Gate: {str(report.gate_passed).lower()}</p><table><thead><tr><th>Scenario</th><th>Status</th><th>Tool calls</th><th>Failed assertions</th></tr></thead><tbody>{body}</tbody></table></body></html>"
    target.write_text(document, encoding="utf-8")
    return target
