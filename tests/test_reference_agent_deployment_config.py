from __future__ import annotations

from reference_agent.app import create_app
from pathlib import Path


def test_compose_passes_reference_agent_model_runtime_configuration():
    compose = Path(__file__).parents[1].joinpath("docker-compose.yml").read_text(encoding="utf-8")
    for name in (
        "REFERENCE_AGENT_MODEL_MODE",
        "REFERENCE_AGENT_MODEL_PROVIDER",
        "REFERENCE_AGENT_MODEL",
        "REFERENCE_AGENT_MODEL_BASE_URL",
        "REFERENCE_AGENT_MODEL_API_KEY",
    ):
        assert name in compose


def test_application_uses_configured_database_path_when_no_argument_is_given(monkeypatch, tmp_path):
    configured_database = tmp_path / "runtime" / "reference_agent.db"
    configured_database.parent.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REFERENCE_AGENT_DATABASE", str(configured_database))

    create_app()

    assert configured_database.exists()
    assert not (tmp_path / "reference_agent.db").exists()
