from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import qe_platform.ops.backup as backup_module
from qe_platform.ops.backup import backup_database
from qe_platform.ops.restore import RestoreError, restore_database


def _database(path, *, version: int = 1) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE records (value TEXT NOT NULL)")
        connection.execute("INSERT INTO records(value) VALUES ('kept')")
        connection.execute(
            "CREATE TABLE schema_meta (component TEXT PRIMARY KEY, version INTEGER NOT NULL, updated_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO schema_meta(component, version, updated_at) VALUES ('reference_agent', ?, '2026-09-10T00:00:00Z')",
            (version,),
        )


def test_online_backup_records_schema_versions_checksum_and_integrity(tmp_path):
    source = tmp_path / "source.db"
    target = tmp_path / "backup.db"
    _database(source)

    result = backup_database(source, target)

    assert result.path == target
    assert result.schema_versions == {"reference_agent": 1}
    assert len(result.sha256) == 64
    assert result.integrity_ok is True
    manifest = json.loads(target.with_suffix(target.suffix + ".manifest.json").read_text(encoding="utf-8"))
    assert manifest == {"schema_versions": {"reference_agent": 1}, "sha256": result.sha256}
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT value FROM records").fetchone()[0] == "kept"


def test_restore_rejects_corrupted_backup_before_replacing_target(tmp_path):
    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    backup = tmp_path / "backup.db"
    _database(source)
    _database(target)
    backup_database(source, backup)
    backup.write_bytes(b"not a sqlite database")

    with pytest.raises(RestoreError, match="checksum"):
        restore_database(backup, target, {"reference_agent": 1})

    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT value FROM records").fetchone()[0] == "kept"


def test_restore_rejects_schema_newer_than_running_code(tmp_path):
    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    backup = tmp_path / "backup.db"
    _database(source, version=2)
    _database(target)
    backup_database(source, backup)

    with pytest.raises(RestoreError, match="schema version"):
        restore_database(backup, target, {"reference_agent": 1})


def test_restore_validates_backup_and_replaces_target_atomically(tmp_path):
    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    backup = tmp_path / "backup.db"
    _database(source)
    connection = sqlite3.connect(target)
    try:
        connection.execute("CREATE TABLE records (value TEXT NOT NULL)")
        connection.execute("INSERT INTO records(value) VALUES ('old')")
        connection.commit()
    finally:
        connection.close()
    backup_database(source, backup)

    result = restore_database(backup, target, {"reference_agent": 1})

    assert result.path == target
    assert result.schema_versions == {"reference_agent": 1}
    assert result.integrity_ok is True
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT value FROM records").fetchone()[0] == "kept"


def test_restore_reads_backup_through_an_immutable_read_only_connection(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    backup = tmp_path / "backup.db"
    target = tmp_path / "target.db"
    _database(source)
    backup_database(source, backup)

    real_connect = backup_module.sqlite3.connect
    connection_calls: list[tuple[str, bool]] = []

    def read_only_mount_connect(database, *args, **kwargs):
        connection_calls.append((str(database), kwargs.get("uri", False)))
        if str(database) == str(backup):
            raise sqlite3.OperationalError("attempt to write a readonly database")
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(backup_module.sqlite3, "connect", read_only_mount_connect)

    restore_database(backup, target, {"reference_agent": 1})

    backup_connections = [call for call in connection_calls if call[0].startswith("file:") and "backup.db" in call[0]]
    assert backup_connections
    assert all(uri for _, uri in backup_connections)
    assert all("mode=ro&immutable=1" in database for database, _ in backup_connections)


def test_restore_rejects_non_quiescent_target_before_replacing_it(tmp_path):
    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    backup = tmp_path / "backup.db"
    _database(source)
    _database(target)
    with sqlite3.connect(target) as connection:
        connection.execute("UPDATE records SET value = 'old'")
    backup_database(source, backup)
    Path(str(target) + "-wal").write_bytes(b"active database sidecar")

    with pytest.raises(RestoreError, match="quiescent"):
        restore_database(backup, target, {"reference_agent": 1})

    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT value FROM records").fetchone()[0] == "old"


def test_backup_publish_failure_restores_previous_database_manifest_pair(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    target = tmp_path / "backup.db"
    _database(source)
    backup_database(source, target)
    original_database = target.read_bytes()
    original_manifest = target.with_suffix(target.suffix + ".manifest.json").read_bytes()
    with sqlite3.connect(source) as connection:
        connection.execute("INSERT INTO records(value) VALUES ('new')")

    real_replace = backup_module.os.replace

    failed = False

    def fail_manifest_publish(current, destination):
        nonlocal failed
        if Path(destination) == target.with_suffix(target.suffix + ".manifest.json") and not failed:
            failed = True
            raise OSError("simulated manifest publish failure")
        return real_replace(current, destination)

    monkeypatch.setattr(backup_module.os, "replace", fail_manifest_publish)

    with pytest.raises(RuntimeError, match="publication"):
        backup_database(source, target)

    assert target.read_bytes() == original_database
    assert target.with_suffix(target.suffix + ".manifest.json").read_bytes() == original_manifest
