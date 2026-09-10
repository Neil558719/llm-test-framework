from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

from .secrets import SecretSource


_ENVIRONMENTS = frozenset({"development", "production"})
_SAMESITE_VALUES = frozenset({"lax", "strict", "none"})


def _required_string(values: Mapping[str, str], name: str, *, production: bool) -> str:
    value = values.get(name, "")
    if not isinstance(value, str):
        raise ValueError("%s must be a string" % name)
    value = value.strip()
    if production and not value:
        raise ValueError("%s must be configured" % name)
    return value


def _url(value: str, name: str, *, production: bool) -> str:
    if not value:
        return ""
    parsed = urlsplit(value.strip())
    allowed_schemes = {"https"} if production else {"http", "https"}
    if parsed.scheme not in allowed_schemes or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("%s must be an absolute %s URL" % (name, "HTTPS" if production else "HTTP"))
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _database_path(value: str, name: str, *, production: bool) -> str:
    if not value:
        if production:
            raise ValueError("%s must be configured" % name)
        return ""
    if value == ":memory:" and not production:
        return value
    path = Path(value)
    if production and not path.is_absolute():
        raise ValueError("%s must be an absolute path in production" % name)
    if not path.name or path.name in {".", ".."}:
        raise ValueError("%s must name a database file" % name)
    return str(path)


def _positive_integer(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("%s must be a positive integer" % name) from exc
    if str(value).strip() != str(parsed) or parsed <= 0:
        raise ValueError("%s must be a positive integer" % name)
    return parsed


def _boolean(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ValueError("%s must be true or false" % name)


@dataclass(frozen=True)
class ProductionSettings:
    environment: str
    reference_agent_database: str
    telemetry_database: str
    auth_database: str
    oidc_issuer: str
    oidc_audience: str
    oidc_client_id: str
    oidc_redirect_uri: str
    oidc_jwks_url: str
    oidc_roles_claim: str
    auth_cookie_name: str
    auth_cookie_secure: bool
    auth_cookie_samesite: str
    telemetry_retention_days: int
    auth_session_secret: str = field(repr=False)
    telemetry_hash_key: str = field(repr=False)
    telemetry_ingest_token: str = field(repr=False)

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "ProductionSettings":
        values = os.environ if environ is None else environ
        environment = str(values.get("QE_ENVIRONMENT", "development")).strip().lower()
        if environment not in _ENVIRONMENTS:
            raise ValueError("QE_ENVIRONMENT must be development or production")
        production = environment == "production"
        secrets = SecretSource.from_environment(values)
        issuer = _url(_required_string(values, "OIDC_ISSUER", production=production), "OIDC_ISSUER", production=production)
        redirect_uri = _url(_required_string(values, "OIDC_REDIRECT_URI", production=production), "OIDC_REDIRECT_URI", production=production)
        jwks_url = _url(str(values.get("OIDC_JWKS_URL", "")).strip(), "OIDC_JWKS_URL", production=production)
        samesite = str(values.get("AUTH_COOKIE_SAMESITE", "lax")).strip().lower()
        if samesite not in _SAMESITE_VALUES:
            raise ValueError("AUTH_COOKIE_SAMESITE must be lax, strict, or none")
        secure = _boolean(str(values.get("AUTH_COOKIE_SECURE", "true" if production else "false")), "AUTH_COOKIE_SECURE")
        if production and not secure:
            raise ValueError("AUTH_COOKIE_SECURE must be true in production")
        settings = cls(
            environment=environment,
            reference_agent_database=_database_path(str(values.get("REFERENCE_AGENT_DATABASE", "reference_agent.db")), "REFERENCE_AGENT_DATABASE", production=production),
            telemetry_database=_database_path(str(values.get("QE_TELEMETRY_DATABASE", "telemetry.db")), "QE_TELEMETRY_DATABASE", production=production),
            auth_database=_database_path(str(values.get("QE_AUTH_DATABASE", "auth.db")), "QE_AUTH_DATABASE", production=production),
            oidc_issuer=issuer,
            oidc_audience=_required_string(values, "OIDC_AUDIENCE", production=production),
            oidc_client_id=_required_string(values, "OIDC_CLIENT_ID", production=production),
            oidc_redirect_uri=redirect_uri,
            oidc_jwks_url=jwks_url,
            oidc_roles_claim=str(values.get("OIDC_ROLES_CLAIM", "roles")).strip() or "roles",
            auth_cookie_name=str(values.get("AUTH_COOKIE_NAME", "qe_session")).strip() or "qe_session",
            auth_cookie_secure=secure,
            auth_cookie_samesite=samesite,
            telemetry_retention_days=_positive_integer(str(values.get("QE_TELEMETRY_RETENTION_DAYS", "30")), "QE_TELEMETRY_RETENTION_DAYS"),
            auth_session_secret=secrets.require("AUTH_SESSION_SECRET") if production else secrets.get("AUTH_SESSION_SECRET"),
            telemetry_hash_key=secrets.require("QE_TELEMETRY_HASH_KEY") if production else secrets.get("QE_TELEMETRY_HASH_KEY"),
            telemetry_ingest_token=secrets.require("QE_TELEMETRY_INGEST_TOKEN") if production else secrets.get("QE_TELEMETRY_INGEST_TOKEN"),
        )
        return settings

    def public_dict(self) -> dict[str, Any]:
        return {
            "environment": self.environment,
            "reference_agent_database": self.reference_agent_database,
            "telemetry_database": self.telemetry_database,
            "auth_database": self.auth_database,
            "oidc_issuer": self.oidc_issuer,
            "oidc_audience": self.oidc_audience,
            "oidc_client_id": self.oidc_client_id,
            "oidc_redirect_uri": self.oidc_redirect_uri,
            "oidc_jwks_url": self.oidc_jwks_url,
            "oidc_roles_claim": self.oidc_roles_claim,
            "auth_cookie_name": self.auth_cookie_name,
            "auth_cookie_secure": self.auth_cookie_secure,
            "auth_cookie_samesite": self.auth_cookie_samesite,
            "telemetry_retention_days": self.telemetry_retention_days,
            "auth_session_secret_configured": bool(self.auth_session_secret),
            "telemetry_hash_key_configured": bool(self.telemetry_hash_key),
            "telemetry_ingest_token_configured": bool(self.telemetry_ingest_token),
        }
