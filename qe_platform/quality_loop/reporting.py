from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Mapping


def write_quality_json(payload: Mapping[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def write_quality_html(payload: Mapping[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    nested_validation = payload.get("validation") if isinstance(payload.get("validation"), Mapping) else {}
    passed = payload.get("passed", nested_validation.get("passed"))
    status = "PASSED" if passed is True else "FAILED" if passed is False else "QUALITY EVIDENCE"
    color = "#176b2c" if passed is True else "#a11" if passed is False else "#333"
    def cell(value: Any) -> str:
        if value is None:
            return "<span class='null'>null</span>"
        return html.escape(str(value))

    def table(title: str, headers: list[str], rows: list[list[Any]], *, table_id: str) -> str:
        head = "".join(f"<th>{cell(item)}</th>" for item in headers)
        body = "".join("<tr>" + "".join(f"<td>{cell(item)}</td>" for item in row) + "</tr>" for row in rows)
        if not rows:
            body = f"<tr><td colspan='{len(headers)}' class='null'>No data</td></tr>"
        return f"<section><h2>{cell(title)}</h2><table id='{html.escape(table_id)}'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></section>"

    trends = payload.get("trends") if isinstance(payload.get("trends"), list) else []
    trend_rows = [
        [item.get(key) for key in ("bucket", "application", "version", "online_trace_count", "feedback_count", "confirmed_low_quality_count", "low_quality_rate", "offline_run_count", "offline_pass_rate", "p95_latency_ms", "total_tokens", "total_cost")]
        for item in trends if isinstance(item, Mapping)
    ]
    offline_runs: list[Mapping[str, Any]] = []
    if isinstance(payload.get("offline_runs"), list):
        offline_runs = [item for item in payload["offline_runs"] if isinstance(item, Mapping)]
    else:
        for label in ("baseline", "candidate"):
            if isinstance(payload.get(label), Mapping):
                offline_runs.append({"role": label, **payload[label]})
    offline_rows = [
        [item.get(key) for key in ("role", "run_id", "application", "release_id", "version", "environment", "total", "passed", "failed", "gate_passed", "p95_latency_ms", "total_tokens", "total_cost")]
        for item in offline_runs
    ]
    links = payload.get("links") if isinstance(payload.get("links"), list) else []
    link_rows = [
        [item.get(key) for key in ("link_id", "trace_id", "feedback_id", "review_id", "promotion_id", "scenario_id", "offline_run_id")]
        for item in links if isinstance(item, Mapping)
    ]
    validation = payload.get("validation") if isinstance(payload.get("validation"), Mapping) else payload
    checks = validation.get("checks") if isinstance(validation.get("checks"), list) else []
    check_rows = [[item.get(key) for key in ("name", "actual", "threshold", "passed", "message")] for item in checks if isinstance(item, Mapping)]
    serialized = html.escape(json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True))
    sections = [
        table("Online and offline trends", ["Bucket", "Application", "Version", "Online traces", "Feedback", "Confirmed low quality", "Low quality rate", "Offline runs", "Offline pass rate", "P95 latency (ms)", "Tokens", "Cost"], trend_rows, table_id="trends"),
        table("Offline run comparison", ["Role", "Run", "Application", "Release", "Version", "Environment", "Total", "Passed", "Failed", "Gate passed", "P95 latency (ms)", "Tokens", "Cost"], offline_rows, table_id="offline-runs"),
        table("Trace to run associations", ["Link", "Trace", "Feedback", "Review", "Promotion", "Scenario", "Offline run"], link_rows, table_id="associations"),
        table("Release gate checks", ["Check", "Actual", "Threshold", "Passed", "Message"], check_rows, table_id="gate-checks"),
    ]
    document = "<!doctype html><html><head><meta charset='utf-8'><title>Quality Loop Evidence</title>" \
        "<style>body{font:15px system-ui;margin:2rem;color:#222}h1{color:" + color + "}h2{margin-top:2rem}table{border-collapse:collapse;width:100%;margin-bottom:1.5rem}th,td{border:1px solid #ddd;padding:.45rem;text-align:left;vertical-align:top}th{background:#f5f5f5}.null{color:#777}details{margin-top:2rem}pre{white-space:pre-wrap;background:#f5f5f5;border:1px solid #ddd;padding:1rem}</style></head><body><h1>" + status + "</h1>" + "".join(sections) + "<details><summary>Structured evidence JSON</summary><pre>" + serialized + "</pre></details></body></html>"
    target.write_text(document, encoding="utf-8")
    return target
