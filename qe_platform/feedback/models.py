from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from qe_platform.telemetry.redaction import fingerprint


_SOURCES = frozenset({"user", "ui", "human_reviewer", "system"})


def _fingerprint_value(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value.lower())


class FeedbackKind(str, Enum):
    CORRECT = "correct"
    INACCURATE = "inaccurate"
    IRRELEVANT = "irrelevant"
    INCOMPLETE = "incomplete"
    HALLUCINATION = "hallucination"
    TOOL_EXECUTION_ERROR = "tool_execution_error"
    SLOW_RESPONSE = "slow_response"


@dataclass(frozen=True)
class FeedbackInput:
    category: FeedbackKind
    reporter_id: str
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.category, FeedbackKind):
            raise ValueError("category must be a FeedbackKind")
        if not isinstance(self.reporter_id, str) or not self.reporter_id:
            raise ValueError("reporter_id must be nonempty")
        if self.source not in _SOURCES:
            raise ValueError("source must be an approved feedback source")


@dataclass(frozen=True)
class FeedbackRecord:
    feedback_id: str
    trace_id: str
    category: FeedbackKind
    reporter_fingerprint: str
    source: str
    created_at: datetime

    @classmethod
    def from_input(cls, feedback_id: str, trace_id: str, feedback: FeedbackInput, hash_key: str, *, created_at: datetime | None = None) -> "FeedbackRecord":
        timestamp = datetime.now(timezone.utc) if created_at is None else created_at
        return cls(feedback_id, trace_id, feedback.category, fingerprint(feedback.reporter_id, hash_key), feedback.source, timestamp)

    def __post_init__(self) -> None:
        if not all(isinstance(value, str) and value for value in (self.feedback_id, self.trace_id, self.reporter_fingerprint, self.source)):
            raise ValueError("feedback identifiers and source must be nonempty")
        if not _fingerprint_value(self.reporter_fingerprint):
            raise ValueError("reporter_fingerprint must be a SHA-256 hexadecimal fingerprint")
        if not isinstance(self.category, FeedbackKind):
            raise ValueError("category must be a FeedbackKind")
        if self.source not in _SOURCES:
            raise ValueError("source must be an approved feedback source")
        if not isinstance(self.created_at, datetime) or self.created_at.tzinfo is None or self.created_at.utcoffset() != timezone.utc.utcoffset(self.created_at):
            raise ValueError("created_at must be UTC")

    def as_dict(self) -> dict[str, str]:
        return {"feedback_id": self.feedback_id, "trace_id": self.trace_id, "category": self.category.value, "reporter_fingerprint": self.reporter_fingerprint, "source": self.source, "created_at": self.created_at.isoformat().replace("+00:00", "Z")}


@dataclass(frozen=True)
class FeedbackQuery:
    trace_id: str = ""
    category: FeedbackKind | None = None
    limit: int = 100
    offset: int = 0

    def __post_init__(self) -> None:
        if not self.trace_id and self.category is None:
            raise ValueError("a feedback query needs a filter")
        if self.category is not None and not isinstance(self.category, FeedbackKind):
            raise ValueError("category must be a FeedbackKind")
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or not 1 <= self.limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if isinstance(self.offset, bool) or not isinstance(self.offset, int) or self.offset < 0:
            raise ValueError("offset must be a nonnegative integer")

    def as_dict(self) -> dict[str, str | int]:
        result: dict[str, str | int] = {"trace_id": self.trace_id} if self.trace_id else {}
        if self.category is not None:
            result["category"] = self.category.value
        if self.limit != 100:
            result["limit"] = self.limit
        if self.offset:
            result["offset"] = self.offset
        return result
