"""Consistent, self-describing backups for SQLite databases."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class BackupResult:
    path: Path
    sha256: str
    schema_versions: Mapping[str, int]
    integrity_ok: bool


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _integrity_check(path: Path) -> bool:
    connection = sqlite3.connect(str(path))
    try:
        rows = connection.execute("PRAGMA integrity_check").fetchall()
    finally:
        connection.close()
    return rows == [("ok",)]


def schema_versions(path: Path) -> dict[str, int]:
    connection = sqlite3.connect(str(path))
    try:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_meta'"
        ).fetchone()
        if table is None:
            return {}
        rows = connection.execute("SELECT component, version FROM schema_meta ORDER BY component").fetchall()
    finally:
        connection.close()
    return {str(component): int(version) for component, version in rows}


def _manifest_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".manifest.json")


def backup_database(source: Path, target: Path) -> BackupResult:
    """Create an online SQLite backup and atomically publish its manifest."""
    source = Path(source)
    target = Path(target)
    if not source.is_file():
        raise ValueError("backup source database is unavailable")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    manifest_temporary: Path | None = None
    try:
        source_connection = sqlite3.connect("file:" + source.resolve().as_posix() + "?mode=ro", uri=True)
        destination_connection = sqlite3.connect(str(temporary))
        try:
            source_connection.backup(destination_connection)
        finally:
            destination_connection.close()
            source_connection.close()
        if not _integrity_check(temporary):
            raise RuntimeError("backup integrity check failed")
        versions = schema_versions(temporary)
        checksum = _sha256(temporary)
        descriptor, manifest_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".manifest.tmp", dir=target.parent)
        os.close(descriptor)
        manifest_temporary = Path(manifest_name)
        manifest_temporary.write_text(
            json.dumps({"schema_versions": versions, "sha256": checksum}, sort_keys=True), encoding="utf-8"
        )
        os.replace(temporary, target)
        os.replace(manifest_temporary, _manifest_path(target))
        return BackupResult(target, checksum, versions, True)
    finally:
        if temporary.exists():
            temporary.unlink()
        if manifest_temporary is not None and manifest_temporary.exists():
            manifest_temporary.unlink()
