from __future__ import annotations

import re
import uuid
from typing import Any, Mapping
from datetime import datetime, timezone

import yaml

from qe_platform.scenarios import load_scenario_text

from .models import FeedbackInput, FeedbackRecord
from .review import FeedbackReview, PromotionRecord


_FORBIDDEN_KEYS = ("authorization", "apikey", "token", "secret", "password", "cookie", "header", "rawrequest", "rawresponse")
_SENSITIVE_VALUE = re.compile(r"(?i)(?:bearer\s+|api[_ -]?key\s*[:=]|token\s*[:=]|secret\s*[:=])")


def _validate_scenario_safety(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("scenario keys must be strings")
            normalized = "".join(char for char in key.lower() if char.isalnum())
            if any(part in normalized for part in _FORBIDDEN_KEYS):
                raise ValueError(f"forbidden scenario field: {key}")
            _validate_scenario_safety(item)
    elif isinstance(value, str):
        if _SENSITIVE_VALUE.search(value):
            raise ValueError("forbidden sensitive scenario value")
    elif isinstance(value, (list, tuple)):
        for item in value:
            _validate_scenario_safety(item)
    elif value is not None and not isinstance(value, (bool, int, float)):
        raise ValueError("scenario values must be YAML-safe scalars or collections")


def _feedback_category(value: FeedbackInput | FeedbackRecord):
    category = getattr(value, "category", None)
    if category is None:
        raise ValueError("feedback category is required")
    return category


def promote_review(
    review: FeedbackReview,
    feedback: FeedbackInput | FeedbackRecord,
    scenario_payload: Mapping[str, Any],
) -> PromotionRecord:
    if not isinstance(review, FeedbackReview):
        raise ValueError("review must be a FeedbackReview")
    if not isinstance(feedback, (FeedbackInput, FeedbackRecord)):
        raise ValueError("feedback must be a FeedbackInput or FeedbackRecord")
    if review.status.value != "confirmed":
        raise ValueError("review must be confirmed before promotion")
    if _feedback_category(feedback).value == "correct":
        raise ValueError("only low-quality feedback can be promoted")
    feedback_id = getattr(feedback, "feedback_id", review.feedback_id)
    trace_id = getattr(feedback, "trace_id", review.trace_id)
    if feedback_id != review.feedback_id or trace_id != review.trace_id:
        raise ValueError("review and feedback identifiers do not match")
    if not isinstance(scenario_payload, Mapping):
        raise ValueError("scenario must be a mapping")
    _validate_scenario_safety(scenario_payload)
    try:
        scenario_yaml = yaml.safe_dump(
            dict(scenario_payload),
            allow_unicode=False,
            default_flow_style=False,
            sort_keys=False,
        )
        loaded = load_scenario_text(scenario_yaml, source="<promotion>")
    except (TypeError, yaml.YAMLError, ValueError) as exc:
        raise ValueError(f"invalid regression scenario: {exc}") from exc
    if len(loaded) != 1:
        raise ValueError("promotion must contain exactly one scenario")
    return PromotionRecord(
        uuid.uuid4().hex,
        review.review_id,
        review.feedback_id,
        review.trace_id,
        loaded[0].id,
        scenario_yaml,
        datetime.now(timezone.utc),
    )
