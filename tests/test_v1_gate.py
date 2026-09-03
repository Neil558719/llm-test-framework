import json

from qe_platform.v1_gate import run_gate


ASSETS = "qe_platform/scenarios/assets/reference_agent"


def test_v1_gate_executes_packaged_api_scenarios_and_writes_reports(tmp_path):
    code = run_gate(asset_dir=ASSETS, json_path=tmp_path / "run.json", html_path=tmp_path / "run.html")
    assert code == 0
    payload = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert payload["total"] == 14
    assert payload["passed"] == 14
    assert payload["gate_passed"] is True
    assert (tmp_path / "run.html").exists()


def test_v1_gate_can_fail_for_a_subset_with_a_bad_scenario_id(tmp_path):
    code = run_gate(asset_dir=ASSETS, scenario_ids={"does-not-exist"}, json_path=tmp_path / "run.json", html_path=tmp_path / "run.html")
    assert code == 1
    payload = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert payload["gate_passed"] is False
