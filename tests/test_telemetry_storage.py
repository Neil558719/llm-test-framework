import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from qe_platform.feedback import FeedbackInput, FeedbackKind, FeedbackQuery
from qe_platform.storage import (
    SQLiteTelemetryRepository,
    create_telemetry_repository,
    prune_expired,
)
from qe_platform.telemetry import TelemetryQuery, TelemetryTrace, VersionFingerprint, build_trace_event


REQUEST_HASH = "16beff55fc64e01d89cc0941bbf8541e361565d6a790aa6391c62b79a7d6c08b"
ANSWER_HASH = "1f6565182de5ba4d5480090c0b6b8290a6c8ac3604d9a4ca08f3ebe219851ac2"
USER_HASH = "5c046d19135216cdd4c36c9f12f9b7fc330e0376daf2c086970e850a753d09e7"
SESSION_HASH = "28a69be031b9e50ebdb451f1371b5afa9e872ef50935f3d0b21affa1e4df010f"


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def trace_at(value: str, *, trace_id: str = "trace-1", application: str = "service-desk") -> TelemetryTrace:
    return TelemetryTrace(
        trace_id=trace_id,
        application=application,
        timestamp=utc(value),
        request_fingerprint=REQUEST_HASH,
        answer_fingerprint=ANSWER_HASH,
        request_length=15,
        answer_length=14,
        user_fingerprint=USER_HASH,
        session_fingerprint=SESSION_HASH,
        model_version={"model": VersionFingerprint("mock-v1", "test-key")},
        latency={"total_ms": 12.5, "status": "succeeded"},
    )


def test_sqlite_upserts_trace_links_feedback_and_removes_expired_rows(tmp_path):
    repo = SQLiteTelemetryRepository(tmp_path / "telemetry.db", retention_days=30, hash_key="test-key")
    repo.upsert_trace(trace_at("2026-08-01T00:00:00+00:00"))
    repo.add_feedback(FeedbackInput(FeedbackKind.INACCURATE, "reporter", "ui"), "trace-1")

    stored = repo.get_trace("trace-1", now=utc("2026-08-30T00:00:00+00:00"))
    assert stored is not None
    assert stored.feedback_count == 1
    assert repo.prune_expired(now=utc("2026-09-01T00:00:00+00:00")) == 1
    assert repo.list_feedback(
        FeedbackQuery(trace_id="trace-1"), now=utc("2026-09-01T00:00:00+00:00")
    ) == []


def test_sqlite_reopens_hydrates_versions_and_upserts_without_losing_feedback(tmp_path):
    database = tmp_path / "telemetry.db"
    original = trace_at("2026-08-20T00:00:00+00:00")
    original_digest = original.model_version["model"].digest
    first = SQLiteTelemetryRepository(database, hash_key="test-key")
    first.upsert_trace(original)
    first.add_feedback(FeedbackInput(FeedbackKind.CORRECT, "reporter", "ui"), "trace-1")
    first.upsert_trace(replace(original, application="service-desk-v2"))
    first.close()

    reopened = SQLiteTelemetryRepository(database, hash_key="test-key")
    stored = reopened.get_trace("trace-1", now=utc("2026-09-01T00:00:00+00:00"))
    assert stored is not None
    assert stored.application == "service-desk-v2"
    assert stored.feedback_count == 1
    assert type(stored.model_version["model"]) is VersionFingerprint
    assert stored.model_version["model"].digest == original_digest
    assert reopened.list_feedback(
        FeedbackQuery(trace_id="trace-1"), now=utc("2026-09-01T00:00:00+00:00")
    )[0].category is FeedbackKind.CORRECT


def test_trace_filters_and_pagination_are_deterministic(tmp_path):
    repo = SQLiteTelemetryRepository(tmp_path / "telemetry.db", hash_key="test-key")
    for trace_id, timestamp, application in (
        ("trace-a", "2026-08-28T10:00:00+00:00", "service-desk"),
        ("trace-b", "2026-08-29T10:00:00+00:00", "other-app"),
        ("trace-c", "2026-08-29T10:00:00+00:00", "service-desk"),
        ("trace-d", "2026-08-29T10:00:00+00:00", "service-desk"),
    ):
        repo.upsert_trace(trace_at(timestamp, trace_id=trace_id, application=application))

    first_page = repo.list_traces(
        TelemetryQuery(application="service-desk", limit=2),
        now=utc("2026-09-01T00:00:00+00:00"),
    )
    second_page = repo.list_traces(
        TelemetryQuery(application="service-desk", limit=2, offset=2),
        now=utc("2026-09-01T00:00:00+00:00"),
    )
    assert [trace.trace_id for trace in first_page] == ["trace-d", "trace-c"]
    assert [trace.trace_id for trace in second_page] == ["trace-a"]
    assert [trace.trace_id for trace in repo.list_traces(
        TelemetryQuery(trace_id="trace-c"), now=utc("2026-09-01T00:00:00+00:00")
    )] == ["trace-c"]


def test_feedback_filters_and_pagination_are_deterministic(tmp_path):
    repo = SQLiteTelemetryRepository(tmp_path / "telemetry.db", hash_key="test-key")
    repo.upsert_trace(trace_at("2026-08-29T00:00:00+00:00"))
    for category in (FeedbackKind.CORRECT, FeedbackKind.INACCURATE, FeedbackKind.INACCURATE):
        repo.add_feedback(FeedbackInput(category, "reporter", "ui"), "trace-1")

    results = repo.list_feedback(
        FeedbackQuery(trace_id="trace-1", category=FeedbackKind.INACCURATE, limit=1, offset=1),
        now=utc("2026-09-01T00:00:00+00:00"),
    )
    assert len(results) == 1
    assert results[0].category is FeedbackKind.INACCURATE


