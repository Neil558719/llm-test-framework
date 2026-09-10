"""Small, component-scoped and transactional SQLite migration runner."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Sequence


@dataclass(frozen=True)
class Migration:
    version: int
    apply: Callable[[sqlite3.Connection], None]

    def __post_init__(self) -> None:
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version <= 0:
            raise ValueError("migration version must be a positive integer")


class MigrationRunner:
    """Apply ordered migrations and remember an independent version per component."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        component: str,
        migrations: Sequence[Migration],
    ) -> None:
        if not isinstance(component, str) or not component.strip():
            raise ValueError("migration component must be nonempty")
        self._connection = connection
        self._component = component.strip()
        self._migrations = tuple(sorted(migrations, key=lambda item: item.version))
        versions = tuple(item.version for item in self._migrations)
        if len(set(versions)) != len(versions):
            raise ValueError("migration versions must be unique")
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_meta ("
            "component TEXT PRIMARY KEY, version INTEGER NOT NULL, updated_at TEXT NOT NULL)"
        )
        self._connection.commit()

    def current_version(self) -> int:
        row = self._connection.execute(
            "SELECT version FROM schema_meta WHERE component = ?", (self._component,)
        ).fetchone()
        return 0 if row is None else int(row[0])

    def apply(self) -> int:
        current = self.current_version()
        code_version = self._migrations[-1].version if self._migrations else 0
        if current > code_version:
            raise RuntimeError(
                "database schema version is newer than this code; upgrade code or restore a compatible backup"
            )
        for migration in self._migrations:
            if migration.version <= current:
                continue
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                migration.apply(self._connection)
                self._connection.execute(
                    "INSERT INTO schema_meta(component, version, updated_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(component) DO UPDATE SET version=excluded.version, updated_at=excluded.updated_at",
                    (self._component, migration.version, datetime.now(timezone.utc).isoformat()),
                )
                self._connection.commit()
            except BaseException:
                self._connection.rollback()
                raise
            current = migration.version
        return current
