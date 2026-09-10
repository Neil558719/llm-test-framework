"""Safe restore operations for manifest-backed SQLite backups."""

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

from .backup import _integrity_check, _manifest_path, _pending_path, schema_versions


class RestoreError(RuntimeError):
    """A restore was rejected before the target database changed."""


@dataclass(frozen=True)
class RestoreResult:
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


def _load_manifest(backup: Path) -> tuple[str, dict[str, int]]:
    if _pending_path(backup).exists():
        raise RestoreError("backup publication requires recovery")
    try:
        payload = json.loads(_manifest_path(backup).read_text(encoding="utf-8"))
        checksum = payload["sha256"]
        versions = payload["schema_versions"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RestoreError("backup manifest is invalid") from exc
    if not isinstance(checksum, str) or len(checksum) != 64 or not all(char in "0123456789abcdef" for char in checksum):
        raise RestoreError("backup manifest is invalid")
    if not isinstance(versions, dict) or not all(
        isinstance(component, str) and isinstance(version, int) and not isinstance(version, bool) and version > 0
        for component, version in versions.items()
    ):
        raise RestoreError("backup manifest is invalid")
    return checksum, dict(versions)


def _validate_compatibility(actual: Mapping[str, int], expected: Mapping[str, int]) -> None:
    if not isinstance(expected, Mapping) or not all(
        isinstance(component, str) and isinstance(version, int) and not isinstance(version, bool) and version > 0
        for component, version in expected.items()
    ):
        raise ValueError("expected schema versions are invalid")
    for component, version in expected.items():
        found = actual.get(component)
        if found is None or found > version:
            raise RestoreError("backup schema version is incompatible")


def restore_database(backup: Path, target: Path, expected_versions: Mapping[str, int]) -> RestoreResult:
    """Verify a backup completely before atomically replacing ``target``."""
    backup = Path(backup)
    target = Path(target)
    if not backup.is_file():
        raise RestoreError("backup database is unavailable")
    checksum, manifest_versions = _load_manifest(backup)
    if _sha256(backup) != checksum:
        raise RestoreError("backup checksum does not match")
    try:
        actual_versions = schema_versions(backup)
        integrity_ok = _integrity_check(backup)
    except sqlite3.DatabaseError as exc:
        raise RestoreError("backup integrity check failed") from exc
    if not integrity_ok:
        raise RestoreError("backup integrity check failed")
    if actual_versions != manifest_versions:
        raise RestoreError("backup schema metadata does not match")
    _validate_compatibility(actual_versions, expected_versions)
    if any(Path(str(target) + suffix).exists() for suffix in ("-wal", "-shm")):
        raise RestoreError("target database is not quiescent")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, staging_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".restore", dir=target.parent)
    os.close(descriptor)
    staging = Path(staging_name)
    try:
        shutil.copyfile(backup, staging)
        if not _integrity_check(staging) or schema_versions(staging) != actual_versions:
            raise RestoreError("backup integrity check failed")
        os.replace(staging, target)
    finally:
        if staging.exists():
            staging.unlink()
    return RestoreResult(target, checksum, actual_versions, True)
