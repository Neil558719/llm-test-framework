from datetime import datetime, timezone

import pytest

from qe_platform.feedback import (
    FeedbackInput,
    FeedbackKind,
    FeedbackReview,
    ReviewAttribution,
    ReviewPriority,
    ReviewStatus,
)
from qe_platform.feedback.promotion import promote_review
from qe_platform.scenarios import load_scenario_text


def review_for(category=FeedbackKind.INACCURATE):
    feedback = FeedbackInput(category, "reporter", "ui")
    review = FeedbackReview.from_input(
        "review-1",
        "feedback-1",
        "trace-1",
        "reviewer",
        ReviewStatus.CONFIRMED,
        ReviewAttribution.MODEL,
        ReviewPriority.HIGH,
        "hash-key",
        created_at=datetime(2026, 9, 9, tzinfo=timezone.utc),
    )
    return feedback, review


def valid_scenario():
    return {
        "id": "promoted-1",
        "name": "Promoted regression",
        "tags": ["feedback", "m16"],
        "conversation": [{"user": "VPN is unavailable"}],
        "expect": {"response": {"contains": ["ticket"]}},
    }


def test_promote_review_returns_yaml_that_round_trips_through_existing_loader():
    feedback, review = review_for()

    record = promote_review(review, feedback, valid_scenario())

    assert record.scenario_id == "promoted-1"
    loaded = load_scenario_text(record.scenario_yaml, source="promotion.yaml")
    assert loaded[0].id == "promoted-1"
    assert loaded[0].conversation[0].user == "VPN is unavailable"
    assert "feedback-1" not in record.scenario_yaml


def test_promote_review_rejects_correct_feedback_or_unconfirmed_review():
    feedback, review = review_for(FeedbackKind.CORRECT)
    with pytest.raises(ValueError, match="low-quality"):
        promote_review(review, feedback, valid_scenario())

    inaccurate, pending = review_for()
    pending = FeedbackReview(
        pending.review_id,
        pending.feedback_id,
        pending.trace_id,
        pending.reviewer_fingerprint,
        ReviewStatus.PENDING,
        pending.attribution,
        pending.priority,
        pending.created_at,
        pending.updated_at,
    )
    with pytest.raises(ValueError, match="confirmed"):
        promote_review(pending, inaccurate, valid_scenario())


@pytest.mark.parametrize(
    "scenario",
    [
        {"id": "bad", "name": "Bad", "conversation": []},
        {"id": "bad", "name": "Bad", "conversation": [{"user": "Bearer token=secret"}]},
        {"id": "bad", "name": "Bad", "conversation": [{"user": "hello"}], "authorization": "x"},
    ],
)
def test_promote_review_rejects_invalid_or_sensitive_scenario(scenario):
    feedback, review = review_for()
    with pytest.raises(ValueError):
        promote_review(review, feedback, scenario)
