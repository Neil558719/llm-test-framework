import sqlite3

import pytest

from qe_platform.storage.migrations import Migration, MigrationRunner
from qe_platform.storage.sqlite_runtime import configure_sqlite
from qe_platform.storage.telemetry import SQLiteTelemetryRepository
from qe_platform.quality_loop.storage import SQLiteQualityRepository


def test_migration_runner_applies_each_version_once_in_order():
    connection = sqlite3.connect(":memory:")
    applied: list[int] = []

    runner = MigrationRunner(
        connection,
        "example",
        (
            Migration(1, lambda database: applied.append(1)),
            Migration(2, lambda database: applied.append(2)),
        ),
    )

    assert runner.apply() == 2
    assert runner.current_version() == 2
    assert runner.apply() == 2
    assert applied == [1, 2]


def test_migration_runner_rejects_database_newer_than_the_code():
    connection = sqlite3.connect(":memory:")
    initial = MigrationRunner(connection, "example", (Migration(1, lambda database: None),))
    initial.apply()
    connection.execute("UPDATE schema_meta SET version = 2 WHERE component = 'example'")
    connection.commit()

    runner = MigrationRunner(connection, "example", (Migration(1, lambda database: None),))

    with pytest.raises(RuntimeError, match="newer than this code"):
        runner.apply()


def test_failed_migration_rolls_back_its_data_and_version():
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE values_table (value TEXT NOT NULL)")

    def fail_after_write(database: sqlite3.Connection) -> None:
        database.execute("INSERT INTO values_table(value) VALUES ('partial')")
        raise RuntimeError("injected migration failure")

    runner = MigrationRunner(connection, "example", (Migration(1, fail_after_write),))

    with pytest.raises(RuntimeError, match="injected migration failure"):
        runner.apply()

    assert connection.execute("SELECT value FROM values_table").fetchall() == []
    assert runner.current_version() == 0


def test_configure_sqlite_enables_required_file_database_pragmas(tmp_path):
    connection = sqlite3.connect(tmp_path / "runtime.db")

    configure_sqlite(connection)

    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert connection.execute("PRAGMA synchronous").fetchone()[0] == 1
    assert connection.execute("PRAGMA busy_timeout").fetchone()[0] > 0


def test_telemetry_and_quality_components_register_versions_in_shared_database(tmp_path):
    database = tmp_path / "quality.db"
    telemetry = SQLiteTelemetryRepository(database)
    quality = SQLiteQualityRepository(database)
    connection = sqlite3.connect(database)
    try:
        rows = connection.execute(
            "SELECT component, version FROM schema_meta ORDER BY component"
        ).fetchall()
        assert rows == [("quality_loop", 1), ("telemetry", 1)]
    finally:
        connection.close()
        quality.close()
        telemetry.close()
