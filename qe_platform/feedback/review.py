from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from qe_platform.telemetry.redaction import fingerprint


class ReviewStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class ReviewAttribution(str, Enum):
    MODEL = "model"
    PROMPT = "prompt"
    KNOWLEDGE_BASE = "knowledge_base"
    TOOL = "tool"
    INFRASTRUCTURE = "infrastructure"
    USER_INPUT = "user_input"
    UNKNOWN = "unknown"


class ReviewPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


def _nonempty(name: str, value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be nonempty")


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("timestamp must be UTC")
    return value


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _fingerprint(value: str) -> None:
    _nonempty("reviewer_fingerprint", value)
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower()):
        raise ValueError("reviewer_fingerprint must be a SHA-256 hexadecimal fingerprint")


def _enum(enum_type, value, name: str):
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a valid {enum_type.__name__}") from exc


@dataclass(frozen=True)
class FeedbackReview:
    review_id: str
    feedback_id: str
    trace_id: str
    reviewer_fingerprint: str
    status: ReviewStatus
    attribution: ReviewAttribution
    priority: ReviewPriority
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_input(
        cls,
        review_id: str,
        feedback_id: str,
        trace_id: str,
        reviewer_id: str,
        status: ReviewStatus | str,
        attribution: ReviewAttribution | str,
        priority: ReviewPriority | str,
        hash_key: str,
        *,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> "FeedbackReview":
        timestamp = datetime.now(timezone.utc) if created_at is None else created_at
        return cls(
            review_id,
            feedback_id,
            trace_id,
            fingerprint(reviewer_id, hash_key),
            _enum(ReviewStatus, status, "status"),
            _enum(ReviewAttribution, attribution, "attribution"),
            _enum(ReviewPriority, priority, "priority"),
            timestamp,
            timestamp if updated_at is None else updated_at,
        )

    def __post_init__(self) -> None:
        for name, value in (("review_id", self.review_id), ("feedback_id", self.feedback_id), ("trace_id", self.trace_id)):
            _nonempty(name, value)
        _fingerprint(self.reviewer_fingerprint)
        object.__setattr__(self, "status", _enum(ReviewStatus, self.status, "status"))
        object.__setattr__(self, "attribution", _enum(ReviewAttribution, self.attribution, "attribution"))
        object.__setattr__(self, "priority", _enum(ReviewPriority, self.priority, "priority"))
        _utc(self.created_at)
        _utc(self.updated_at)

    def as_dict(self) -> dict[str, str]:
        return {
            "review_id": self.review_id,
            "feedback_id": self.feedback_id,
            "trace_id": self.trace_id,
            "reviewer_fingerprint": self.reviewer_fingerprint,
            "status": self.status.value,
            "attribution": self.attribution.value,
            "priority": self.priority.value,
            "created_at": _timestamp(self.created_at),
            "updated_at": _timestamp(self.updated_at),
        }


@dataclass(frozen=True)
class PromotionRecord:
    promotion_id: str
    review_id: str
    feedback_id: str
    trace_id: str
    scenario_id: str
    scenario_yaml: str
    created_at: datetime

    def __post_init__(self) -> None:
        for name, value in (
            ("promotion_id", self.promotion_id),
            ("review_id", self.review_id),
            ("feedback_id", self.feedback_id),
            ("trace_id", self.trace_id),
            ("scenario_id", self.scenario_id),
            ("scenario_yaml", self.scenario_yaml),
        ):
            _nonempty(name, value)
        _utc(self.created_at)

    def as_dict(self) -> dict[str, str]:
        return {
            "promotion_id": self.promotion_id,
            "review_id": self.review_id,
            "feedback_id": self.feedback_id,
            "trace_id": self.trace_id,
            "scenario_id": self.scenario_id,
            "scenario_yaml": self.scenario_yaml,
            "created_at": _timestamp(self.created_at),
        }
