"""Report integrity regressions: old-entry defects precede new v2 interfaces."""

from copy import deepcopy

import pytest

from llmtest import ResponseEnvelope
from qe_platform.quality_loop.engine import validate_release
from qe_platform.quality_loop.models import ReleaseGatePolicy, parse_run_report
from qe_platform.quality_loop.storage import SQLiteQualityRepository
from qe_platform.reporting import build_run_report
from qe_platform.scenarios import load_scenario_text
from qe_platform.workflow_runner import ScenarioRunner
from tests.test_quality_loop_engine import _setup_database
from tests.test_quality_loop_models import _report_payload
from tests.test_run_reporting import _result
from tests.test_telemetry_storage import utc
from tests.test_workflow_runner import SequenceAdapter


NOW = utc("2026-09-10T00:00:00Z")


def _native_payload(answer="answer", *, run_id="same-id"):
    spec = load_scenario_text("id: native\nname: Native\nconversation: [{user: hello}]\n")[0]
    result = ScenarioRunner(lambda setup: SequenceAdapter([ResponseEnvelope(answer=answer)])).run(spec)
    result.started_at, result.finished_at = "2026-09-09T00:00:00Z", "2026-09-09T00:00:01Z"
    return build_run_report([result], run_id=run_id, application="reference-agent", release_id="candidate",
                            version="v1", environment="offline").as_dict()


@pytest.mark.parametrize("damage", ["incomplete", "execution-error", "quality-unavailable", "failed-scenario"])
def test_existing_import_rejects_forged_gate_or_ignored_execution(damage):
    payload = _report_payload()
    row = payload["scenarios"][0]
    if damage == "incomplete":
        row["complete"] = False
    elif damage == "execution-error":
        row["steps"] = [{"index": 0, "user": "hello", "status": "error", "response": None, "error": "failed", "assertions": []}]
    elif damage == "quality-unavailable":
        row["quality_checks"] = [{"metric": "relevance", "expectation": {"min_score": .8}, "required": True,
                                  "status": "not_executed", "score": None, "threshold": .8}]
    else:
        row["passed"] = False
        payload["passed"], payload["failed"] = 1, 1
    with pytest.raises(ValueError):
        parse_run_report(payload, "fixture")


def test_existing_native_report_rejects_duplicate_scenarios():
    with pytest.raises(ValueError):
        build_run_report([_result(), _result()])


def test_existing_import_id_cannot_erase_changed_valid_execution(tmp_path):
    repository = SQLiteQualityRepository(tmp_path / "identity.db", clock=lambda: NOW)
    try:
        first = _native_payload("first valid answer")
        second = _native_payload("different valid answer")
        assert first["gate_passed"] and second["gate_passed"]
        repository.import_run(first, source_label="fixture")
        with pytest.raises(ValueError):
            repository.import_run(second, source_label="fixture")
    finally:
        repository.close()


@pytest.mark.parametrize("mismatch", ["self", "application", "environment"])
def test_existing_direct_release_rejects_incomparable_runs(tmp_path, mismatch):
    repository, baseline, _ = _setup_database(tmp_path)
    try:
        candidate_id = baseline.run_id
        if mismatch != "self":
            overrides = {"run_id": "incomparable"}
            overrides["application" if mismatch == "application" else "environment"] = "other"
            candidate_id = repository.import_run(_report_payload(**overrides), source_label="fixture").run_id
        with pytest.raises(ValueError):
            validate_release(repository, baseline.run_id, candidate_id, ReleaseGatePolicy(max_low_quality_rate_increase=1),
                             now=utc("2026-09-01T00:00:00Z"))
    finally:
        repository.close()


@pytest.mark.parametrize("damage", ["count", "duplicate-id"])
def test_preserved_existing_import_guards(damage):
    payload = _report_payload()
    if damage == "count":
        payload["total"] = 3
    else:
        payload["scenarios"][1]["scenario_id"] = payload["scenarios"][0]["scenario_id"]
    with pytest.raises(ValueError):
        parse_run_report(payload, "fixture")


