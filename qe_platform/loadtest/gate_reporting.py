"""JSON and standalone HTML reports for milestone 13 quality gates."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .gate_models import GateSuiteResult
from .models import LoadTestRun


def _display(value: Any) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _phase(name: str, run: LoadTestRun | None) -> str:
    if run is None:
        return ""
    summary = run.summary
    sample_rows = "".join(
        "<tr>"
        f"<td>{index}</td>"
        f"<td>{'OK' if sample.success else 'ERROR'}</td>"
        f"<td>{sample.duration_ms:.3f}</td>"
        f"<td>{html.escape(_display(sample.ttft_ms))}</td>"
        f"<td>{html.escape(_display(sample.status_code))}</td>"
        f"<td>{html.escape(sample.error_type)}</td>"
        f"<td>{html.escape(sample.trace_id)}</td>"
        "</tr>"
        for index, sample in enumerate(run.samples, 1)
    )
    metrics = {
        "completed": summary.completed,
        "succeeded": summary.succeeded,
        "failed": summary.failed,
        "throughput_rps": summary.throughput_rps,
        "latency_ms": dict(summary.latency_ms),
        "ttft_ms": dict(summary.ttft_ms),
        "error_rate": summary.error_rate,
        "rate_429": summary.rate_429,
        "stream_interruption_rate": summary.stream_interruption_rate,
        "cost_total": summary.cost_total,
        "cost_currency": summary.cost_currency,
    }
    return (
        f"<h3>{html.escape(name)}</h3>"
        f"<pre>{html.escape(json.dumps(metrics, ensure_ascii=False, sort_keys=True, indent=2))}</pre>"
        "<table><thead><tr><th>#</th><th>Status</th><th>Latency ms</th>"
        "<th>TTFT ms</th><th>HTTP</th><th>Error</th><th>Trace</th></tr></thead>"
        f"<tbody>{sample_rows}</tbody></table>"
    )


def write_gate_reports(result: GateSuiteResult) -> tuple[Path, Path]:
    json_path = Path(result.config.json_report)
    html_path = Path(result.config.html_report)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.as_dict()
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    scenario_sections = []
    for scenario in result.scenarios:
        checks = "".join(
            "<tr>"
            f"<td>{html.escape(check.stage)}</td>"
            f"<td>{html.escape(check.name)}</td>"
            f"<td>{html.escape(check.operator)}</td>"
            f"<td>{html.escape(_display(check.expected))}</td>"
            f"<td>{html.escape(_display(check.actual))}</td>"
            f"<td>{html.escape(check.unit)}</td>"
            f"<td class={'ok' if check.passed else 'bad'}>{'PASSED' if check.passed else 'FAILED'}</td>"
            f"<td>{html.escape(check.reason)}</td>"
            "</tr>"
            for check in scenario.checks
        )
        scenario_sections.append(
            "<section>"
            f"<h2>{html.escape(scenario.scenario_id)} · {html.escape(scenario.fault_type)} · "
            f"<span class={'ok' if scenario.gate_passed else 'bad'}>{'PASSED' if scenario.gate_passed else 'FAILED'}</span></h2>"
            f"{_phase('Fault phase', scenario.fault_run)}"
            f"{_phase('Recovery phase', scenario.recovery_run)}"
            "<h3>Gate checks</h3><table><thead><tr><th>Stage</th><th>Check</th>"
            "<th>Operator</th><th>Expected</th><th>Actual</th><th>Unit</th>"
            f"<th>Result</th><th>Reason</th></tr></thead><tbody>{checks}</tbody></table>"
            "</section>"
        )
    status = "PASSED" if result.gate_passed else "FAILED"
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>M13 Quality Gate</title><style>
body{{font:15px system-ui;margin:2rem;color:#172033}}section{{margin:2rem 0;padding:1rem;border:1px solid #ccd5e0;border-radius:8px}}
table{{width:100%;border-collapse:collapse;margin:1rem 0}}th,td{{padding:.5rem;border:1px solid #ddd;text-align:left;vertical-align:top}}
pre{{white-space:pre-wrap;background:#f6f8fa;padding:1rem}}.ok{{color:#087830}}.bad{{color:#b42318}}
</style></head><body><h1>M13 Quality Gate</h1>
<p>Suite: <code>{html.escape(result.config.id)}</code></p>
<p>Started: {html.escape(result.started_at)} · Finished: {html.escape(result.finished_at)}</p>
<p>Scenarios: {len(result.scenarios)} · Passed: {result.passed_scenarios} · Failed checks: {result.failed_checks} · Gate: <strong class={'ok' if result.gate_passed else 'bad'}>{status}</strong></p>
{''.join(scenario_sections)}</body></html>"""
    html_path.write_text(document, encoding="utf-8")
    return json_path, html_path
