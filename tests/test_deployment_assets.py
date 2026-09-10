from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]


def test_compose_runs_reference_agent_with_healthcheck_and_persistent_data_volume():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    service = compose["services"]["reference-agent"]
    assert service["build"]["context"] == "."
    assert service["build"]["args"]["BUILD_REV"] == "${BUILD_REV:-source}"
    assert service["healthcheck"]["test"] == ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]
    assert "reference-agent-data:/data" in service["volumes"]
    assert compose["volumes"]["reference-agent-data"]["name"] == "${REFERENCE_AGENT_VOLUME:-local-production-drill_reference-agent-data}"


def test_container_contract_keeps_runtime_configuration_external_and_has_no_secret_value():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "uvicorn" in dockerfile
    assert "DATABASE_PATH=/data/reference_agent.db" in env_example
    assert "LLM_API_KEY=" in env_example
    assert "sk-" not in env_example


def test_dockerfile_installs_real_client_extras_for_configured_model_runtime():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "pip install --no-cache-dir .[real]" in dockerfile


def test_local_compose_remains_a_safe_loopback_default_when_production_overlay_is_opt_in():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    service = compose["services"]["reference-agent"]

    assert service["ports"] == ['127.0.0.1:${REFERENCE_AGENT_PORT:-8000}:8000']
    assert "docker-compose.production.yml" not in (ROOT / "docker-compose.yml").read_text(encoding="utf-8")


def test_model_config_reload_script_recreates_container_and_waits_for_health():
    script = (ROOT / "deploy" / "reload-model-config.ps1").read_text(encoding="utf-8")
    assert "--force-recreate" in script
    assert "--wait" in script
    assert "/api/model-profiles" in script
