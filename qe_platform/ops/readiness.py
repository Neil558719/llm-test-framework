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


def _probe(value: Any) -> bool:
    if callable(value):
        return value() is True
    if isinstance(value, bool):
        return value
    connection = getattr(value, "_connection", None)
    if connection is not None:
        connection.execute("SELECT 1").fetchone()
        return True
    database = getattr(value, "database", value)
    if isinstance(database, Path):
        database = str(database)
    if not isinstance(database, str):
        return False
    if database == ":memory:":
        return True
    path = Path(database)
    if not path.is_file():
        return False
    connection = sqlite3.connect("file:" + path.resolve().as_posix() + "?mode=ro", uri=True)
    try:
        connection.execute("SELECT 1").fetchone()
        return connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
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
        except (OSError, sqlite3.Error, ValueError):
            checks[name] = "unavailable"
    return ReadinessResult(all(value == "ok" for value in checks.values()), checks)
