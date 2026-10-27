from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from qe_platform.feedback import FeedbackInput, FeedbackKind, FeedbackQuery, ReviewAttribution, ReviewPriority, ReviewStatus
from qe_platform.quality_loop.engine import validate_release
from qe_platform.quality_loop.models import ReleaseGatePolicy
from qe_platform.quality_loop.storage import SQLiteQualityRepository
from qe_platform.storage import SQLiteTelemetryRepository
from qe_platform.telemetry import TelemetryQuery
from qe_platform.telemetry.api import create_telemetry_app
from qe_platform.telemetry.settings import TelemetrySettings
from tests.test_quality_loop_models import _report_payload
from tests.report_integrity_fixtures import verified_payload, trusted_plan
from tests.test_telemetry_storage import trace_at, utc


SCENARIO = "id: vpn-recovery-regression\nname: VPN recovery\nconversation:\n  - user: hello\n"


def review(repo, feedback_id, **kwargs):
    return repo.upsert_review(feedback_id, "reviewer", ReviewStatus.CONFIRMED, ReviewAttribution.MODEL, ReviewPriority.HIGH, **kwargs)


def seed(repo, timestamp="2026-08-29T00:00:00+00:00"):
    repo.upsert_trace(trace_at(timestamp))
    feedback = repo.add_feedback(FeedbackInput(FeedbackKind.INACCURATE, "reporter", "ui"), "trace-1")
    return feedback, review(repo, feedback.feedback_id)


def test_review_respects_injected_clock(tmp_path):
    current = [utc("2026-09-01T00:00:00+00:00")]
    repo = SQLiteTelemetryRepository(tmp_path / "t.db", hash_key="test", clock=lambda: current[0])
    feedback, first = seed(repo)
    assert feedback.created_at == first.created_at == first.updated_at == current[0]
    current[0] = utc("2026-09-02T00:00:00+00:00")
    updated = review(repo, feedback.feedback_id)
    assert updated.created_at == first.created_at
    assert updated.updated_at == current[0]
    assert repo.get_review(first.review_id) is not None
    current[0] = utc("2026-10-20T00:00:00+00:00")
    assert repo.get_review(first.review_id) is None


@pytest.mark.parametrize("timestamp,current,visible", [
    ("2026-08-29T00:00:00+00:00", "2026-09-27T23:59:59.999999+00:00", True),
    ("2026-08-29T00:00:00+00:00", "2026-09-28T00:00:00+00:00", False),
    ("2026-08-29T00:00:00+00:00", "2026-09-28T00:00:00.000001+00:00", False),
    ("2024-02-29T00:00:00+00:00", "2024-03-29T23:59:59.999999+00:00", True),
    ("2024-02-29T00:00:00+00:00", "2024-03-30T00:00:00+00:00", False),
])
def test_retention_boundaries_apply_to_all_reads_and_writes(tmp_path, timestamp, current, visible):
    clock = [utc(timestamp)]
    repo = SQLiteTelemetryRepository(tmp_path / "t.db", clock=lambda: clock[0])
    feedback, item = seed(repo, timestamp)
    promotion = repo.create_promotion(item.review_id, "vpn-recovery-regression", SCENARIO)
    assert promotion.created_at == clock[0]
    clock[0] = utc(current)
    assert (repo.get_trace("trace-1") is not None) is visible
    assert bool(repo.list_traces(TelemetryQuery(trace_id="trace-1"))) is visible
    assert (repo.get_feedback(feedback.feedback_id) is not None) is visible
    assert bool(repo.list_feedback(FeedbackQuery(trace_id="trace-1"))) is visible
    assert (repo.get_review(item.review_id) is not None) is visible
    assert bool(repo.list_reviews()) is visible
    assert (repo.get_promotion(promotion.promotion_id) is not None) is visible
    assert (repo.get_promotion_for_review(item.review_id) is not None) is visible
    if visible:
        assert review(repo, feedback.feedback_id).review_id == item.review_id
        assert repo.create_promotion(item.review_id, "vpn-recovery-regression", SCENARIO) == promotion
    else:
        with pytest.raises(KeyError):
            review(repo, feedback.feedback_id)
        with pytest.raises(KeyError):
            repo.create_promotion(item.review_id, "vpn-recovery-regression", SCENARIO)
    assert repo.prune_expired(now=clock[0]) == (0 if visible else 1)


