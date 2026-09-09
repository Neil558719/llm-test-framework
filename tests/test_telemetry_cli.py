from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from qe_platform.storage import SQLiteTelemetryRepository
from qe_platform.telemetry import TelemetryTrace, VersionFingerprint
from qe_platform.telemetry import cli


REQUEST_HASH = "16beff55fc64e01d89cc0941bbf8541e361565d6a790aa6391c62b79a7d6c08b"
ANSWER_HASH = "1f6565182de5ba4d5480090c0b6b8290a6c8ac3604d9a4ca08f3ebe219851ac2"
USER_HASH = "5c046d19135216cdd4c36c9f12f9b7fc330e0376daf2c086970e850a753d09e7"
SESSION_HASH = "28a69be031b9e50ebdb451f1371b5afa9e872ef50935f3d0b21affa1e4df010f"


def old_trace() -> TelemetryTrace:
    return TelemetryTrace(
        trace_id="trace-old",
        application="service-desk",
        timestamp=datetime(2000, 1, 1, tzinfo=timezone.utc),
        request_fingerprint=REQUEST_HASH,
        answer_fingerprint=ANSWER_HASH,
        request_length=15,
        answer_length=14,
        user_fingerprint=USER_HASH,
        session_fingerprint=SESSION_HASH,
        model_version={"model": VersionFingerprint("mock-v1", "test-key")},
        latency={"total_ms": 12.5, "status": "succeeded"},
    )


def test_prune_cli_reads_environment_and_prints_deleted_count(tmp_path, monkeypatch, capsys):
    database = tmp_path / "telemetry.db"
    repo = SQLiteTelemetryRepository(database, retention_days=30, hash_key="test-key")
    repo.upsert_trace(old_trace())
    repo.close()
    monkeypatch.setenv("QE_TELEMETRY_DATABASE", str(database))
    monkeypatch.setenv("QE_TELEMETRY_HASH_KEY", "test-key")
    monkeypatch.setenv("QE_TELEMETRY_INGEST_TOKEN", "ingest-token")
    monkeypatch.setenv("QE_TELEMETRY_RETENTION_DAYS", "30")
    monkeypatch.setenv("REFERENCE_AGENT_DATABASE", str(tmp_path / "must-not-use.db"))

    assert cli.main([]) == 0

    captured = capsys.readouterr()
    assert "Deleted 1 expired telemetry trace" in captured.out
    assert "Traceback" not in captured.err
    reopened = SQLiteTelemetryRepository(database, retention_days=30, hash_key="test-key")
    assert reopened.get_trace("trace-old", now=datetime.now(timezone.utc)) is None
    reopened.close()


def test_prune_cli_returns_two_without_traceback_for_bad_configuration(monkeypatch, capsys):
    monkeypatch.delenv("QE_TELEMETRY_HASH_KEY", raising=False)
    monkeypatch.setenv("QE_TELEMETRY_INGEST_TOKEN", "ingest-token")
    monkeypatch.setenv("QE_TELEMETRY_RETENTION_DAYS", "0")

    assert cli.main([]) == 2

    captured = capsys.readouterr()
    assert "Configuration error:" in captured.err
    assert "QE_TELEMETRY_HASH_KEY" in captured.err
    assert "ingest-token" not in captured.err
    assert "Traceback" not in captured.err


def test_settings_default_database_ignores_reference_agent_database(monkeypatch, tmp_path):
    monkeypatch.setenv("REFERENCE_AGENT_DATABASE", str(tmp_path / "reference.db"))
    monkeypatch.delenv("QE_TELEMETRY_DATABASE", raising=False)
    monkeypatch.setenv("QE_TELEMETRY_HASH_KEY", "test-key")
    monkeypatch.setenv("QE_TELEMETRY_INGEST_TOKEN", "ingest-token")
    monkeypatch.delenv("QE_TELEMETRY_RETENTION_DAYS", raising=False)

    settings = cli.TelemetrySettings.from_environment()

    assert settings.database == "telemetry.db"
    assert settings.retention_days == 30
