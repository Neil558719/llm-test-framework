"""Exercise the actual Python payloads of privileged deployment helpers.

Docker and POSIX chown are unavailable on native Windows. Only chown is
substituted; SQLite backup, manifests, restore, and file I/O remain real.
The container workflow separately checks the Linux permission boundary.
"""
from pathlib import Path
import json
import os
import sqlite3
import sys
from types import SimpleNamespace

import pytest

from qe_platform.ops import backup_database
from tests.test_production_ops import _database


ROOT = Path(__file__).parents[1]


def _run_helper(script_name, arguments, monkeypatch):
    script = (ROOT / "deploy" / script_name).read_text(encoding="utf-8")
    payload = script.split("--entrypoint python reference-agent -c '\n", 1)[1].split("\n'", 1)[0]
    monkeypatch.setattr(sys, "argv", [script_name, *map(str, arguments)])
    exec(compile(payload, script_name + ":helper", "exec"), {"__name__": "__main__"})


def test_backup_hands_database_and_manifest_to_invoking_host_user(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    backup = tmp_path / "backup.db"
    _database(source)
    ownership_changes = []
    monkeypatch.setattr(os, "chown", lambda path, uid, gid: ownership_changes.append((Path(path), uid, gid)), raising=False)

    _run_helper("backup.sh", [source, backup, 1001, 1002], monkeypatch)

    manifest = backup.with_suffix(".db.manifest.json")
    assert ownership_changes == [(backup, 1001, 1002), (manifest, 1001, 1002)]
    assert json.loads(manifest.read_text(encoding="utf-8"))["schema_versions"] == {"reference_agent": 1}
    with sqlite3.connect(backup) as connection:
        assert connection.execute("SELECT value FROM records").fetchone() == ("kept",)


@pytest.mark.parametrize("existing_owner", [(10001, 10002), (0, 0), None])
def test_restore_returns_database_to_application_owner(tmp_path, monkeypatch, existing_owner):
    source = tmp_path / "source.db"
    backup = tmp_path / "backup.db"
    data = tmp_path / "data"
    data.mkdir()
    target = data / "agent.db"
    _database(source)
    backup_database(source, backup)
    if existing_owner is not None:
        _database(target)
    real_stat = Path.stat

    def application_owned_stat(path, *args, **kwargs):
        value = real_stat(path, *args, **kwargs)
        if path == target and existing_owner is not None:
            fields = list(value)
            fields[4:6] = existing_owner
            return os.stat_result(fields)
        return value

    ownership_changes = []
    monkeypatch.setattr(Path, "stat", application_owned_stat)
    monkeypatch.setattr(os, "chown", lambda path, uid, gid: ownership_changes.append((Path(path), uid, gid)), raising=False)
    application_users = {"appuser": SimpleNamespace(pw_uid=10001, pw_gid=10002)}
    monkeypatch.setitem(sys.modules, "pwd", SimpleNamespace(getpwnam=application_users.__getitem__))

    _run_helper("restore.sh", [backup, target], monkeypatch)

    assert len(ownership_changes) == 1
    owned_path, uid, gid = ownership_changes[0]
    assert (uid, gid) == (10001, 10002)
    assert owned_path.parent == data
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT value FROM records").fetchone() == ("kept",)