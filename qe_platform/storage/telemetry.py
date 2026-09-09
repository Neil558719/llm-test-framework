from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Protocol
from urllib.parse import unquote, urlparse

from qe_platform.feedback import (
    FeedbackInput,
    FeedbackKind,
    FeedbackQuery,
    FeedbackRecord,
    FeedbackReview,
    PromotionRecord,
    ReviewAttribution,
    ReviewPriority,
    ReviewStatus,
)
from qe_platform.telemetry import TelemetryQuery, TelemetryTrace, ToolSummary, VersionFingerprint
from qe_platform.telemetry.redaction import assert_sanitized_payload


_TRACE_FIELDS = frozenset(
    {
        "trace_id",
        "application",
        "timestamp",
        "request_fingerprint",
        "answer_fingerprint",
        "request_length",
        "answer_length",
        "source",
        "tool_calls",
        "metadata",
        "usage",
        "cost",
        "model_version",
        "latency",
    }
)


class TelemetryRepository(Protocol):
    def upsert_trace(self, trace: TelemetryTrace) -> TelemetryTrace: ...

    def get_trace(self, trace_id: str, *, now: datetime | None = None) -> TelemetryTrace | None: ...

    def list_traces(self, query: TelemetryQuery, *, now: datetime | None = None) -> list[TelemetryTrace]: ...

    def add_feedback(self, value: FeedbackInput, trace_id: str) -> FeedbackRecord: ...

    def list_feedback(self, query: FeedbackQuery, *, now: datetime | None = None) -> list[FeedbackRecord]: ...

    def get_feedback(self, feedback_id: str, *, now: datetime | None = None) -> FeedbackRecord | None: ...

    def upsert_review(
        self,
        feedback_id: str,
        reviewer_id: str,
        status: ReviewStatus | str,
        attribution: ReviewAttribution | str,
        priority: ReviewPriority | str,
    ) -> FeedbackReview: ...

    def get_review(self, review_id: str, *, now: datetime | None = None) -> FeedbackReview | None: ...

    def list_reviews(
        self,
        *,
        feedback_id: str = "",
        trace_id: str = "",
        status: ReviewStatus | str | None = None,
        limit: int = 100,
        offset: int = 0,
        now: datetime | None = None,
    ) -> list[FeedbackReview]: ...

    def create_promotion(self, review_id: str, scenario_id: str, scenario_yaml: str, *, promotion_id: str | None = None) -> PromotionRecord: ...

    def get_promotion(self, promotion_id: str, *, now: datetime | None = None) -> PromotionRecord | None: ...

    def get_promotion_for_review(self, review_id: str, *, now: datetime | None = None) -> PromotionRecord | None: ...

    def prune_expired(self, *, now: datetime) -> int: ...


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be UTC")
    return value


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _positive_retention(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("retention_days must be a positive integer")
    return value


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("persisted timestamp must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _utc(parsed)


def _hydrate_version_fingerprint(value: Any) -> VersionFingerprint:
    """Restore a digest read from this repository's validated trace payload."""
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower()):
        raise ValueError("persisted model version must be a SHA-256 hexadecimal fingerprint")
    fingerprint = object.__new__(VersionFingerprint)
    object.__setattr__(fingerprint, "digest", value.lower())
    return fingerprint


@dataclass(frozen=True)
class _StoredTelemetryTrace(TelemetryTrace):
    feedback_count: int = 0

    def __post_init__(self) -> None:
        super().__post_init__()
        if isinstance(self.feedback_count, bool) or not isinstance(self.feedback_count, int) or self.feedback_count < 0:
            raise ValueError("feedback_count must be a nonnegative integer")


def _hydrate_review(row: tuple[Any, ...]) -> FeedbackReview:
    return FeedbackReview(
        review_id=row[0],
        feedback_id=row[1],
        trace_id=row[2],
        reviewer_fingerprint=row[3],
        status=ReviewStatus(row[4]),
        attribution=ReviewAttribution(row[5]),
        priority=ReviewPriority(row[6]),
        created_at=_parse_timestamp(row[7]),
        updated_at=_parse_timestamp(row[8]),
    )


def _hydrate_promotion(row: tuple[Any, ...]) -> PromotionRecord:
    return PromotionRecord(
        promotion_id=row[0],
        review_id=row[1],
        feedback_id=row[2],
        trace_id=row[3],
        scenario_id=row[4],
        scenario_yaml=row[5],
        created_at=_parse_timestamp(row[6]),
    )


def _hydrate_trace(payload_text: str, feedback_count: int = 0) -> _StoredTelemetryTrace:
    payload = json.loads(payload_text)
    if not isinstance(payload, Mapping) or set(payload) != _TRACE_FIELDS:
        raise ValueError("persisted trace payload has an invalid schema")
    assert_sanitized_payload(payload)
    source = payload["source"]
    if not isinstance(source, Mapping) or set(source) != {"user_fingerprint", "session_fingerprint"}:
        raise ValueError("persisted trace source has an invalid schema")
    tools = payload["tool_calls"]
    versions = payload["model_version"]
    if not isinstance(tools, list) or not isinstance(versions, Mapping):
        raise ValueError("persisted trace collections have an invalid schema")
    return _StoredTelemetryTrace(
        trace_id=payload["trace_id"],
        application=payload["application"],
        timestamp=_parse_timestamp(payload["timestamp"]),
        request_fingerprint=payload["request_fingerprint"],
        answer_fingerprint=payload["answer_fingerprint"],
        request_length=payload["request_length"],
        answer_length=payload["answer_length"],
        user_fingerprint=source["user_fingerprint"],
        session_fingerprint=source["session_fingerprint"],
        tool_calls=tuple(ToolSummary(**tool) for tool in tools),
        metadata=payload["metadata"],
        usage=payload["usage"],
        cost=payload["cost"],
        model_version={key: _hydrate_version_fingerprint(value) for key, value in versions.items()},
        latency=payload["latency"],
        feedback_count=feedback_count,
    )


class SQLiteTelemetryRepository:
    def __init__(
        self,
        database: str | Path,
        *,
        retention_days: int = 30,
        hash_key: str = "qe-telemetry-local-default",
    ) -> None:
        if not isinstance(hash_key, str) or not hash_key:
            raise ValueError("hash_key must be nonempty")
        self.retention_days = _positive_retention(retention_days)
        self._hash_key = hash_key
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(str(database), check_same_thread=False, isolation_level=None)
        with self._lock:
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS telemetry_traces (
                    trace_id TEXT PRIMARY KEY,
                    application TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_telemetry_traces_timestamp_id
                    ON telemetry_traces(timestamp DESC, trace_id DESC);
                CREATE TABLE IF NOT EXISTS telemetry_feedback (
                    feedback_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL REFERENCES telemetry_traces(trace_id) ON DELETE CASCADE,
                    category TEXT NOT NULL,
                    reporter_fingerprint TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_telemetry_feedback_timestamp_id
                    ON telemetry_feedback(created_at DESC, feedback_id DESC);
                CREATE TABLE IF NOT EXISTS telemetry_reviews (
                    review_id TEXT PRIMARY KEY,
                    feedback_id TEXT NOT NULL UNIQUE REFERENCES telemetry_feedback(feedback_id) ON DELETE CASCADE,
                    trace_id TEXT NOT NULL REFERENCES telemetry_traces(trace_id) ON DELETE CASCADE,
                    reviewer_fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attribution TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_telemetry_reviews_updated_id
                    ON telemetry_reviews(updated_at DESC, review_id DESC);
                CREATE TABLE IF NOT EXISTS telemetry_promotions (
                    promotion_id TEXT PRIMARY KEY,
                    review_id TEXT NOT NULL UNIQUE REFERENCES telemetry_reviews(review_id) ON DELETE CASCADE,
                    feedback_id TEXT NOT NULL REFERENCES telemetry_feedback(feedback_id) ON DELETE CASCADE,
                    trace_id TEXT NOT NULL REFERENCES telemetry_traces(trace_id) ON DELETE CASCADE,
                    scenario_id TEXT NOT NULL,
                    scenario_yaml TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_telemetry_promotions_created_id
                    ON telemetry_promotions(created_at DESC, promotion_id DESC);
                """
            )

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                yield
                self._connection.commit()
            except BaseException:
                self._connection.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def upsert_trace(self, trace: TelemetryTrace) -> TelemetryTrace:
        if not isinstance(trace, TelemetryTrace):
            raise ValueError("trace must be a TelemetryTrace")
        payload = trace.as_dict()
        if set(payload) != _TRACE_FIELDS:
            raise ValueError("trace payload has an invalid schema")
        assert_sanitized_payload(payload)
        serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        with self._transaction():
            self._connection.execute(
                """
                INSERT INTO telemetry_traces(trace_id, application, timestamp, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(trace_id) DO UPDATE SET
                    application=excluded.application,
                    timestamp=excluded.timestamp,
                    payload=excluded.payload
                """,
                (
                    payload["trace_id"],
                    payload["application"],
                    _timestamp(_parse_timestamp(payload["timestamp"])),
                    serialized,
                ),
            )
        return trace

    def _cutoff(self, now: datetime | None) -> str:
        current = datetime.now(timezone.utc) if now is None else _utc(now)
        return _timestamp(current - timedelta(days=self.retention_days))

    def get_trace(self, trace_id: str, *, now: datetime | None = None) -> TelemetryTrace | None:
        if not isinstance(trace_id, str) or not trace_id:
            raise ValueError("trace_id must be nonempty")
        with self._lock:
            row = self._connection.execute(
                """
                SELECT trace.payload, COUNT(feedback.feedback_id)
                FROM telemetry_traces AS trace
                LEFT JOIN telemetry_feedback AS feedback ON feedback.trace_id = trace.trace_id
                WHERE trace.trace_id = ? AND trace.timestamp > ?
                GROUP BY trace.trace_id, trace.payload
                """,
                (trace_id, self._cutoff(now)),
            ).fetchone()
        return None if row is None else _hydrate_trace(row[0], row[1])

    def list_traces(self, query: TelemetryQuery, *, now: datetime | None = None) -> list[TelemetryTrace]:
        if not isinstance(query, TelemetryQuery):
            raise ValueError("query must be a TelemetryQuery")
        filters = ["trace.timestamp > ?"]
        parameters: list[Any] = [self._cutoff(now)]
        if query.application:
            filters.append("trace.application = ?")
            parameters.append(query.application)
        if query.trace_id:
            filters.append("trace.trace_id = ?")
            parameters.append(query.trace_id)
        sql = f"""
            SELECT trace.payload, COUNT(feedback.feedback_id)
            FROM telemetry_traces AS trace
            LEFT JOIN telemetry_feedback AS feedback ON feedback.trace_id = trace.trace_id
            WHERE {' AND '.join(filters)}
            GROUP BY trace.trace_id, trace.payload, trace.timestamp
            ORDER BY trace.timestamp DESC, trace.trace_id DESC
            LIMIT ? OFFSET ?
        """
        parameters.extend((query.limit, query.offset))
        with self._lock:
            rows = self._connection.execute(sql, parameters).fetchall()
        return [_hydrate_trace(row[0], row[1]) for row in rows]

    def add_feedback(self, value: FeedbackInput, trace_id: str) -> FeedbackRecord:
        if not isinstance(value, FeedbackInput):
            raise ValueError("value must be a FeedbackInput")
        if not isinstance(trace_id, str) or not trace_id:
            raise ValueError("trace_id must be nonempty")
        with self._transaction():
            exists = self._connection.execute(
                "SELECT 1 FROM telemetry_traces WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()
            if exists is None:
                raise KeyError("trace not found")
            record = FeedbackRecord.from_input(uuid.uuid4().hex, trace_id, value, self._hash_key)
            payload = record.as_dict()
            self._connection.execute(
                """
                INSERT INTO telemetry_feedback(
                    feedback_id, trace_id, category, reporter_fingerprint, source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["feedback_id"],
                    payload["trace_id"],
                    payload["category"],
                    payload["reporter_fingerprint"],
                    payload["source"],
                    _timestamp(record.created_at),
                ),
            )
        return record

    def list_feedback(self, query: FeedbackQuery, *, now: datetime | None = None) -> list[FeedbackRecord]:
        if not isinstance(query, FeedbackQuery):
            raise ValueError("query must be a FeedbackQuery")
        filters = ["trace.timestamp > ?"]
        parameters: list[Any] = [self._cutoff(now)]
        if query.trace_id:
            filters.append("feedback.trace_id = ?")
            parameters.append(query.trace_id)
        if query.category is not None:
            filters.append("feedback.category = ?")
            parameters.append(query.category.value)
        sql = f"""
            SELECT feedback.feedback_id, feedback.trace_id, feedback.category,
                   feedback.reporter_fingerprint, feedback.source, feedback.created_at
            FROM telemetry_feedback AS feedback
            JOIN telemetry_traces AS trace ON trace.trace_id = feedback.trace_id
            WHERE {' AND '.join(filters)}
            ORDER BY feedback.created_at DESC, feedback.feedback_id DESC
            LIMIT ? OFFSET ?
        """
        parameters.extend((query.limit, query.offset))
        with self._lock:
            rows = self._connection.execute(sql, parameters).fetchall()
        return [
            FeedbackRecord(
                feedback_id=row[0],
                trace_id=row[1],
                category=FeedbackKind(row[2]),
                reporter_fingerprint=row[3],
                source=row[4],
                created_at=_parse_timestamp(row[5]),
            )
            for row in rows
        ]

    def get_feedback(self, feedback_id: str, *, now: datetime | None = None) -> FeedbackRecord | None:
        if not isinstance(feedback_id, str) or not feedback_id:
            raise ValueError("feedback_id must be nonempty")
        with self._lock:
            row = self._connection.execute(
                """
                SELECT feedback.feedback_id, feedback.trace_id, feedback.category,
                       feedback.reporter_fingerprint, feedback.source, feedback.created_at
                FROM telemetry_feedback AS feedback
                JOIN telemetry_traces AS trace ON trace.trace_id = feedback.trace_id
                WHERE feedback.feedback_id = ? AND trace.timestamp > ?
                """,
                (feedback_id, self._cutoff(now)),
            ).fetchone()
        return None if row is None else FeedbackRecord(
            feedback_id=row[0],
            trace_id=row[1],
            category=FeedbackKind(row[2]),
            reporter_fingerprint=row[3],
            source=row[4],
            created_at=_parse_timestamp(row[5]),
        )

    def upsert_review(
        self,
        feedback_id: str,
        reviewer_id: str,
        status: ReviewStatus | str,
        attribution: ReviewAttribution | str,
        priority: ReviewPriority | str,
    ) -> FeedbackReview:
        if not isinstance(feedback_id, str) or not feedback_id:
            raise ValueError("feedback_id must be nonempty")
        with self._transaction():
            source = self._connection.execute(
                "SELECT feedback_id, trace_id FROM telemetry_feedback WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
            if source is None:
                raise KeyError("feedback not found")
            existing = self._connection.execute(
                "SELECT review_id, created_at FROM telemetry_reviews WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
            review_id = existing[0] if existing is not None else uuid.uuid4().hex
            created_at = _parse_timestamp(existing[1]) if existing is not None else datetime.now(timezone.utc)
            review = FeedbackReview.from_input(
                review_id,
                source[0],
                source[1],
                reviewer_id,
                status,
                attribution,
                priority,
                self._hash_key,
                created_at=created_at,
            )
            updated_at = datetime.now(timezone.utc)
            self._connection.execute(
                """
                INSERT INTO telemetry_reviews(
                    review_id, feedback_id, trace_id, reviewer_fingerprint, status,
                    attribution, priority, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(feedback_id) DO UPDATE SET
                    reviewer_fingerprint=excluded.reviewer_fingerprint,
                    status=excluded.status,
                    attribution=excluded.attribution,
                    priority=excluded.priority,
                    updated_at=excluded.updated_at
                """,
                (
                    review.review_id,
                    review.feedback_id,
                    review.trace_id,
                    review.reviewer_fingerprint,
                    review.status.value,
                    review.attribution.value,
                    review.priority.value,
                    _timestamp(review.created_at),
                    _timestamp(updated_at),
                ),
            )
            return FeedbackReview(
                review.review_id,
                review.feedback_id,
                review.trace_id,
                review.reviewer_fingerprint,
                review.status,
                review.attribution,
                review.priority,
                review.created_at,
                updated_at,
            )

    def get_review(self, review_id: str, *, now: datetime | None = None) -> FeedbackReview | None:
        if not isinstance(review_id, str) or not review_id:
            raise ValueError("review_id must be nonempty")
        with self._lock:
            row = self._connection.execute(
                """
                SELECT review.review_id, review.feedback_id, review.trace_id,
                       review.reviewer_fingerprint, review.status, review.attribution,
                       review.priority, review.created_at, review.updated_at
                FROM telemetry_reviews AS review
                JOIN telemetry_traces AS trace ON trace.trace_id = review.trace_id
                WHERE review.review_id = ? AND trace.timestamp > ?
                """,
                (review_id, self._cutoff(now)),
            ).fetchone()
        return None if row is None else _hydrate_review(row)

    def list_reviews(
        self,
        *,
        feedback_id: str = "",
        trace_id: str = "",
        status: ReviewStatus | str | None = None,
        limit: int = 100,
        offset: int = 0,
        now: datetime | None = None,
    ) -> list[FeedbackReview]:
        if isinstance(status, str):
            status = ReviewStatus(status)
        if status is not None and not isinstance(status, ReviewStatus):
            raise ValueError("status must be a ReviewStatus")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be a nonnegative integer")
        filters = ["trace.timestamp > ?"]
        parameters: list[Any] = [self._cutoff(now)]
        if feedback_id:
            filters.append("review.feedback_id = ?")
            parameters.append(feedback_id)
        if trace_id:
            filters.append("review.trace_id = ?")
            parameters.append(trace_id)
        if status is not None:
            filters.append("review.status = ?")
            parameters.append(status.value)
        parameters.extend((limit, offset))
        with self._lock:
            rows = self._connection.execute(
                f"""
                SELECT review.review_id, review.feedback_id, review.trace_id,
                       review.reviewer_fingerprint, review.status, review.attribution,
                       review.priority, review.created_at, review.updated_at
                FROM telemetry_reviews AS review
                JOIN telemetry_traces AS trace ON trace.trace_id = review.trace_id
                WHERE {' AND '.join(filters)}
                ORDER BY review.updated_at DESC, review.review_id DESC
                LIMIT ? OFFSET ?
                """,
                parameters,
            ).fetchall()
        return [_hydrate_review(row) for row in rows]

    def create_promotion(self, review_id: str, scenario_id: str, scenario_yaml: str, *, promotion_id: str | None = None) -> PromotionRecord:
        if not isinstance(review_id, str) or not review_id:
            raise ValueError("review_id must be nonempty")
        if not isinstance(scenario_id, str) or not scenario_id:
            raise ValueError("scenario_id must be nonempty")
        if not isinstance(scenario_yaml, str) or not scenario_yaml:
            raise ValueError("scenario_yaml must be nonempty")
        with self._transaction():
            existing = self._connection.execute(
                """
                SELECT promotion_id, review_id, feedback_id, trace_id,
                       scenario_id, scenario_yaml, created_at
                FROM telemetry_promotions WHERE review_id = ?
                """,
                (review_id,),
            ).fetchone()
            if existing is not None:
                return _hydrate_promotion(existing)
            source = self._connection.execute(
                """
                SELECT review.review_id, review.feedback_id, review.trace_id
                FROM telemetry_reviews AS review
                JOIN telemetry_feedback AS feedback ON feedback.feedback_id = review.feedback_id
                WHERE review.review_id = ?
                """,
                (review_id,),
            ).fetchone()
            if source is None:
                raise KeyError("review not found")
            record = PromotionRecord(
                uuid.uuid4().hex if promotion_id is None else promotion_id,
                source[0],
                source[1],
                source[2],
                scenario_id,
                scenario_yaml,
                datetime.now(timezone.utc),
            )
            payload = record.as_dict()
            self._connection.execute(
                """
                INSERT INTO telemetry_promotions(
                    promotion_id, review_id, feedback_id, trace_id,
                    scenario_id, scenario_yaml, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["promotion_id"],
                    payload["review_id"],
                    payload["feedback_id"],
                    payload["trace_id"],
                    payload["scenario_id"],
                    payload["scenario_yaml"],
                    payload["created_at"],
                ),
            )
            return record

    def get_promotion(self, promotion_id: str, *, now: datetime | None = None) -> PromotionRecord | None:
        if not isinstance(promotion_id, str) or not promotion_id:
            raise ValueError("promotion_id must be nonempty")
        with self._lock:
            row = self._connection.execute(
                """
                SELECT promotion.promotion_id, promotion.review_id, promotion.feedback_id,
                       promotion.trace_id, promotion.scenario_id, promotion.scenario_yaml,
                       promotion.created_at
                FROM telemetry_promotions AS promotion
                JOIN telemetry_traces AS trace ON trace.trace_id = promotion.trace_id
                WHERE promotion.promotion_id = ? AND trace.timestamp > ?
                """,
                (promotion_id, self._cutoff(now)),
            ).fetchone()
        return None if row is None else _hydrate_promotion(row)

    def get_promotion_for_review(self, review_id: str, *, now: datetime | None = None) -> PromotionRecord | None:
        if not isinstance(review_id, str) or not review_id:
            raise ValueError("review_id must be nonempty")
        with self._lock:
            row = self._connection.execute(
                """
                SELECT promotion.promotion_id, promotion.review_id, promotion.feedback_id,
                       promotion.trace_id, promotion.scenario_id, promotion.scenario_yaml,
                       promotion.created_at
                FROM telemetry_promotions AS promotion
                JOIN telemetry_traces AS trace ON trace.trace_id = promotion.trace_id
                WHERE promotion.review_id = ? AND trace.timestamp > ?
                """,
                (review_id, self._cutoff(now)),
            ).fetchone()
        return None if row is None else _hydrate_promotion(row)

    def prune_expired(self, *, now: datetime) -> int:
        with self._transaction():
            cursor = self._connection.execute(
                "DELETE FROM telemetry_traces WHERE timestamp <= ?",
                (self._cutoff(now),),
            )
        return cursor.rowcount


class PostgreSQLTelemetryRepository:
    def __init__(self, *_: Any, **__: Any) -> None:
        raise NotImplementedError("PostgreSQL telemetry storage is not enabled")


def _sqlite_path(value: str | Path) -> str | Path:
    if isinstance(value, Path):
        return value
    if len(value) >= 3 and value[1] == ":" and value[2] in {"/", "\\"}:
        return value
    parsed = urlparse(value)
    if not parsed.scheme:
        return value
    if parsed.scheme != "sqlite":
        raise ValueError(f"unsupported telemetry database scheme: {parsed.scheme}")
    if parsed.netloc not in {"", "localhost"}:
        raise ValueError("sqlite telemetry database must be local")
    path = unquote(parsed.path)
    if path == "/:memory:":
        return ":memory:"
    if len(path) >= 3 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return path


def create_telemetry_repository(
    database: str | Path,
    *,
    retention_days: int = 30,
    hash_key: str = "qe-telemetry-local-default",
) -> TelemetryRepository:
    _positive_retention(retention_days)
    if isinstance(database, str) and urlparse(database).scheme in {"postgres", "postgresql"}:
        raise NotImplementedError("PostgreSQL telemetry storage is not enabled")
    return SQLiteTelemetryRepository(
        _sqlite_path(database), retention_days=retention_days, hash_key=hash_key
    )


def prune_expired(repository: TelemetryRepository, *, now: datetime) -> int:
    return repository.prune_expired(now=now)