def test_absent_trace_does_not_accept_feedback_and_transaction_recovers(tmp_path):
    repo = SQLiteTelemetryRepository(tmp_path / "telemetry.db", hash_key="test-key")
    assert repo.get_trace("missing", now=utc("2026-09-01T00:00:00+00:00")) is None
    with pytest.raises(KeyError, match="trace not found"):
        repo.add_feedback(FeedbackInput(FeedbackKind.CORRECT, "reporter", "ui"), "missing")

    repo.upsert_trace(trace_at("2026-08-29T00:00:00+00:00"))
    record = repo.add_feedback(FeedbackInput(FeedbackKind.CORRECT, "reporter", "ui"), "trace-1")
    assert record.trace_id == "trace-1"


def test_one_connection_serializes_concurrent_writes(tmp_path):
    repo = SQLiteTelemetryRepository(tmp_path / "telemetry.db", hash_key="test-key")

    def write_trace(index: int) -> None:
        repo.upsert_trace(
            trace_at("2026-08-29T00:00:00+00:00", trace_id=f"trace-{index:02d}")
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write_trace, range(32)))

    traces = repo.list_traces(
        TelemetryQuery(application="service-desk", limit=100),
        now=utc("2026-09-01T00:00:00+00:00"),
    )
    assert len(traces) == 32
    assert len({trace.trace_id for trace in traces}) == 32


def test_expired_rows_are_hidden_at_boundary_before_physical_prune(tmp_path):
    repo = SQLiteTelemetryRepository(tmp_path / "telemetry.db", retention_days=30, hash_key="test-key")
    repo.upsert_trace(trace_at("2026-08-01T00:00:00+00:00"))
    repo.add_feedback(FeedbackInput(FeedbackKind.CORRECT, "reporter", "ui"), "trace-1")
    boundary = utc("2026-08-31T00:00:00+00:00")

    assert repo.get_trace("trace-1", now=boundary) is None
    assert repo.list_traces(TelemetryQuery(trace_id="trace-1"), now=boundary) == []
    assert repo.list_feedback(FeedbackQuery(trace_id="trace-1"), now=boundary) == []
    assert prune_expired(repo, now=boundary) == 1


def test_retention_comparison_preserves_microsecond_precision(tmp_path):
    repo = SQLiteTelemetryRepository(tmp_path / "telemetry.db", retention_days=30, hash_key="test-key")
    repo.upsert_trace(trace_at("2026-08-01T00:00:00.000001+00:00"))

    stored = repo.get_trace("trace-1", now=utc("2026-08-31T00:00:00+00:00"))
    assert stored is not None
    assert stored.timestamp == utc("2026-08-01T00:00:00.000001+00:00")


def test_factory_and_retention_validation_have_explicit_boundaries(tmp_path):
    plain = create_telemetry_repository(str(tmp_path / "plain.db"), hash_key="test-key")
    assert isinstance(plain, SQLiteTelemetryRepository)
    plain.close()
    sqlite_uri = f"sqlite:///{(tmp_path / 'uri.db').as_posix()}"
    from_uri = create_telemetry_repository(sqlite_uri, retention_days=1, hash_key="test-key")
    assert isinstance(from_uri, SQLiteTelemetryRepository)
    from_uri.close()

    with pytest.raises(NotImplementedError, match="^PostgreSQL telemetry storage is not enabled$"):
        create_telemetry_repository("postgresql://localhost/telemetry", hash_key="test-key")
    with pytest.raises(ValueError, match="positive"):
        create_telemetry_repository(
            "postgresql://localhost/telemetry", retention_days=0, hash_key="test-key"
        )
    with pytest.raises(ValueError):
        create_telemetry_repository("mysql://localhost/telemetry", hash_key="test-key")
    for value in (0, -1, 1.5, True):
        with pytest.raises(ValueError, match="positive"):
            SQLiteTelemetryRepository(tmp_path / f"invalid-{value}.db", retention_days=value, hash_key="test-key")
        with pytest.raises(ValueError, match="positive"):
            create_telemetry_repository(tmp_path / f"factory-{value}.db", retention_days=value, hash_key="test-key")


def test_database_contains_only_sanitized_trace_and_feedback_fields(tmp_path):
    database = tmp_path / "telemetry.db"
    trace = build_trace_event(
        "trace-1",
        "service-desk",
        "private-user-id",
        "private-session-id",
        "private request body",
        "private answer body",
        "test-key",
        tool_calls=[{"name": "create_ticket", "status": "succeeded", "arguments": {"secret": "private tool argument"}}],
        metadata={"environment": "test"},
        usage={"prompt_tokens": 3},
        cost=None,
        model_version={"model": "private-model-label"},
        latency={"total_ms": 12.5, "status": "succeeded"},
    )
    repo = SQLiteTelemetryRepository(database, hash_key="test-key")
    repo.upsert_trace(replace(trace, timestamp=utc("2026-08-29T00:00:00+00:00")))
    repo.add_feedback(FeedbackInput(FeedbackKind.CORRECT, "private-reporter-id", "ui"), "trace-1")

    with sqlite3.connect(database) as connection:
        trace_payload = connection.execute("SELECT payload FROM telemetry_traces").fetchone()[0]
        feedback_values = connection.execute(
            "SELECT category, reporter_fingerprint, source FROM telemetry_feedback"
        ).fetchone()
    serialized = trace_payload + json.dumps(feedback_values)
    for plaintext in (
        "private-user-id",
        "private-session-id",
        "private request body",
        "private answer body",
        "private tool argument",
        "private-model-label",
        "private-reporter-id",
    ):
        assert plaintext not in serialized
    assert "arguments" not in trace_payload