def test_quality_clock_controls_import_links_and_validation(tmp_path):
    current = [utc("2026-09-01T00:00:00+00:00")]
    database = tmp_path / "t.db"
    telemetry = SQLiteTelemetryRepository(database, clock=lambda: current[0])
    _, item = seed(telemetry)
    promotion = telemetry.create_promotion(item.review_id, "vpn-recovery-regression", SCENARIO)
    quality = SQLiteQualityRepository(database, clock=lambda: current[0])
    plan = trusted_plan()
    report = verified_payload()
    baseline = quality.import_run(verified_payload(run_id="clock-baseline"), source_label="fixture", expected_manifest=plan)
    run = quality.import_run(report, source_label="fixture", expected_manifest=plan)
    assert baseline.release_eligible and run.release_eligible
    link = quality.create_link(promotion.promotion_id, run.run_id)
    assert link.created_at == "2026-09-01T00:00:00.000000Z"
    result = validate_release(quality, baseline.run_id, run.run_id, ReleaseGatePolicy())
    assert result.created_at == "2026-09-01T00:00:00.000000Z"
    assert quality.get_run(run.run_id) == run
    assert quality.list_links() == [link]
    assert quality.online_rows()
    current[0] = utc("2026-10-20T00:00:00+00:00")
    assert quality.get_run(run.run_id) is None
    assert quality.list_runs() == quality.list_links() == quality.online_rows() == []
    with pytest.raises(ValueError, match="expired"):
        quality.import_run(report, source_label="fixture", expected_manifest=plan)
    with pytest.raises(KeyError):
        quality.create_link(promotion.promotion_id, run.run_id)
    explicit = utc("2026-09-01T00:00:00+00:00")
    assert quality.get_run(run.run_id, now=explicit) == run
    assert quality.list_links(now=explicit) == [link]
    assert quality.import_run(report, source_label="fixture", now=explicit, expected_manifest=plan) == run
    assert quality.create_link(promotion.promotion_id, run.run_id, now=explicit) == link
    assert validate_release(quality, baseline.run_id, run.run_id, ReleaseGatePolicy(), now=explicit).created_at == link.created_at


@pytest.mark.parametrize("current,accepted", [
    ("2026-09-27T23:59:59.999999+00:00", True),
    ("2026-09-28T00:00:00+00:00", False),
    ("2026-09-28T00:00:00.000001+00:00", False),
    ("2024-03-30T00:00:00+00:00", False),
])
def test_offline_import_rejects_at_or_after_cutoff(tmp_path, current, accepted):
    started = "2024-02-29T00:00:00Z" if current.startswith("2024") else "2026-08-29T00:00:00Z"
    finished = started.replace("00:00:00Z", "00:00:02Z")
    repo = SQLiteQualityRepository(tmp_path / "t.db", clock=lambda: utc(current))
    payload = _report_payload(started_at=started, finished_at=finished)
    if accepted:
        assert repo.import_run(payload, source_label="fixture").run_id == payload["run_id"]
    else:
        with pytest.raises(ValueError, match="expired"):
            repo.import_run(payload, source_label="fixture")


