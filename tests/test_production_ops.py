from __future__ import annotations

import json
import sqlite3

import pytest

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
