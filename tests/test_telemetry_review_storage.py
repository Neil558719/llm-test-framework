from datetime import datetime, timezone

from qe_platform.feedback import (
    FeedbackInput,
    FeedbackKind,
    ReviewAttribution,
    ReviewPriority,
    ReviewStatus,
)
from qe_platform.storage import SQLiteTelemetryRepository
from tests.test_telemetry_storage import trace_at, utc


def test_review_upsert_hydrates_and_updates_one_record_per_feedback(tmp_path):
    repo = SQLiteTelemetryRepository(tmp_path / "telemetry.db", hash_key="test-key")
    repo.upsert_trace(trace_at("2026-08-29T00:00:00+00:00"))
    feedback = repo.add_feedback(FeedbackInput(FeedbackKind.INACCURATE, "reporter", "ui"), "trace-1")

    first = repo.upsert_review(
        feedback.feedback_id,
        "reviewer-1",
        ReviewStatus.PENDING,
        ReviewAttribution.UNKNOWN,
        ReviewPriority.MEDIUM,
    )
    second = repo.upsert_review(
        feedback.feedback_id,
        "reviewer-2",
        ReviewStatus.CONFIRMED,
        ReviewAttribution.TOOL,
        ReviewPriority.HIGH,
    )

    assert first.review_id == second.review_id
    stored = repo.get_review(first.review_id, now=utc("2026-09-01T00:00:00+00:00"))
    assert stored is not None
    assert stored.status is ReviewStatus.CONFIRMED
    assert stored.attribution is ReviewAttribution.TOOL
    assert stored.priority is ReviewPriority.HIGH
    assert stored.reviewer_fingerprint != "reviewer-2"
    assert len(repo.list_reviews(trace_id="trace-1", now=utc("2026-09-01T00:00:00+00:00"))) == 1


def test_promotion_is_idempotent_and_cascades_with_expired_trace(tmp_path):
    repo = SQLiteTelemetryRepository(tmp_path / "telemetry.db", retention_days=30, hash_key="test-key")
    repo.upsert_trace(trace_at("2026-08-01T00:00:00+00:00"))
    feedback = repo.add_feedback(FeedbackInput(FeedbackKind.HALLUCINATION, "reporter", "ui"), "trace-1")
    review = repo.upsert_review(
        feedback.feedback_id,
        "reviewer-1",
        ReviewStatus.CONFIRMED,
        ReviewAttribution.MODEL,
        ReviewPriority.CRITICAL,
    )
    yaml_text = "id: promoted\nname: Promoted\nconversation:\n  - user: hello\n"

    first = repo.create_promotion(review.review_id, "promoted", yaml_text)
    second = repo.create_promotion(review.review_id, "promoted", yaml_text)
    assert first.promotion_id == second.promotion_id
    assert repo.get_promotion(first.promotion_id, now=utc("2026-08-30T00:00:00+00:00")) is not None
    assert repo.prune_expired(now=datetime(2026, 9, 1, tzinfo=timezone.utc)) == 1
    assert repo.get_review(review.review_id, now=utc("2026-09-01T00:00:00+00:00")) is None
    assert repo.get_promotion(first.promotion_id, now=utc("2026-09-01T00:00:00+00:00")) is None
