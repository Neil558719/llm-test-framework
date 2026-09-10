from __future__ import annotations

import pytest

from qe_platform.production import ProductionSettings, SecretSource


def test_production_mode_rejects_each_required_configuration_without_leaking_secret(tmp_path):
    secret = "do-not-print-this-secret"
    base = {
        "QE_ENVIRONMENT": "production",
        "REFERENCE_AGENT_DATABASE": str(tmp_path / "reference.db"),
        "QE_TELEMETRY_DATABASE": str(tmp_path / "telemetry.db"),
        "QE_AUTH_DATABASE": str(tmp_path / "auth.db"),
        "OIDC_ISSUER": "https://id.example.test/tenant/",
        "OIDC_AUDIENCE": "quality-platform",
        "OIDC_CLIENT_ID": "quality-web",
        "OIDC_REDIRECT_URI": "https://quality.example.test/auth/callback",
        "AUTH_SESSION_SECRET": secret,
        "QE_TELEMETRY_HASH_KEY": secret,
        "QE_TELEMETRY_INGEST_TOKEN": secret,
    }
    for required in (
        "OIDC_ISSUER",
        "OIDC_AUDIENCE",
        "OIDC_CLIENT_ID",
        "OIDC_REDIRECT_URI",
        "AUTH_SESSION_SECRET",
        "QE_TELEMETRY_HASH_KEY",
        "QE_TELEMETRY_INGEST_TOKEN",
        "REFERENCE_AGENT_DATABASE",
        "QE_TELEMETRY_DATABASE",
        "QE_AUTH_DATABASE",
    ):
        values = dict(base)
        values.pop(required)
        with pytest.raises(ValueError) as excinfo:
            ProductionSettings.from_environment(values)
        assert required in str(excinfo.value)
        assert secret not in str(excinfo.value)


def test_development_defaults_are_local_safe_and_public_serialization_redacts_secrets():
    settings = ProductionSettings.from_environment({"QE_ENVIRONMENT": "development"})

    assert settings.environment == "development"
    assert settings.reference_agent_database == "reference_agent.db"
    assert settings.telemetry_database == "telemetry.db"
    assert settings.auth_database == "auth.db"
    assert settings.oidc_issuer == ""
    assert settings.public_dict()["environment"] == "development"
    assert "auth_session_secret" not in settings.public_dict()
    assert "AUTH_SESSION_SECRET" not in repr(settings)


def test_secret_file_is_used_when_direct_environment_value_is_empty(tmp_path):
    secret_path = tmp_path / "session-secret"
    secret_path.write_bytes(b"file-only-secret\r\n")
    source = SecretSource.from_environment(
        {"AUTH_SESSION_SECRET": "", "AUTH_SESSION_SECRET_FILE": str(secret_path)}
    )

    assert source.get("AUTH_SESSION_SECRET") == "file-only-secret"
    assert "file-only-secret" not in repr(source)
    assert "file-only-secret" not in str(source)


def test_secret_file_overrides_a_stale_direct_environment_value(tmp_path):
    secret_path = tmp_path / "session-secret"
    secret_path.write_text("mounted-secret\n", encoding="utf-8")
    source = SecretSource.from_environment(
        {
            "AUTH_SESSION_SECRET": "stale-environment-secret",
            "AUTH_SESSION_SECRET_FILE": str(secret_path),
        }
    )

    assert source.get("AUTH_SESSION_SECRET") == "mounted-secret"
    assert "mounted-secret" not in repr(source)
    assert "stale-environment-secret" not in repr(source)


def test_production_urls_and_retention_are_normalized_and_validated(tmp_path):
    values = {
        "QE_ENVIRONMENT": "production",
        "REFERENCE_AGENT_DATABASE": str(tmp_path / "reference.db"),
        "QE_TELEMETRY_DATABASE": str(tmp_path / "telemetry.db"),
        "QE_AUTH_DATABASE": str(tmp_path / "auth.db"),
        "OIDC_ISSUER": "https://id.example.test/tenant/",
        "OIDC_AUDIENCE": "quality-platform",
        "OIDC_CLIENT_ID": "quality-web",
        "OIDC_REDIRECT_URI": "https://quality.example.test/auth/callback/",
        "AUTH_SESSION_SECRET": "session-secret",
        "QE_TELEMETRY_HASH_KEY": "hash-key",
        "QE_TELEMETRY_INGEST_TOKEN": "ingest-token",
        "QE_TELEMETRY_RETENTION_DAYS": "31",
    }
    settings = ProductionSettings.from_environment(values)

    assert settings.oidc_issuer == "https://id.example.test/tenant"
    assert settings.oidc_redirect_uri == "https://quality.example.test/auth/callback"
    assert settings.telemetry_retention_days == 31
    assert settings.public_dict()["oidc_issuer"] == "https://id.example.test/tenant"

    values["QE_TELEMETRY_RETENTION_DAYS"] = "0"
    with pytest.raises(ValueError, match="QE_TELEMETRY_RETENTION_DAYS"):
        ProductionSettings.from_environment(values)


@pytest.mark.parametrize("name", ("OIDC_ISSUER", "OIDC_REDIRECT_URI", "OIDC_JWKS_URL"))
def test_production_urls_reject_userinfo_and_do_not_publish_it(tmp_path, name):
    values = {
        "QE_ENVIRONMENT": "production",
        "REFERENCE_AGENT_DATABASE": str(tmp_path / "reference.db"),
        "QE_TELEMETRY_DATABASE": str(tmp_path / "telemetry.db"),
        "QE_AUTH_DATABASE": str(tmp_path / "auth.db"),
        "OIDC_ISSUER": "https://id.example.test/tenant",
        "OIDC_AUDIENCE": "quality-platform",
        "OIDC_CLIENT_ID": "quality-web",
        "OIDC_REDIRECT_URI": "https://quality.example.test/auth/callback",
        "AUTH_SESSION_SECRET": "session-secret",
        "QE_TELEMETRY_HASH_KEY": "hash-key",
        "QE_TELEMETRY_INGEST_TOKEN": "ingest-token",
    }
    values[name] = "https://private-user:private-password@id.example.test/endpoint"

    with pytest.raises(ValueError, match=name) as excinfo:
        ProductionSettings.from_environment(values)
    assert "private-user" not in str(excinfo.value)
    assert "private-password" not in str(excinfo.value)
