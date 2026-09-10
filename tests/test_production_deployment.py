from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]


class _ComposeLoader(yaml.SafeLoader):
    pass


def _construct_reset(loader: yaml.SafeLoader, node: yaml.Node):
    loader.construct_scalar(node)
    return None


_ComposeLoader.add_constructor("!reset", _construct_reset)


def _source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _production_compose() -> dict[str, object]:
    return yaml.load(_source("docker-compose.production.yml"), Loader=_ComposeLoader)


def test_production_compose_requires_server_settings_and_uses_secret_files():
    compose = _production_compose()
    service = compose["services"]["reference-agent"]
    environment = service["environment"]

    assert environment["QE_ENVIRONMENT"] == "production"
    for name in ("OIDC_ISSUER", "OIDC_AUDIENCE", "OIDC_CLIENT_ID", "OIDC_REDIRECT_URI", "OIDC_JWKS_URL"):
        assert ":?" in environment[name]
    assert environment["AUTH_SESSION_SECRET_FILE"] == "/run/secrets/auth_session_secret"
    assert environment["QE_TELEMETRY_HASH_KEY_FILE"] == "/run/secrets/qe_telemetry_hash_key"
    assert environment["QE_TELEMETRY_INGEST_TOKEN_FILE"] == "/run/secrets/qe_telemetry_ingest_token"
    assert "AUTH_SESSION_SECRET" not in environment
    assert "QE_TELEMETRY_HASH_KEY" not in environment
    assert "QE_TELEMETRY_INGEST_TOKEN" not in environment
    assert {item["source"] for item in service["secrets"]} == {
        "auth_session_secret",
        "qe_telemetry_hash_key",
        "qe_telemetry_ingest_token",
        "reference_agent_model_api_key",
    }


def test_production_compose_locks_down_container_and_pins_image_digest():
    compose = _production_compose()
    service = compose["services"]["reference-agent"]

    assert "@${REFERENCE_AGENT_IMAGE_DIGEST:?" in service["image"]
    assert service["build"] is None
    assert service["user"] == "10001:10001"
    assert service["read_only"] is True
    assert service["restart"] == "unless-stopped"
    assert service["healthcheck"]["test"][-1].endswith("/api/health/ready')")
    assert service["deploy"]["resources"]["limits"]["memory"]
    assert service["deploy"]["resources"]["reservations"]["memory"]
    assert any(item["target"] == "/data" for item in service["volumes"])


def test_dockerfile_keeps_non_root_runtime_and_does_not_bake_credentials():
    dockerfile = _source("Dockerfile")

    assert "--user-group" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "COPY . /app" in dockerfile
    assert "AUTH_SESSION_SECRET=" not in dockerfile
    assert "QE_TELEMETRY_INGEST_TOKEN=" not in dockerfile


def test_cross_platform_deployment_scripts_share_reported_operation_contracts():
    expected_pairs = {
        "migrate": ("deploy/migrate.sh", "deploy/migrate.ps1"),
        "backup": ("deploy/backup.sh", "deploy/backup.ps1"),
        "smoke": ("deploy/smoke.sh", "deploy/smoke.ps1"),
    }

    for operation, paths in expected_pairs.items():
        for path in paths:
            source = _source(path)
            assert "ReportPath" in source or "REPORT_PATH" in source or "SMOKE_REPORT" in source
            assert f'"operation": "{operation}"' in source or f'operation = "{operation}"' in source
            assert '"status": "ok"' in source or 'status = "ok"' in source


def test_deployment_scripts_use_database_volume_inputs_and_fail_fast():
    for path in ("deploy/migrate.sh", "deploy/backup.sh", "deploy/restore.sh", "deploy/smoke.sh"):
        source = _source(path)
        assert "set -eu" in source
    for path in ("deploy/migrate.ps1", "deploy/backup.ps1", "deploy/rollback.ps1", "deploy/smoke.ps1"):
        source = _source(path)
        assert "$ErrorActionPreference = \"Stop\"" in source

    assert "REFERENCE_AGENT_VOLUME" in _source("deploy/migrate.sh")
    assert "REFERENCE_AGENT_VOLUME" in _source("deploy/backup.sh")
    assert "REFERENCE_AGENT_VOLUME" in _source("deploy/restore.sh")
    assert "ImageDigest" in _source("deploy/rollback.ps1")


def test_compose_operations_forward_declared_database_and_volume_inputs():
    for path in ("deploy/migrate.sh", "deploy/backup.sh", "deploy/restore.sh"):
        source = _source(path)
        assert 'export DATABASE_PATH="$database_path"' in source
        assert 'export REFERENCE_AGENT_VOLUME="$volume"' in source
    for path in ("deploy/migrate.ps1", "deploy/backup.ps1"):
        source = _source(path)
        assert "$env:DATABASE_PATH = $DatabasePath" in source
        assert "$env:REFERENCE_AGENT_VOLUME = $Volume" in source