def test_preserved_identical_import_is_idempotent(tmp_path):
    repository = SQLiteQualityRepository(tmp_path / "same.db", clock=lambda: NOW)
    try:
        payload = _report_payload()
        first = repository.import_run(payload, source_label="fixture")
        assert repository.import_run(deepcopy(payload), source_label="fixture") == first
    finally:
        repository.close()


def _v2_payload(*, answer="answer", run_id="v2", metric=False, scoring_assets=None, **metadata):
    from qe_platform.reporting.integrity import freeze_run_manifest
    from qe_platform.workflow_runner import QualityCheckResult
    text = "id: controlled\nname: Controlled\nconversation: [{user: hello}]\n"
    if metric:
        text += "quality: {relevance: {min_score: 0.8}}\n"
    spec = load_scenario_text(text)[0]
    plan = freeze_run_manifest([spec], scoring_assets=scoring_assets)
    evaluator = lambda s, r: [QualityCheckResult("relevance", {"min_score": .8}, "passed", .9)]
    result = ScenarioRunner(lambda setup: SequenceAdapter([ResponseEnvelope(answer=answer)]), quality_evaluator=evaluator).run(spec)
    result.started_at, result.finished_at = "2026-09-09T00:00:00Z", "2026-09-09T00:00:01Z"
    report = build_run_report([result], manifest=plan, run_id=run_id, application="reference-agent",
                              release_id="candidate", version=metadata.pop("version", "v1"),
                              environment=metadata.pop("environment", "offline"), **metadata)
    return report.as_dict(), plan


def test_v2_interface_freezes_assets_before_execution_and_is_immutable():
    from qe_platform.reporting.integrity import freeze_run_manifest
    spec = load_scenario_text("id: frozen\nname: Frozen\nconversation: [{user: original}]\n")[0]
    plan = freeze_run_manifest([spec])
    original = deepcopy(plan.as_dict())
    spec.conversation.clear()
    returned = plan.as_dict()
    returned["scenarios"].clear()
    assert plan.as_dict() == original
    assert original["scenarios"][0]["expected_steps"][0]["index"] == 0
    assert len(plan.asset_fingerprint) == 64


def test_v2_interface_external_manifest_controls_verification():
    payload, plan = _v2_payload(metric=True)
    assert payload["schema_version"] == "qe-run-v2"
    verified = parse_run_report(payload, "fixture", expected_manifest=plan)
    unverified = parse_run_report(payload, "fixture")
    assert verified.complete is True and verified.release_eligible
    assert verified.verification == "verified_v2" and verified.asset_fingerprint == plan.asset_fingerprint
    assert unverified.verification == "unverified_manifest" and not unverified.release_eligible


@pytest.mark.parametrize("damage", ["missing-scenario", "duplicate-scenario", "unexpected-scenario", "missing-step", "duplicate-step", "unexpected-step", "missing-quality", "duplicate-quality", "unexpected-quality", "forged-gate", "changed-policy"])
def test_v2_interface_rejects_missing_or_changed_controlled_evidence(damage):
    payload, plan = _v2_payload(metric=True)
    row = payload["scenarios"][0]
    if damage == "missing-scenario": payload["scenarios"] = []
    if damage == "duplicate-scenario": payload["scenarios"].append(deepcopy(row))
    if damage == "unexpected-scenario": row["scenario_id"] = "unexpected"
    if damage == "missing-step": row["steps"] = []
    if damage == "duplicate-step": row["steps"].append(deepcopy(row["steps"][0]))
    if damage == "unexpected-step": row["steps"][0]["index"] = 99
    if damage == "missing-quality": row["quality_checks"] = []
    if damage == "duplicate-quality": row["quality_checks"].append(deepcopy(row["quality_checks"][0]))
    if damage == "unexpected-quality": row["quality_checks"][0]["metric"] = "helpfulness"
    if damage == "forged-gate": payload["gate_passed"] = False
    if damage == "changed-policy": row["quality_checks"][0]["threshold"] = .1
    with pytest.raises(ValueError):
        parse_run_report(payload, "fixture", expected_manifest=plan)


