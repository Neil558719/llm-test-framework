from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from qe_platform.telemetry.sink import HttpTelemetrySink, NoopTelemetrySink, telemetry_sink_from_environment
from reference_agent.app import create_app
from reference_agent.deployment import create_deployment_app


ROOT = Path(__file__).parents[1]


def test_compose_passes_reference_agent_model_runtime_configuration():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
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


def test_telemetry_sink_from_environment_is_noop_until_all_required_values_exist(monkeypatch):
    monkeypatch.setenv("QE_TELEMETRY_ENDPOINT", "http://telemetry.local/api/traces")
    monkeypatch.setenv("QE_TELEMETRY_INGEST_TOKEN", "token-value")
    monkeypatch.delenv("QE_TELEMETRY_HASH_KEY", raising=False)

    assert isinstance(telemetry_sink_from_environment(), NoopTelemetrySink)

    monkeypatch.setenv("QE_TELEMETRY_HASH_KEY", "hash-key")
    monkeypatch.setenv("QE_TELEMETRY_RETENTION_DAYS", "45")

    sink = telemetry_sink_from_environment()
    assert isinstance(sink, HttpTelemetrySink)
    assert sink.endpoint == "http://telemetry.local/api/traces"
    assert sink.hash_key == "hash-key"
    assert sink.retention_days == 45


def test_compose_declares_only_reference_agent_telemetry_environment_pass_through():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    environment = compose["services"]["reference-agent"]["environment"]

    assert environment["QE_TELEMETRY_ENDPOINT"] == "${QE_TELEMETRY_ENDPOINT:-}"
    assert environment["QE_TELEMETRY_INGEST_TOKEN"] == "${QE_TELEMETRY_INGEST_TOKEN:-}"
    assert environment["QE_TELEMETRY_HASH_KEY"] == "${QE_TELEMETRY_HASH_KEY:-}"
    assert environment["QE_TELEMETRY_RETENTION_DAYS"] == "${QE_TELEMETRY_RETENTION_DAYS:-30}"
    assert sorted(key for key in environment if key.startswith("QE_TELEMETRY_")) == [
        "QE_TELEMETRY_ENDPOINT",
        "QE_TELEMETRY_HASH_KEY",
        "QE_TELEMETRY_INGEST_TOKEN",
        "QE_TELEMETRY_RETENTION_DAYS",
    ]


def test_deployment_app_does_not_expose_telemetry_configuration(monkeypatch):
    monkeypatch.setenv("QE_TELEMETRY_ENDPOINT", "http://telemetry.local/api/traces")
    monkeypatch.setenv("QE_TELEMETRY_INGEST_TOKEN", "private-token")
    monkeypatch.setenv("QE_TELEMETRY_HASH_KEY", "private-hash-key")

    client = TestClient(create_deployment_app())

    health = client.get("/api/health").json()
    profiles = client.get("/api/model-profiles").json()
    serialized = f"{health} {profiles}"
    assert "QE_TELEMETRY" not in serialized
    assert "private-token" not in serialized
    assert "private-hash-key" not in serialized
    assert "telemetry.local" not in serialized
