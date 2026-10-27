"""Explicitly trusted v2 fixtures; legacy summary fixtures remain separate."""
from copy import deepcopy

from llmtest import ResponseEnvelope
from qe_platform.reporting import build_run_report
from qe_platform.reporting.integrity import freeze_run_manifest
from qe_platform.scenarios import load_scenario_text
from qe_platform.workflow_runner import ScenarioRunner
from tests.test_quality_loop_models import _report_payload
from tests.test_workflow_runner import SequenceAdapter


def trusted_plan():
    return freeze_run_manifest(_specs())


def _specs():
    return [load_scenario_text(f"id: {scenario_id}\nname: Fixture\nconversation: [{{user: hello, expect: {{response: {{contains: [ok]}}}}}}]\n")[0]
            for scenario_id in ("vpn-recovery-regression", "ticket-create-vpn")]


def verified_payload(**overrides):
    legacy = _report_payload(**overrides)
    plan = trusted_plan()
    specs = _specs()
    results = []
    for spec, old in zip(specs, legacy["scenarios"]):
        result = ScenarioRunner(lambda _: SequenceAdapter([ResponseEnvelope(answer="ok" if old["passed"] else "bad")])).run(spec)
        result.started_at, result.finished_at = legacy["started_at"], legacy["finished_at"]
        results.append(result)
    report = build_run_report(results, manifest=plan, **{k: legacy[k] for k in ("run_id", "application", "release_id", "version", "environment")}).as_dict()
    for row, old in zip(report["scenarios"], legacy["scenarios"]):
        for key in ("usage", "cost", "latency_ms"):
            if key in old:
                row[key] = deepcopy(old[key])
    return report