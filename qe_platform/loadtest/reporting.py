from __future__ import annotations

import html
import json
from pathlib import Path

from .models import LoadTestRun


def write_reports(run: LoadTestRun) -> tuple[Path, Path]:
    json_path = Path(run.config.json_report)
    html_path = Path(run.config.html_report)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    payload = run.as_dict()
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = run.summary
    status_summary = html.escape(json.dumps(summary.status_codes, ensure_ascii=False, sort_keys=True))
    error_summary = html.escape(json.dumps(summary.errors, ensure_ascii=False, sort_keys=True))
    rows = "".join(
        f"<tr><td>{index}</td><td>{'OK' if sample.success else 'ERROR'}</td>"
        f"<td>{sample.duration_ms:.3f}</td><td>{sample.ttft_ms if sample.ttft_ms is not None else '-'}</td>"
        f"<td>{sample.status_code or '-'}</td><td>{html.escape(sample.error_type)}</td>"
        f"<td>{html.escape(sample.trace_id)}</td></tr>"
        for index, sample in enumerate(run.samples, 1)
    )
    document = f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>Load Test Report</title>
<style>body{{font-family:system-ui;margin:2rem;color:#172033}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1rem}}.card{{padding:1rem;border:1px solid #ccd5e0;border-radius:8px}}table{{width:100%;border-collapse:collapse;margin-top:1rem}}th,td{{padding:.5rem;border-bottom:1px solid #ddd;text-align:left}}</style></head>
<body><h1>独立压测报告</h1><p>{html.escape(run.started_at)} — {html.escape(run.finished_at)}</p>
<div class='grid'><div class='card'>并发<br><strong>{run.config.concurrency}</strong></div><div class='card'>吞吐 RPS<br><strong>{summary.throughput_rps}</strong></div><div class='card'>P50<br><strong>{summary.latency_ms['p50']}</strong></div><div class='card'>P95<br><strong>{summary.latency_ms['p95']}</strong></div><div class='card'>P99<br><strong>{summary.latency_ms['p99']}</strong></div><div class='card'>TTFT P50<br><strong>{summary.ttft_ms['p50']}</strong></div><div class='card'>TTFT P95<br><strong>{summary.ttft_ms['p95']}</strong></div><div class='card'>TTFT P99<br><strong>{summary.ttft_ms['p99']}</strong></div><div class='card'>错误率<br><strong>{summary.error_rate:.2%}</strong></div><div class='card'>429 比例<br><strong>{summary.rate_429:.2%}</strong></div><div class='card'>流式中断率<br><strong>{summary.stream_interruption_rate:.2%}</strong></div><div class='card'>Token<br><strong>{summary.total_tokens}</strong></div><div class='card'>总成本<br><strong>{summary.cost_total if summary.cost_total is not None else '-'} {html.escape(summary.cost_currency)}</strong></div><div class='card'>价格版本<br><strong>{html.escape(summary.price_version)}</strong></div></div>
<p>HTTP 状态分布：<code>{status_summary}</code></p><p>错误分类：<code>{error_summary}</code></p>
<h2>样本</h2><table><thead><tr><th>#</th><th>状态</th><th>延迟 ms</th><th>TTFT ms</th><th>HTTP</th><th>错误</th><th>Trace</th></tr></thead><tbody>{rows}</tbody></table></body></html>"""
    html_path.write_text(document, encoding="utf-8")
    return json_path, html_path
