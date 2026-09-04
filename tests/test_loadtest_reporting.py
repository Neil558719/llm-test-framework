import json

from qe_platform.loadtest.metrics import summarize
from qe_platform.loadtest.models import LoadTestConfig, LoadTestRun, SampleResult
from qe_platform.loadtest.reporting import write_reports


def test_reports_include_required_metrics_and_redact_request_secrets(tmp_path):
    config = LoadTestConfig(
        target_url="http://test", message="private incident text",
        headers={"Authorization": "Bearer top-secret"}, requests=1,
        json_report=str(tmp_path / "load.json"), html_report=str(tmp_path / "load.html"),
    )
    sample = SampleResult(True, 42, None, status_code=200, trace_id="trace-1")
    run = LoadTestRun(config, "start", "finish", [sample], summarize([sample], config, wall_time_ms=50))
    write_reports(run)
    json_text = (tmp_path / "load.json").read_text(encoding="utf-8")
    html_text = (tmp_path / "load.html").read_text(encoding="utf-8")
    payload = json.loads(json_text)
    assert payload["summary"]["latency_ms"]["p95"] == 42.0
    assert payload["samples"][0]["trace_id"] == "trace-1"
    assert "private incident text" not in json_text + html_text
    assert "top-secret" not in json_text + html_text
    assert "[REDACTED]" in json_text
    assert "P95" in html_text
    assert "TTFT" in html_text
    assert "流式中断率" in html_text
    assert "Token" in html_text
