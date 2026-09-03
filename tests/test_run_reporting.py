import json

from llmtest import ResponseEnvelope, ToolCall
from qe_platform.contracts import AssertionResult
from qe_platform.reporting import RunReport, build_run_report, write_html, write_json
from qe_platform.workflow_runner import ScenarioRunResult, StepResult


def _result(scenario_id="s1", passed=True):
    result = ScenarioRunResult(scenario_id, "Scenario", "fixture.yaml", "session-1", "2026-01-01T00:00:00Z", expected_step_count=1)
    response = ResponseEnvelope(answer="created", tool_calls=[ToolCall("create_ticket", {"category": "vpn"})], metadata={"ticket_status": "created"})
    assertion = AssertionResult("response_contains", passed, "expected text", "answer", "created", "created")
    result.steps.append(StepResult(0, "create", "passed" if passed else "failed", response, [assertion]))
    result.tool_calls.extend(response.tool_calls)
    result.final_assertions.append(assertion)
    result.finished_at = "2026-01-01T00:00:01Z"
    return result


def test_run_report_aggregates_results_and_failure_details(tmp_path):
    report = build_run_report([_result(), _result("s2", False)], run_id="run-1")
    assert isinstance(report, RunReport)
    assert report.total == 2
    assert report.passed == 1
    assert report.failed == 1
    assert report.scenarios[1]["failed_assertions"][0]["assertion_type"] == "response_contains"
    assert report.scenarios[0]["tool_calls"][0]["name"] == "create_ticket"
    path = write_json(report, tmp_path / "run.json")
    assert json.loads(path.read_text(encoding="utf-8"))["run_id"] == "run-1"


def test_html_report_is_standalone_and_contains_run_summary(tmp_path):
    report = build_run_report([_result()], run_id="run-html")
    path = write_html(report, tmp_path / "run.html")
    html = path.read_text(encoding="utf-8")
    assert "run-html" in html
    assert "create_ticket" in html
    assert "<html" in html and "https://" not in html
