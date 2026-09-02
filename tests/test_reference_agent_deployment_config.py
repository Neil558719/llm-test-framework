from __future__ import annotations

from reference_agent.app import create_app


def test_application_uses_configured_database_path_when_no_argument_is_given(monkeypatch, tmp_path):
    configured_database = tmp_path / "runtime" / "reference_agent.db"
    configured_database.parent.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REFERENCE_AGENT_DATABASE", str(configured_database))

    create_app()

    assert configured_database.exists()
    assert not (tmp_path / "reference_agent.db").exists()
