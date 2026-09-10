"""Consistent, self-describing backups for SQLite databases."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
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


def _pending_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".publish-pending")


def _temporary_path(target: Path, suffix: str) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=target.name + ".", suffix=suffix, dir=target.parent)
    os.close(descriptor)
    return Path(name)


def backup_database(source: Path, target: Path) -> BackupResult:
    """Create an online SQLite backup and atomically publish its manifest."""
    source = Path(source)
    target = Path(target)
    if not source.is_file():
        raise ValueError("backup source database is unavailable")
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = _pending_path(target)
    if pending.exists():
        raise RuntimeError("backup publication requires recovery")
    temporary = _temporary_path(target, ".tmp")
    manifest_temporary: Path | None = None
    previous_database: Path | None = None
    previous_manifest: Path | None = None
    pending_temporary: Path | None = None
    published = False
    recovered = False
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
        manifest_temporary = _temporary_path(target, ".manifest.tmp")
        manifest_temporary.write_text(
            json.dumps({"schema_versions": versions, "sha256": checksum}, sort_keys=True), encoding="utf-8"
        )
        manifest = _manifest_path(target)
        if target.is_file() and manifest.is_file():
            previous_database = _temporary_path(target, ".previous.db")
            previous_manifest = _temporary_path(target, ".previous.manifest")
            shutil.copyfile(target, previous_database)
            shutil.copyfile(manifest, previous_manifest)
        pending_temporary = _temporary_path(target, ".pending.tmp")
        pending_temporary.write_text('{"state":"publishing"}', encoding="utf-8")
        os.replace(pending_temporary, pending)
        pending_temporary = None
        try:
            os.replace(temporary, target)
            os.replace(manifest_temporary, manifest)
            published = True
        except OSError as exc:
            try:
                if previous_database is not None and previous_manifest is not None:
                    os.replace(previous_database, target)
                    previous_database = None
                    os.replace(previous_manifest, manifest)
                    previous_manifest = None
                else:
                    target.unlink(missing_ok=True)
                    manifest.unlink(missing_ok=True)
                recovered = True
            except OSError as recovery_error:
                raise RuntimeError("backup publication requires recovery") from recovery_error
            raise RuntimeError("backup publication failed") from exc
        return BackupResult(target, checksum, versions, True)
    finally:
        if (published or recovered) and pending.exists():
            pending.unlink()
        if temporary.exists():
            temporary.unlink()
        if manifest_temporary is not None and manifest_temporary.exists():
            manifest_temporary.unlink()
        if pending_temporary is not None and pending_temporary.exists():
            pending_temporary.unlink()
        if previous_database is not None and previous_database.exists():
            previous_database.unlink()
        if previous_manifest is not None and previous_manifest.exists():
            previous_manifest.unlink()
