from __future__ import annotations

import json

from qe_platform.quality_loop.reporting import write_quality_html, write_quality_json


def test_quality_json_and_html_are_deterministic_and_escaped(tmp_path):
    payload = {
        "validation": {"passed": False, "message": "<script>alert(1)</script>"},
        "links": [{"trace_id": "trace-1", "scenario_id": "scenario-1"}],
    }
    json_path = write_quality_json(payload, tmp_path / "evidence.json")
    html_path = write_quality_html(payload, tmp_path / "evidence.html")
    assert json.loads(json_path.read_text(encoding="utf-8")) == payload
    html = html_path.read_text(encoding="utf-8")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert "https://" not in html


def test_quality_html_renders_trends_associations_offline_runs_and_gate_checks(tmp_path):
    payload = {
        "validation": {"passed": True, "checks": [{"name": "scenario_set", "actual": ["s-1"], "threshold": ["s-1"], "passed": True, "message": "ok"}]},
        "baseline": {"run_id": "run-baseline", "application": "agent", "release_id": "r1", "version": "old", "environment": "offline", "total": 1, "passed": 1, "failed": 0, "gate_passed": True, "p95_latency_ms": 10.0, "total_tokens": 4, "total_cost": 0.1},
        "candidate": {"run_id": "run-candidate", "application": "agent", "release_id": "r2", "version": "new", "environment": "offline", "total": 1, "passed": 1, "failed": 0, "gate_passed": True, "p95_latency_ms": 11.0, "total_tokens": 5, "total_cost": 0.2},
        "trends": [{"bucket": "2026-09-09", "application": "agent", "version": "new", "online_trace_count": 2, "feedback_count": 1, "confirmed_low_quality_count": 0, "low_quality_rate": 0.0, "offline_run_count": 1, "offline_pass_rate": 1.0, "p95_latency_ms": 11.0, "total_tokens": 5, "total_cost": 0.2}],
        "links": [{"link_id": "link-1", "trace_id": "trace-1", "feedback_id": "feedback-1", "review_id": "review-1", "promotion_id": "promotion-1", "scenario_id": "s-1", "offline_run_id": "run-candidate"}],
    }
    html = (tmp_path / "evidence.html")
    write_quality_html(payload, html)
    document = html.read_text(encoding="utf-8")
    for marker in ("id='trends'", "id='offline-runs'", "id='associations'", "id='gate-checks'", "trace-1", "run-candidate", "scenario_set"):
        assert marker in document