def test_v2_interface_storage_resolver_is_independent_of_report(tmp_path):
    payload, plan = _v2_payload()
    seen = []
    def resolver(report):
        seen.append(report["run_id"])
        return plan
    repository = SQLiteQualityRepository(tmp_path / "resolver.db", clock=lambda: NOW, trusted_manifest_resolver=resolver)
    try:
        run = repository.import_run(payload, source_label="fixture")
        assert run.release_eligible and seen == ["v2"]
        assert repository.get_run("v2") == run
    finally:
        repository.close()


def _old_database(path):
    import json
    import sqlite3
    from qe_platform.quality_loop.storage import _create_quality_tables
    from qe_platform.storage.migrations import Migration, MigrationRunner
    connection = sqlite3.connect(path)
    MigrationRunner(connection, "quality_loop", (Migration(1, _create_quality_tables),)).apply()
    legacy = parse_run_report(_report_payload(run_id="legacy"), "fixture").as_dict()
    for key in ("complete", "asset_fingerprint", "verification", "content_sha256", "manifest_sha256", "evidence", "release_eligible"):
        legacy.pop(key)
    raw = json.dumps(legacy)
    connection.execute("INSERT INTO quality_offline_runs VALUES (?, ?, ?)", ("legacy", legacy["started_at"], raw))
    connection.execute("INSERT INTO quality_release_validations VALUES (?, ?, ?, ?, ?)",
                       ("historical", "legacy", "legacy", legacy["started_at"], '{"historical":"unchanged"}'))
    connection.execute("CREATE TABLE telemetry_promotions(promotion_id TEXT PRIMARY KEY)")
    connection.execute("INSERT INTO telemetry_promotions VALUES ('promotion-old')")
    connection.execute("INSERT INTO quality_links VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       ("link-old", "trace-old", "feedback-old", "review-old", "promotion-old", "vpn-recovery-regression", "legacy", legacy["started_at"]))
    connection.commit()
    connection.close()
    return raw


def test_migration_v2_preserves_old_bytes_and_reopens_unverified(tmp_path):
    import sqlite3
    path = tmp_path / "upgrade.db"
    raw = _old_database(path)
    for _ in range(2):
        repository = SQLiteQualityRepository(path, clock=lambda: NOW)
        try:
            version = repository._connection.execute("SELECT version FROM schema_meta WHERE component='quality_loop'").fetchone()[0]
            assert version == 2
            assert repository.get_run("legacy").verification == "legacy_unverified"
            assert not repository.get_run("legacy").release_eligible
        finally:
            repository.close()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT payload FROM quality_offline_runs").fetchone()[0] == raw
        assert connection.execute("SELECT payload FROM quality_release_validations").fetchone()[0] == '{"historical":"unchanged"}'
        assert connection.execute("SELECT link_id, promotion_id, offline_run_id FROM quality_links").fetchone() == ("link-old", "promotion-old", "legacy")


def test_migration_v2_new_proof_columns_are_not_payload_self_attestation(tmp_path):
    payload, plan = _v2_payload()
    repository = SQLiteQualityRepository(tmp_path / "proof.db", clock=lambda: NOW)
    try:
        repository.import_run(payload, source_label="fixture", expected_manifest=plan)
        repository._connection.execute("UPDATE quality_offline_runs SET verification='legacy_unverified'")
        with pytest.raises(ValueError):
            repository.get_run("v2")
    finally:
        repository.close()


@pytest.mark.parametrize("damage", ["user", "response", "assertions", "required", "expectation", "score-bool", "score-nan", "score-range", "status", "status-score", "complete", "unknown-schema", "bad-id-type", "bad-metric-type"])
def test_v2_rejects_evidence_policy_and_type_forgery(damage):
    payload, plan = _v2_payload(metric=True)
    row, check = payload["scenarios"][0], payload["scenarios"][0]["quality_checks"][0]
    if damage == "user": row["steps"][0]["user"] = "different"
    if damage == "response": row["steps"][0]["response"] = None
    if damage == "assertions": row["final_assertions"] = [{"assertion_type": "fake", "passed": True}]
    if damage == "required": check["required"] = False
    if damage == "expectation": check["expectation"] = {"min_score": .1}
    if damage == "score-bool": check["score"] = True
    if damage == "score-nan": check["score"] = float("nan")
    if damage == "score-range": check["score"] = 1.1
    if damage == "status": check["status"] = "success"
    if damage == "status-score": check["score"] = .2
    if damage == "complete": payload["complete"] = False
    if damage == "unknown-schema": payload["schema_version"] = "qe-run-v999"
    if damage == "bad-id-type": row["scenario_id"] = []
    if damage == "bad-metric-type": check["metric"] = {}
    with pytest.raises(ValueError):
        parse_run_report(payload, "fixture", expected_manifest=plan)


@pytest.mark.parametrize("change", ["input", "assertion", "tool", "threshold", "rubric"])
def test_controlled_asset_changes_require_new_baseline(tmp_path, change):
    from qe_platform.reporting.integrity import freeze_run_manifest
    first, plan = _v2_payload(run_id="baseline", metric=True)
    text = "id: controlled\nname: Controlled\nconversation: [{user: hello}]\nquality: {relevance: {min_score: 0.8}}\n"
    if change == "input": text = text.replace("hello", "changed")
    if change == "assertion": text += "expect: {response: {contains: [answer]}}\n"
    if change == "tool": text += "expect: {tools: [{name: lookup}]}\n"
    if change == "threshold": text = text.replace("0.8", "0.7")
    spec = load_scenario_text(text)[0]
    changed = freeze_run_manifest([spec], scoring_assets={"rubric": "changed"} if change == "rubric" else None)
    assert changed.asset_fingerprint != plan.asset_fingerprint
    # Both reports are legitimately verified under independently chosen plans.
    result = ScenarioRunner(lambda _: SequenceAdapter([ResponseEnvelope(answer="answer")]),
                            quality_evaluator=lambda s, r: [__import__("qe_platform.workflow_runner", fromlist=["QualityCheckResult"]).QualityCheckResult("relevance", spec.quality.metrics["relevance"], "passed", .9)]).run(spec)
    result.started_at, result.finished_at = first["started_at"], first["finished_at"]
    second = build_run_report([result], manifest=changed, run_id="candidate", application="reference-agent", release_id="next", version="v2", environment="offline").as_dict()
    repository = SQLiteQualityRepository(tmp_path / "compare.db", clock=lambda: NOW)
    try:
        repository.import_run(first, source_label="fixture", expected_manifest=plan)
        repository.import_run(second, source_label="fixture", expected_manifest=changed)
        with pytest.raises(ValueError, match="new baseline"):
            validate_release(repository, "baseline", "candidate", ReleaseGatePolicy(max_candidate_failure_rate=1, max_pass_rate_drop=1))
    finally:
        repository.close()


def test_model_versions_may_change_with_same_controlled_assets(tmp_path):
    from qe_platform.storage import SQLiteTelemetryRepository
    first, plan = _v2_payload(run_id="baseline", version="model-prompt-old")
    second, other = _v2_payload(run_id="candidate", version="model-prompt-new")
    second["scenarios"][0]["model_versions"] = [{"provider": "offline", "model": "new", "prompt": "new"}]
    assert plan == other
    telemetry = SQLiteTelemetryRepository(tmp_path / "versions.db", clock=lambda: NOW)
    repository = SQLiteQualityRepository(tmp_path / "versions.db", clock=lambda: NOW)
    try:
        repository.import_run(first, source_label="fixture", expected_manifest=plan)
        repository.import_run(second, source_label="fixture", expected_manifest=plan)
        result = validate_release(repository, "baseline", "candidate", ReleaseGatePolicy())
        assert result.passed and result.report_policy_version == 2
    finally:
        repository.close()
        telemetry.close()


@pytest.mark.parametrize("trusted", [False, True])
def test_http_trust_is_server_injected_and_cannot_be_self_uploaded(tmp_path, trusted):
    from fastapi.testclient import TestClient
    from qe_platform.auth.dependencies import AuthRuntime
    from qe_platform.telemetry.api import create_telemetry_app
    from qe_platform.telemetry.settings import TelemetrySettings
    payload, plan = _v2_payload()
    path = tmp_path / "http.db"
    repository = SQLiteQualityRepository(path, clock=lambda: NOW)
    app = create_telemetry_app(TelemetrySettings(str(path), "local-hash", "local-token"), quality_repository=repository,
                               auth_runtime=AuthRuntime.disabled(), trusted_manifest_resolver=(lambda _: plan) if trusted else None)
    client = TestClient(app)
    try:
        headers = {"X-QE-Telemetry-Token": "local-token"}
        bad = client.post("/api/quality/offline-runs", headers=headers, json={**payload, "expected_manifest": plan.as_dict()})
        assert bad.status_code == 400
        response = client.post("/api/quality/offline-runs", headers=headers, json=payload)
        assert response.status_code == 201
        assert response.json()["release_eligible"] is trusted
    finally:
        repository.close()


def test_quality_v2_backup_restore_readiness_and_expiry(tmp_path):
    from datetime import timedelta
    from qe_platform.ops.backup import backup_database
    from qe_platform.ops.restore import restore_database
    from qe_platform.ops.readiness import readiness
    source, backup, target = (tmp_path / name for name in ("source.db", "backup.db", "restored.db"))
    payload, plan = _v2_payload()
    repository = SQLiteQualityRepository(source, clock=lambda: NOW)
    repository.import_run(payload, source_label="fixture", expected_manifest=plan)
    assert readiness({"quality": repository}).ready
    result = backup_database(source, backup)
    assert result.schema_versions == {"quality_loop": 2}
    repository.close()
    restore_database(backup, target, {"quality_loop": 2})
    restored = SQLiteQualityRepository(target, clock=lambda: NOW)
    try:
        assert restored.get_run("v2").release_eligible
        assert restored.get_run("v2", now=NOW + timedelta(days=31)) is None
        assert readiness({"quality": restored}).ready
    finally:
        restored.close()


def test_migration_v2_failure_rolls_back_schema_and_old_bytes(tmp_path, monkeypatch):
    import sqlite3
    import qe_platform.quality_loop.storage as storage
    from qe_platform.storage.migrations import Migration, MigrationRunner
    path = tmp_path / "rollback.db"
    raw = _old_database(path)
    def fail(connection):
        storage._add_report_proof(connection)
        raise RuntimeError("injected migration failure")
    with sqlite3.connect(path) as connection:
        with pytest.raises(RuntimeError, match="injected"):
            MigrationRunner(connection, "quality_loop", (Migration(1, storage._create_quality_tables), Migration(2, fail))).apply()
        assert connection.execute("SELECT version FROM schema_meta WHERE component='quality_loop'").fetchone()[0] == 1
        assert [r[1] for r in connection.execute("PRAGMA table_info(quality_offline_runs)")] == ["run_id", "started_at", "payload"]
        assert connection.execute("SELECT payload FROM quality_offline_runs").fetchone()[0] == raw


def test_html_exposes_legacy_verification_and_release_ineligibility(tmp_path):
    from qe_platform.reporting import write_html
    report = build_run_report([_result()])
    text = write_html(report, tmp_path / "legacy.html").read_text(encoding="utf-8")
    assert "legacy_unverified" in text
    assert "Release eligible: false" in text
    assert "Reported gate: true" in text


def test_v2_incomplete_quality_is_readable_but_cannot_release(tmp_path):
    from qe_platform.reporting.integrity import freeze_run_manifest
    spec = load_scenario_text("id: grounded\nname: Grounded\nconversation: [{user: hello}]\nquality: {faithfulness: {min_score: 0.8}}\n")[0]
    plan = freeze_run_manifest([spec])
    calls = []
    result = ScenarioRunner(lambda _: SequenceAdapter([ResponseEnvelope(answer="answer")]), quality_evaluator=lambda *args: calls.append(args)).run(spec)
    payload = build_run_report([result], manifest=plan, application="app", release_id="next", version="v1").as_dict()
    assert not calls and not payload["complete"] and not payload["gate_passed"]
    run = parse_run_report(payload, "fixture", expected_manifest=plan)
    assert run.verification == "verified_v2" and not run.release_eligible
    forged = deepcopy(payload)
    row = forged["scenarios"][0]
    row["quality_checks"][0].update(status="passed", score=.9)
    row.update(passed=True, complete=True)
    forged.update(passed=1, failed=0, complete=True, gate_passed=True)
    with pytest.raises(ValueError):
        parse_run_report(forged, "fixture", expected_manifest=plan)


def test_v2_projection_persists_hashes_not_questions_answers_or_sources():
    payload, plan = _v2_payload(answer="private answer unique")
    run = parse_run_report(payload, "fixture", expected_manifest=plan)
    import json
    serialized = json.dumps(run.as_dict())
    assert "private answer unique" not in serialized and "hello" not in serialized


@pytest.mark.parametrize("failure", ["adapter", "middle", "inconclusive"])
def test_native_v2_preserves_real_incomplete_execution_evidence(failure):
    from qe_platform.reporting.integrity import freeze_run_manifest
    from qe_platform.workflow_runner import QualityCheckResult
    spec = load_scenario_text("""id: interrupted
name: Interrupted
conversation:
  - user: first
  - user: second
  - user: third
expect: {response: {contains: [answer]}}
quality: {relevance: {min_score: 0.8}}
""")[0]
    plan = freeze_run_manifest([spec])
    class Adapter:
        count = 0
        def send(self, *args, **kwargs):
            self.count += 1
            if failure == "middle" and self.count == 2:
                raise RuntimeError("controlled execution failure")
            return ResponseEnvelope(answer="answer")
    def factory(_):
        if failure == "adapter":
            raise RuntimeError("controlled adapter failure")
        return Adapter()
    result = ScenarioRunner(factory, quality_evaluator=lambda *args: [QualityCheckResult("relevance", {"min_score": .8}, "inconclusive")]).run(spec)
    payload = build_run_report([result], manifest=plan, application="app", release_id="next", version="v1").as_dict()
    assert not payload["complete"] and not payload["gate_passed"]
    assert len(payload["scenarios"][0]["steps"]) == {"adapter": 1, "middle": 2, "inconclusive": 3}[failure]
    assert not parse_run_report(payload, "fixture", expected_manifest=plan).release_eligible
    forged = deepcopy(payload)
    forged["scenarios"][0].update(complete=True, passed=True)
    forged.update(complete=True, passed=1, failed=0, gate_passed=True)
    with pytest.raises(ValueError):
        parse_run_report(forged, "fixture", expected_manifest=plan)


def test_manifest_default_scoring_assets_use_actual_judge_rubric():
    from llmtest import JudgeSpec
    _, plan = _v2_payload(metric=True)
    assets = plan.as_dict()["scoring_assets"]
    assert assets["judge_rubrics"]["relevance"]["criteria"] == JudgeSpec.relevance().criteria


def test_quality_html_does_not_label_historical_pass_as_verified_release(tmp_path):
    from qe_platform.quality_loop.reporting import write_quality_html
    run = parse_run_report(_report_payload(), "fixture").as_dict()
    text = write_quality_html({"passed": True, "candidate": run}, tmp_path / "quality.html").read_text(encoding="utf-8")
    assert "REPORTED PASSED" in text and "UNVERIFIED" in text
    assert "Verification" in text and "Release eligible" in text


@pytest.mark.parametrize("damage", ["downgrade", "answer", "sources", "usage", "quality-provider"])
def test_v2_strict_evidence_cannot_downgrade_or_coerce_types(damage):
    payload, plan = _v2_payload(metric=True)
    row = payload["scenarios"][0]
    if damage == "downgrade": payload.pop("schema_version")
    if damage == "answer": row["steps"][0]["response"]["answer"] = True
    if damage == "sources": row["steps"][0]["response"]["sources"] = "not an array"
    if damage == "usage": row["usage"] = {"prompt_tokens": "12"}
    if damage == "quality-provider": row["quality_checks"][0]["provider"] = []
    with pytest.raises(ValueError):
        parse_run_report(payload, "fixture")


def test_v2_safe_projection_keeps_explicit_mock_provenance_visible():
    payload, plan = _v2_payload(metric=True)
    payload["scenarios"][0]["quality_checks"][0].update(provider="mock", model="offline-fixture", version="judge-v1")
    run = parse_run_report(payload, "fixture", expected_manifest=plan)
    provenance = run.evidence["scenarios"][0]["quality"][0]
    assert provenance["provider"] == "mock" and provenance["model"] == "offline-fixture"


def test_manifest_exposes_case_and_quality_policy_digests():
    from qe_platform.reporting.integrity import digest
    _, plan = _v2_payload(metric=True)
    case = plan.as_dict()["scenarios"][0]
    assert case["scenario_sha256"] == digest(case["controls"])
    assert case["quality_policy_sha256"] == digest(case["quality"])


def test_migration_v2_persists_completion_and_asset_fingerprint_separately(tmp_path):
    payload, plan = _v2_payload()
    repository = SQLiteQualityRepository(tmp_path / "columns.db", clock=lambda: NOW)
    try:
        repository.import_run(payload, source_label="fixture", expected_manifest=plan)
        row = repository._connection.execute("SELECT complete, asset_fingerprint FROM quality_offline_runs").fetchone()
        assert row == (1, plan.asset_fingerprint)
        repository._connection.execute("UPDATE quality_offline_runs SET complete=0")
        with pytest.raises(ValueError):
            repository.get_run("v2")
    finally:
        repository.close()


def test_old_reader_rollback_requires_matching_pre_migration_snapshot(tmp_path):
    import sqlite3
    from qe_platform.ops.backup import backup_database
    from qe_platform.ops.restore import restore_database, RestoreError
    from qe_platform.quality_loop.storage import _create_quality_tables
    from qe_platform.storage.migrations import Migration, MigrationRunner
    source, before, after, target = (tmp_path / n for n in ("source.db", "before.db", "after.db", "target.db"))
    _old_database(source)
    backup_database(source, before)
    repository = SQLiteQualityRepository(source, clock=lambda: NOW)
    repository.close()
    backup_database(source, after)
    with pytest.raises(RestoreError, match="schema version"):
        restore_database(after, target, {"quality_loop": 1})
    restore_database(before, target, {"quality_loop": 1})
    with sqlite3.connect(target) as connection:
        assert MigrationRunner(connection, "quality_loop", (Migration(1, _create_quality_tables),)).apply() == 1
        assert connection.execute("SELECT link_id FROM quality_links").fetchone() == ("link-old",)


def test_safe_projection_records_sut_versions_as_experimental_metadata():
    payload, plan = _v2_payload()
    payload["scenarios"][0]["steps"][0]["response"]["model_version"] = {
        "provider": "offline", "model": "candidate-model", "prompt": "candidate-prompt", "knowledge_base": "kb-v2", "tools": "tools-v2"}
    run = parse_run_report(payload, "fixture", expected_manifest=plan)
    versions = run.evidence["scenarios"][0]["steps"][0]["model_version"]
    assert versions["model"] == "candidate-model" and versions["prompt"] == "candidate-prompt"