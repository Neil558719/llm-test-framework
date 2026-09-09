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