def test_explicit_now_overrides_clock_for_review_and_promotion(tmp_path):
    early = utc("2026-09-01T00:00:00+00:00")
    repo = SQLiteTelemetryRepository(tmp_path / "t.db", clock=lambda: utc("2026-10-20T00:00:00+00:00"))
    repo.upsert_trace(trace_at("2026-08-29T00:00:00+00:00"))
    feedback = repo.add_feedback(FeedbackInput(FeedbackKind.INACCURATE, "reporter", "ui"), "trace-1", now=early)
    item = review(repo, feedback.feedback_id, now=early)
    promotion = repo.create_promotion(item.review_id, "vpn-recovery-regression", SCENARIO, now=early)
    assert feedback.created_at == item.updated_at == promotion.created_at == early
    assert repo.get_review(item.review_id) is None
    assert repo.get_review(item.review_id, now=early) is not None
    assert repo.get_promotion(promotion.promotion_id, now=early) is not None


def test_api_uses_repository_clocks_for_reads_and_writes(tmp_path):
    current = [utc("2026-09-01T00:00:00+00:00")]
    database = tmp_path / "t.db"
    telemetry = SQLiteTelemetryRepository(database, clock=lambda: current[0])
    quality = SQLiteQualityRepository(database, clock=lambda: current[0])
    feedback, item = seed(telemetry)
    app = create_telemetry_app(TelemetrySettings(str(database), "test", "ingest", 30), telemetry, quality)
    client = TestClient(app)
    assert client.get("/api/traces/trace-1").status_code == 200
    assert client.get("/api/traces", params={"trace_id": "trace-1"}).json()["traces"]
    assert client.get("/api/feedback", params={"trace_id": "trace-1"}).json()["feedback"]
    assert client.get(f"/api/reviews/{item.review_id}").status_code == 200
    payload = {**_report_payload(), "source_label": "fixture"}
    assert client.post("/api/quality/offline-runs", headers={"X-QE-Telemetry-Token": "ingest"}, json=payload).status_code == 201
    current[0] = utc("2026-10-20T00:00:00+00:00")
    assert client.get("/api/traces/trace-1").status_code == 404
    assert client.get(f"/api/reviews/{item.review_id}").status_code == 404


@pytest.mark.parametrize("existing", [False, True])
def test_expired_review_cannot_create_or_replay_promotion(tmp_path, existing):
    current = [utc("2026-09-01T00:00:00+00:00")]
    repo = SQLiteTelemetryRepository(tmp_path / "t.db", clock=lambda: current[0])
    _, item = seed(repo)
    if existing:
        repo.create_promotion(item.review_id, "vpn-recovery-regression", SCENARIO)
    current[0] = utc("2026-09-28T00:00:00+00:00")
    with pytest.raises(KeyError, match="review not found"):
        repo.create_promotion(item.review_id, "vpn-recovery-regression", SCENARIO)


@pytest.mark.parametrize("host_date", ["2026-09-01T00:00:00+00:00", "2026-10-20T00:00:00+00:00", "2028-02-29T00:00:00+00:00"])
def test_fixed_fixture_keeps_same_conclusion_across_host_dates(tmp_path, monkeypatch, host_date):
    import qe_platform.time as time_module

    class HostDate(datetime):
        @classmethod
        def now(cls, tz=None):
            return utc(host_date)

    monkeypatch.setattr(time_module, "datetime", HostDate)
    # Only the shared wall-clock provider changes; application time remains fixed.
    repo = SQLiteTelemetryRepository(tmp_path / "t.db", clock=lambda: utc("2026-09-01T00:00:00+00:00"))
    _, item = seed(repo)
    assert repo.get_review(item.review_id) == item
    assert repo.get_trace("trace-1") is not None


@pytest.mark.parametrize("repository", [SQLiteTelemetryRepository, SQLiteQualityRepository])
@pytest.mark.parametrize("bad_time", [datetime(2026, 9, 1), datetime.fromisoformat("2026-09-01T00:00:00+08:00")])
def test_repository_rejects_non_utc_clock_results(tmp_path, repository, bad_time):
    repo = repository(tmp_path / "t.db", clock=lambda: bad_time)
    with pytest.raises(ValueError, match="UTC"):
        if repository is SQLiteTelemetryRepository:
            repo.get_trace("trace-1")
        else:
            repo.list_runs()
