from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from qe_platform.storage.telemetry import _sqlite_path

from .models import OfflineRun, QualityLink, ReleaseValidation, parse_run_report


def _utc(value: datetime | None) -> datetime:
    current = datetime.now(timezone.utc) if value is None else value
    if current.tzinfo is None or current.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be UTC")
    return current.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


class SQLiteQualityRepository:
    """Shared-database persistence for M17 artifacts and safe aggregates."""

    def __init__(self, database: str | Path, *, retention_days: int = 30) -> None:
        if isinstance(retention_days, bool) or not isinstance(retention_days, int) or retention_days <= 0:
            raise ValueError("retention_days must be a positive integer")
        self.retention_days = retention_days
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(str(_sqlite_path(database)), check_same_thread=False, isolation_level=None)
        with self._lock:
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS quality_offline_runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_quality_offline_runs_started
                    ON quality_offline_runs(started_at DESC, run_id DESC);
                CREATE TABLE IF NOT EXISTS quality_links (
                    link_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    feedback_id TEXT NOT NULL,
                    review_id TEXT NOT NULL,
                    promotion_id TEXT NOT NULL REFERENCES telemetry_promotions(promotion_id) ON DELETE CASCADE,
                    scenario_id TEXT NOT NULL,
                    offline_run_id TEXT NOT NULL REFERENCES quality_offline_runs(run_id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    UNIQUE(promotion_id, offline_run_id)
                );
                CREATE INDEX IF NOT EXISTS idx_quality_links_run
                    ON quality_links(offline_run_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS quality_release_validations (
                    validation_id TEXT PRIMARY KEY,
                    baseline_run_id TEXT NOT NULL,
                    candidate_run_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_quality_validations_candidate
                    ON quality_release_validations(candidate_run_id, created_at DESC);
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

    def _cutoff(self, now: datetime | None) -> str:
        return _timestamp(_utc(now) - timedelta(days=self.retention_days))

    @staticmethod
    def _hydrate_run(payload: str) -> OfflineRun:
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise ValueError("stored offline run has invalid payload")
        value["scenario_ids"] = tuple(value.get("scenario_ids", ()))
        return OfflineRun(**value)

    @staticmethod
    def _hydrate_link(row: tuple[Any, ...]) -> QualityLink:
        return QualityLink(
            link_id=row[0],
            trace_id=row[1],
            feedback_id=row[2],
            review_id=row[3],
            promotion_id=row[4],
            scenario_id=row[5],
            offline_run_id=row[6],
            created_at=row[7],
        )

    @staticmethod
    def _hydrate_validation(payload: str) -> ReleaseValidation:
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise ValueError("stored validation has invalid payload")
        from .models import ReleaseCheck, ReleaseGatePolicy

        value["policy"] = ReleaseGatePolicy(**value["policy"])
        value["checks"] = tuple(ReleaseCheck(**item) for item in value["checks"])
        return ReleaseValidation(**value)

    def import_run(self, report: dict[str, Any], *, source_label: str, now: datetime | None = None) -> OfflineRun:
        # Run the payload safety check before path-shape validation so a label
        # containing credentials cannot be used to probe storage errors.
        from qe_platform.telemetry.redaction import assert_sanitized_payload

        assert_sanitized_payload(source_label)
        if "/" in source_label or "\\" in source_label or ":" in source_label:
            raise ValueError("source_label must not be an absolute path")
        run = parse_run_report(report, source_label)
        if run.started_at <= self._cutoff(now):
            raise ValueError("offline run is expired")
        payload = json.dumps(run.as_dict(), ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        with self._transaction():
            existing = self._connection.execute(
                "SELECT payload FROM quality_offline_runs WHERE run_id = ?", (run.run_id,)
            ).fetchone()
            if existing is not None:
                if existing[0] != payload:
                    raise ValueError("offline run ID already contains a different report")
                return run
            self._connection.execute(
                "INSERT INTO quality_offline_runs(run_id, started_at, payload) VALUES (?, ?, ?)",
                (run.run_id, run.started_at, payload),
            )
        return run

    def get_run(self, run_id: str, *, now: datetime | None = None) -> OfflineRun | None:
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("run_id must be nonempty")
        with self._lock:
            row = self._connection.execute(
                "SELECT payload FROM quality_offline_runs WHERE run_id = ? AND started_at > ?",
                (run_id, self._cutoff(now)),
            ).fetchone()
        return None if row is None else self._hydrate_run(row[0])

    def list_runs(self, *, application: str = "", version: str = "", now: datetime | None = None) -> list[OfflineRun]:
        query = "SELECT payload FROM quality_offline_runs WHERE started_at > ?"
        params: list[Any] = [self._cutoff(now)]
        if application:
            query += " AND json_extract(payload, '$.application') = ?"
            params.append(application)
        if version:
            query += " AND json_extract(payload, '$.version') = ?"
            params.append(version)
        query += " ORDER BY started_at DESC, run_id DESC"
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [self._hydrate_run(row[0]) for row in rows]

    def create_link(
        self,
        promotion_id: str,
        offline_run_id: str,
        *,
        scenario_id: str | None = None,
        now: datetime | None = None,
    ) -> QualityLink:
        if not isinstance(promotion_id, str) or not promotion_id:
            raise ValueError("promotion_id must be nonempty")
        run = self.get_run(offline_run_id, now=now)
        if run is None:
            raise KeyError("offline run not found")
        cutoff = self._cutoff(now)
        with self._transaction():
            row = self._connection.execute(
                """
                SELECT promotion.promotion_id, promotion.review_id, promotion.feedback_id,
                       promotion.trace_id, promotion.scenario_id
                FROM telemetry_promotions AS promotion
                JOIN telemetry_traces AS trace ON trace.trace_id = promotion.trace_id
                WHERE promotion.promotion_id = ? AND trace.timestamp > ?
                """,
                (promotion_id, cutoff),
            ).fetchone()
            if row is None:
                raise KeyError("promotion not found")
            promoted_scenario = row[4]
            if scenario_id is not None and scenario_id != promoted_scenario:
                raise ValueError("scenario_id does not match promotion")
            if promoted_scenario not in run.scenario_ids:
                raise ValueError("offline run does not contain promoted scenario")
            existing = self._connection.execute(
                """
                SELECT link_id, trace_id, feedback_id, review_id, promotion_id,
                       scenario_id, offline_run_id, created_at
                FROM quality_links WHERE promotion_id = ? AND offline_run_id = ?
                """,
                (promotion_id, offline_run_id),
            ).fetchone()
            if existing is not None:
                return self._hydrate_link(existing)
            link_id = str(uuid.uuid4())
            created_at = _timestamp(_utc(now))
            self._connection.execute(
                """
                INSERT INTO quality_links(
                    link_id, trace_id, feedback_id, review_id, promotion_id,
                    scenario_id, offline_run_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (link_id, row[3], row[2], row[1], row[0], promoted_scenario, offline_run_id, created_at),
            )
            return QualityLink(link_id, row[3], row[2], row[1], row[0], promoted_scenario, offline_run_id, created_at)

    def list_links(
        self,
        *,
        offline_run_id: str = "",
        promotion_id: str = "",
        now: datetime | None = None,
    ) -> list[QualityLink]:
        if offline_run_id and not isinstance(offline_run_id, str):
            raise ValueError("offline_run_id must be a string")
        if promotion_id and not isinstance(promotion_id, str):
            raise ValueError("promotion_id must be a string")
        query = """
            SELECT link.link_id, link.trace_id, link.feedback_id, link.review_id,
                   link.promotion_id, link.scenario_id, link.offline_run_id, link.created_at
            FROM quality_links AS link
            JOIN telemetry_traces AS trace ON trace.trace_id = link.trace_id
            JOIN quality_offline_runs AS run ON run.run_id = link.offline_run_id
            WHERE trace.timestamp > ? AND run.started_at > ?
        """
        params: list[Any] = [self._cutoff(now), self._cutoff(now)]
        if offline_run_id:
            query += " AND link.offline_run_id = ?"
            params.append(offline_run_id)
        if promotion_id:
            query += " AND link.promotion_id = ?"
            params.append(promotion_id)
        query += " ORDER BY link.created_at DESC, link.link_id DESC"
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [self._hydrate_link(row) for row in rows]

    def save_validation(self, value: ReleaseValidation) -> ReleaseValidation:
        if not isinstance(value, ReleaseValidation):
            raise ValueError("value must be a ReleaseValidation")
        payload = json.dumps(value.as_dict(), ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        with self._transaction():
            existing = self._connection.execute(
                "SELECT payload FROM quality_release_validations WHERE validation_id = ?",
                (value.validation_id,),
            ).fetchone()
            if existing is not None:
                if existing[0] != payload:
                    raise ValueError("validation ID already contains a different result")
                return value
            self._connection.execute(
                """
                INSERT INTO quality_release_validations(
                    validation_id, baseline_run_id, candidate_run_id, created_at, payload
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (value.validation_id, value.baseline_run_id, value.candidate_run_id, value.created_at, payload),
            )
        return value

    def get_validation(self, validation_id: str) -> ReleaseValidation | None:
        if not isinstance(validation_id, str) or not validation_id:
            raise ValueError("validation_id must be nonempty")
        with self._lock:
            row = self._connection.execute(
                "SELECT payload FROM quality_release_validations WHERE validation_id = ?",
                (validation_id,),
            ).fetchone()
        return None if row is None else self._hydrate_validation(row[0])

    def online_rows(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        """Return aggregate-safe online values, never raw trace payloads."""
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT trace.trace_id, trace.application, trace.timestamp, trace.payload,
                       COUNT(DISTINCT feedback.feedback_id) AS feedback_count,
                       COALESCE(SUM(CASE WHEN review.status = 'confirmed'
                                         AND feedback.category <> 'correct' THEN 1 ELSE 0 END), 0)
                           AS confirmed_low_quality_count
                FROM telemetry_traces AS trace
                LEFT JOIN telemetry_feedback AS feedback ON feedback.trace_id = trace.trace_id
                LEFT JOIN telemetry_reviews AS review ON review.feedback_id = feedback.feedback_id
                WHERE trace.timestamp > ?
                GROUP BY trace.trace_id, trace.application, trace.timestamp, trace.payload
                ORDER BY trace.timestamp ASC, trace.trace_id ASC
                """,
                (self._cutoff(now),),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for trace_id, application, timestamp, payload_text, feedback_count, low_quality_count in rows:
            payload = json.loads(payload_text)
            latency = payload.get("latency") or {}
            usage = payload.get("usage") or {}
            cost = payload.get("cost") or {}
            versions = payload.get("model_version") or {}
            version = next((str(versions[key]) for key in sorted(versions)), "")
            result.append(
                {
                    "trace_id": trace_id,
                    "application": application,
                    "timestamp": timestamp,
                    "version": version,
                    "latency_ms": float(latency.get("total_ms", 0.0) or 0.0),
                    "total_tokens": int(usage.get("total_tokens", 0) or 0),
                    "total_cost": float((cost or {}).get("total", 0.0) or 0.0),
                    "feedback_count": int(feedback_count),
                    "confirmed_low_quality_count": int(low_quality_count),
                }
            )
        return result
