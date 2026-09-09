from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from qe_platform.feedback import FeedbackInput, FeedbackKind, ReviewAttribution, ReviewPriority, ReviewStatus
from qe_platform.quality_loop.models import ReleaseCheck, ReleaseGatePolicy, ReleaseValidation
from qe_platform.quality_loop.storage import SQLiteQualityRepository
from qe_platform.storage import SQLiteTelemetryRepository, create_telemetry_repository
from tests.test_quality_loop_models import _report_payload
from tests.test_telemetry_storage import trace_at, utc


def _promoted(repo: SQLiteTelemetryRepository, *, trace_timestamp: str = "2026-08-29T00:00:00+00:00"):
    repo.upsert_trace(trace_at(trace_timestamp))
    feedback = repo.add_feedback(FeedbackInput(FeedbackKind.HALLUCINATION, "reporter", "ui"), "trace-1")
    review = repo.upsert_review(
        feedback.feedback_id,
        "reviewer",
        ReviewStatus.CONFIRMED,
        ReviewAttribution.MODEL,
        ReviewPriority.HIGH,
    )
    return repo.create_promotion(
        review.review_id,
        "vpn-recovery-regression",
        "id: vpn-recovery-regression\nname: VPN recovery\nconversation:\n  - user: hello\n",
    )


def test_offline_run_import_is_idempotent_and_filters_sensitive_payload(tmp_path):
    repository = SQLiteQualityRepository(tmp_path / "telemetry.db")
    first = repository.import_run(_report_payload(), source_label="fixture")
    second = repository.import_run(_report_payload(), source_label="fixture")
    assert first == second
    assert repository.get_run(first.run_id) == first
    assert repository.list_runs() == [first]

    with pytest.raises(ValueError, match="forbidden|sensitive"):
        repository.import_run(_report_payload(scenarios=[{"scenario_id": "s", "answer": "raw answer"}]), source_label="fixture")

    with pytest.raises(ValueError, match="expired"):
        repository.import_run(
            _report_payload(
                run_id="expired-run",
                started_at="2026-07-01T00:00:00Z",
                finished_at="2026-07-01T00:00:02Z",
            ),
            source_label="fixture",
            now=utc("2026-09-01T00:00:00+00:00"),
        )

    with pytest.raises(ValueError, match="sensitive"):
        repository.import_run(_report_payload(run_id="sensitive-label"), source_label="Authorization: Bearer secret")


def test_link_requires_matching_unexpired_promotion_and_scenario(tmp_path):
    database = tmp_path / "telemetry.db"
    telemetry = SQLiteTelemetryRepository(database, retention_days=30, hash_key="test-key")
    promotion = _promoted(telemetry)
    quality = SQLiteQualityRepository(database, retention_days=30)
    quality.import_run(_report_payload(), source_label="fixture")

    link = quality.create_link(promotion.promotion_id, "run-candidate", now=utc("2026-09-01T00:00:00+00:00"))
    assert link.trace_id == "trace-1"
    assert link.feedback_id == promotion.feedback_id
    assert quality.create_link(promotion.promotion_id, "run-candidate", now=utc("2026-09-01T00:00:00+00:00")) == link

    with pytest.raises(ValueError, match="scenario"):
        quality.create_link(promotion.promotion_id, "run-candidate", scenario_id="wrong", now=utc("2026-09-01T00:00:00+00:00"))

    with pytest.raises(KeyError, match="promotion"):
        quality.create_link("missing", "run-candidate", now=utc("2026-09-01T00:00:00+00:00"))


def test_link_hides_expired_online_chain_but_keeps_offline_run(tmp_path):
    database = tmp_path / "telemetry.db"
    telemetry = SQLiteTelemetryRepository(database, retention_days=30, hash_key="test-key")
    promotion = _promoted(telemetry)
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE telemetry_traces SET timestamp = ?", ("2026-07-01T00:00:00.000000Z",))
        connection.commit()
    quality = SQLiteQualityRepository(database, retention_days=30)
    quality.import_run(_report_payload(), source_label="fixture")
    with pytest.raises(KeyError, match="promotion"):
        quality.create_link(promotion.promotion_id, "run-candidate", now=utc("2026-09-01T00:00:00+00:00"))
    assert quality.get_run("run-candidate") is not None
    assert quality.list_links() == []


def test_release_validation_is_persisted_and_hydrated(tmp_path):
    repository = SQLiteQualityRepository(tmp_path / "telemetry.db")
    value = ReleaseValidation(
        validation_id="validation-1",
        baseline_run_id="baseline",
        candidate_run_id="candidate",
        policy=ReleaseGatePolicy(),
        passed=True,
        checks=(ReleaseCheck("complete", True, True, True, "complete"),),
        linked_count=1,
        created_at="2026-09-09T00:00:00Z",
    )
    assert repository.save_validation(value) == value
    assert repository.get_validation("validation-1") == value
    assert repository.save_validation(value) == value


def test_storage_rejects_invalid_validation_id(tmp_path):
    repository = SQLiteQualityRepository(tmp_path / "telemetry.db")
    with pytest.raises(ValueError):
        repository.get_validation("")


def test_quality_repository_uses_the_same_file_for_sqlite_uri(tmp_path):
    uri = f"sqlite:///{(tmp_path / 'uri.db').as_posix()}"
    telemetry = create_telemetry_repository(uri, hash_key="test-key")
    telemetry.upsert_trace(trace_at("2026-08-29T00:00:00+00:00"))
    quality = SQLiteQualityRepository(uri)
    assert quality.online_rows(now=utc("2026-09-01T00:00:00+00:00"))[0]["trace_id"] == "trace-1"
