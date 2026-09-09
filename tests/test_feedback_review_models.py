from datetime import datetime, timezone

import pytest

from qe_platform.feedback.review import (
    FeedbackReview,
    PromotionRecord,
    ReviewAttribution,
    ReviewPriority,
    ReviewStatus,
)


def test_review_from_input_fingerprints_reviewer_and_serializes_structured_fields():
    review = FeedbackReview.from_input(
        "review-1",
        "feedback-1",
        "trace-1",
        "reviewer-42",
        ReviewStatus.CONFIRMED,
        ReviewAttribution.TOOL,
        ReviewPriority.HIGH,
        "hash-key",
        created_at=datetime(2026, 9, 9, tzinfo=timezone.utc),
    )

    payload = review.as_dict()
    assert payload["review_id"] == "review-1"
    assert payload["feedback_id"] == "feedback-1"
    assert payload["trace_id"] == "trace-1"
    assert payload["reviewer_fingerprint"] != "reviewer-42"
    assert payload["status"] == "confirmed"
    assert payload["attribution"] == "tool"
    assert payload["priority"] == "high"
    assert payload["updated_at"].endswith("Z")


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "unknown"),
        ("attribution", "free_text"),
        ("priority", "urgent"),
    ],
)
def test_review_rejects_unknown_enum_values(field, value):
    with pytest.raises(ValueError):
        FeedbackReview.from_input(
            "review-1",
            "feedback-1",
            "trace-1",
            "reviewer-42",
            value if field == "status" else ReviewStatus.PENDING,
            value if field == "attribution" else ReviewAttribution.UNKNOWN,
            value if field == "priority" else ReviewPriority.LOW,
            "hash-key",
        )


def test_promotion_record_requires_utc_timestamp_and_nonempty_yaml():
    timestamp = datetime(2026, 9, 9, tzinfo=timezone.utc)
    record = PromotionRecord(
        "promotion-1",
        "review-1",
        "feedback-1",
        "trace-1",
        "promoted-ticket",
        "id: promoted-ticket\nname: Promoted\nconversation:\n  - user: hello\n",
        timestamp,
    )

    assert record.as_dict()["scenario_id"] == "promoted-ticket"
    assert record.as_dict()["created_at"].endswith("Z")
    with pytest.raises(ValueError):
        PromotionRecord("p", "r", "f", "t", "s", "", timestamp)
    with pytest.raises(ValueError):
        PromotionRecord("p", "r", "f", "t", "s", "yaml", datetime(2026, 9, 9))
