from pathlib import Path

from qe_platform.adapters import ReferenceAgentAdapter
from qe_platform.scenarios import load_scenarios
from qe_platform.workflow_runner import ScenarioRunner


ASSET_DIR = Path(__file__).parents[1] / "qe_platform" / "scenarios" / "assets" / "reference_agent"


def test_builtin_assets_load_and_execute_all_reference_agent_workflows():
    scenarios = load_scenarios(ASSET_DIR)
    assert {scenario.id for scenario in scenarios} == {
        "knowledge-hit", "knowledge-refusal", "knowledge-timeout",
        "ticket-create", "ticket-asset-required", "ticket-user-missing",
        "ticket-owner-denied", "ticket-idempotent", "ticket-service-5xx",
        "access-create", "access-multiturn", "access-handoff",
        "access-user-missing", "access-service-5xx",
    }
    results = [ScenarioRunner(ReferenceAgentAdapter.from_setup).run(scenario) for scenario in scenarios]
    assert all(result.passed for result in results)
    assert all(result.complete for result in results)


def test_builtin_assets_are_package_yaml_files():
    assert sorted(path.suffix for path in ASSET_DIR.glob("*.yaml")) == [".yaml", ".yaml", ".yaml"]
