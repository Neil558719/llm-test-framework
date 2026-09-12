"""Readiness checks that keep implementation errors out of health responses."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class ReadinessResult:
    ready: bool
    checks: Mapping[str, str]

    def as_dict(self) -> dict[str, object]:
        return {"ready": self.ready, "checks": dict(self.checks)}


def _check_connection(connection, requirements) -> bool:
    if connection.execute("PRAGMA query_only").fetchone()[0]:
        return False
    if tuple(connection.execute("PRAGMA integrity_check").fetchone()) != ("ok",):
        return False
    versions = dict(connection.execute("SELECT component, version FROM schema_meta"))
    if not versions or not requirements:
        return False
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for component, (version, required_tables) in requirements.items():
        if versions.get(component) != version or not set(required_tables) <= tables:
            return False
    if connection.in_transaction:
        return False
    try:
        connection.execute("BEGIN IMMEDIATE")
        # A real write in a rolled-back transaction detects read-only mounts.
        connection.execute("UPDATE schema_meta SET version=version")
    finally:
        connection.rollback()
    return True


def _probe(value: Any) -> bool:
    from contextlib import nullcontext
    if callable(value):
        return value() is True
    if isinstance(value, bool):
        return value
    requirements = getattr(value, "schema_requirements", None)
    connection = getattr(value, "_connection", None)
    if connection is not None:
        with getattr(value, "_lock", nullcontext()):
            return _check_connection(connection, requirements)
    database = getattr(value, "database", value)
    if not isinstance(database, (str, Path)) or not Path(database).is_file():
        return False
    connection = sqlite3.connect("file:" + Path(database).resolve().as_posix() + "?mode=rw", uri=True, timeout=1)
    try:
        return _check_connection(connection, requirements)
    finally:
        connection.close()


def readiness(repository_bundle: Mapping[str, Any]) -> ReadinessResult:
    """Return one bounded status per named local data dependency."""
    if not isinstance(repository_bundle, Mapping) or not repository_bundle:
        return ReadinessResult(False, {"configuration": "unavailable"})
    checks: dict[str, str] = {}
    for name, repository in repository_bundle.items():
        if not isinstance(name, str) or not name:
            return ReadinessResult(False, {"configuration": "unavailable"})
        try:
            checks[name] = "ok" if _probe(repository) else "unavailable"
        except Exception:
            checks[name] = "unavailable"
    return ReadinessResult(all(value == "ok" for value in checks.values()), checks)
