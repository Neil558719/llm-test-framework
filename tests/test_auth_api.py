from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
from urllib.parse import parse_qs, urlparse

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from qe_platform.auth.dependencies import AuthRuntime, install_auth_routes, require_csrf, require_role, require_user
from qe_platform.auth.models import AuthenticatedPrincipal
from qe_platform.auth.models import RoleMapper
from qe_platform.auth.oidc import OidcVerifier
from qe_platform.auth.session import SessionStore
from qe_platform.telemetry.api import create_telemetry_app
from qe_platform.telemetry.settings import TelemetrySettings
from reference_agent.app import create_app
from tests.test_telemetry_api import safe_payload


NOW = datetime(2026, 9, 10, tzinfo=timezone.utc)


def test_auth_dependencies_return_stable_401_403_and_require_csrf_for_cookie_writes(tmp_path):
    store = SessionStore(tmp_path / "auth.db", clock=lambda: NOW)
    created = store.create("alice", {"reviewer"}, expires_at=NOW + timedelta(minutes=5), csrf_token="csrf-token")
    runtime = AuthRuntime(
        session_store=store,
        cookie_name="qe_session",
        environment="production",
        verifier=None,
    )
    app = FastAPI()

    @app.get("/user")
    def user(principal=Depends(require_user(runtime))):
        return {"subject": principal.subject}

    @app.post("/review")
    def review(principal=Depends(require_role(runtime, "reviewer")), _=Depends(require_csrf(runtime))):
        return {"subject": principal.subject}

    client = TestClient(app)
    assert client.get("/user").status_code == 401
    assert client.get("/user").json() == {"detail": "unauthorized"}
    client.cookies.set("qe_session", created.session_id)
    assert client.post("/review").status_code == 403
    assert client.post("/review").json() == {"detail": "forbidden"}
    assert client.post("/review", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert client.post("/review", headers={"X-CSRF-Token": "csrf-token"}).json() == {"subject": "alice"}


def test_development_runtime_keeps_existing_local_workflows_explicitly_enabled():
    runtime = AuthRuntime.disabled(environment="development")
    assert runtime.principal_from_request(None, None) == AuthenticatedPrincipal("development", frozenset({"admin", "releaser", "reviewer", "viewer"}))


def test_production_telemetry_human_writes_require_role_and_csrf_but_machine_ingest_stays_token_based(tmp_path):
    store = SessionStore(tmp_path / "auth.db", clock=lambda: NOW)
    viewer = store.create("viewer", {"viewer"}, expires_at=NOW + timedelta(minutes=5), csrf_token="viewer-csrf")
    runtime = AuthRuntime(session_store=store, cookie_name="qe_session", environment="production", verifier=None)
    app = create_telemetry_app(
        TelemetrySettings(str(tmp_path / "telemetry.db"), "hash", "machine-token", 30), auth_runtime=runtime
    )
    client = TestClient(app)

    assert client.post("/api/traces", json=safe_payload()).status_code == 401
    assert client.post("/api/traces", headers={"X-QE-Telemetry-Token": "machine-token"}, json=safe_payload()).status_code == 201
    assert client.post("/api/traces/trace-1/feedback", json={"category": "correct", "reporter_id": "v", "source": "ui"}).status_code == 401
    client.cookies.set("qe_session", viewer.session_id)
    assert client.post("/api/traces/trace-1/feedback", json={"category": "correct", "reporter_id": "v", "source": "ui"}).status_code == 403
    assert client.post(
        "/api/traces/trace-1/feedback",
        headers={"X-CSRF-Token": "viewer-csrf"},
        json={"category": "correct", "reporter_id": "v", "source": "ui"},
    ).status_code == 201


def test_production_reference_agent_admin_write_requires_authenticated_admin_and_csrf(tmp_path):
    store = SessionStore(tmp_path / "auth.db", clock=lambda: NOW)
    admin = store.create("admin", {"admin"}, expires_at=NOW + timedelta(minutes=5), csrf_token="admin-csrf")
    runtime = AuthRuntime(session_store=store, cookie_name="qe_session", environment="production", verifier=None)
    client = TestClient(create_app(str(tmp_path / "agent.db"), auth_runtime=runtime))

    assert client.put("/api/model-profile", json={"profile": "mock"}).status_code == 401
    client.cookies.set("qe_session", admin.session_id)
    assert client.put("/api/model-profile", json={"profile": "mock"}).status_code == 403
    assert client.put(
        "/api/model-profile", headers={"X-CSRF-Token": "admin-csrf"}, json={"profile": "mock"}
    ).status_code == 200


def test_oidc_authorization_uses_pkce_state_nonce_and_redirects_to_the_validated_target(tmp_path):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk.update({"kid": "login-key", "alg": "RS256"})

    class LoginClient:
        issuer = "https://issuer.example.test"
        audience = "qe-platform"
        allowed_algorithms = ("RS256",)
        authorization_endpoint = "https://issuer.example.test/authorize"
        id_token = ""

        def get_jwks(self, *, force_refresh=False):
            return {"keys": [jwk]}

        def exchange_code(self, **kwargs):
            assert kwargs["code_verifier"]
            return {"id_token": self.id_token}

    client = LoginClient()
    store = SessionStore(tmp_path / "auth.db", clock=lambda: NOW)
    runtime = AuthRuntime(
        session_store=store,
        cookie_name="qe_session",
        environment="production",
        verifier=OidcVerifier(client, lambda: NOW, role_mapper=RoleMapper("roles", {"qe-view": "viewer"})),
        metadata_client=client,
        redirect_uri="https://platform.example.test/auth/callback",
        client_id="client-id",
    )
    location = runtime.authorize_redirect("/after-login")
    query = parse_qs(urlparse(location).query)
    assert query["code_challenge_method"] == ["S256"]
    state = query["state"][0]
    with sqlite3.connect(tmp_path / "auth.db") as connection:
        nonce = connection.execute("SELECT nonce FROM oidc_authorization_attempts WHERE state = ?", (state,)).fetchone()[0]
    client.id_token = jwt.encode(
        {
            "sub": "alice", "iss": client.issuer, "aud": "client-id",
            "exp": int((NOW + timedelta(minutes=5)).timestamp()), "nonce": nonce, "roles": ["qe-view"],
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "login-key"},
    )

    principal, session_id, csrf_token, target = runtime.complete_authorization("code", state)

    assert principal == AuthenticatedPrincipal("alice", frozenset({"viewer"}))
    assert target == "/after-login"
    assert store.verify_csrf(store.get(session_id), csrf_token)


def test_callback_sets_readable_csrf_cookie_and_logout_requires_session_and_csrf(tmp_path):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk.update({"kid": "callback-key", "alg": "RS256"})

    class LoginClient:
        issuer = "https://issuer.example.test"
        audience = "api-audience"
        allowed_algorithms = ("RS256",)
        authorization_endpoint = "https://issuer.example.test/authorize"
        id_token = ""

        def get_jwks(self, *, force_refresh=False):
            return {"keys": [jwk]}

        def exchange_code(self, **kwargs):
            return {"id_token": self.id_token}

    login_client = LoginClient()
    store = SessionStore(tmp_path / "auth.db", clock=lambda: NOW)
    runtime = AuthRuntime(
        session_store=store, cookie_name="qe_session", environment="production",
        verifier=OidcVerifier(login_client, lambda: NOW, role_mapper=RoleMapper("roles", {"qe-view": "viewer"})),
        metadata_client=login_client, redirect_uri="https://platform.example.test/auth/callback", client_id="browser-client",
    )
    app = FastAPI()
    install_auth_routes(app, runtime)
    browser = TestClient(app, follow_redirects=False)
    login = browser.get("/auth/login?next=/after")
    query = parse_qs(urlparse(login.headers["location"]).query)
    state = query["state"][0]
    with sqlite3.connect(tmp_path / "auth.db") as connection:
        nonce = connection.execute("SELECT nonce FROM oidc_authorization_attempts WHERE state = ?", (state,)).fetchone()[0]
    login_client.id_token = jwt.encode(
        {"sub": "alice", "iss": login_client.issuer, "aud": "browser-client", "exp": int((NOW + timedelta(minutes=5)).timestamp()), "nonce": nonce, "roles": ["qe-view"]},
        private_key, algorithm="RS256", headers={"kid": "callback-key"},
    )
    callback = browser.get(f"/auth/callback?code=code&state={state}")
    assert callback.status_code == 302
    assert callback.headers["location"] == "/after"
    cookie_headers = callback.headers.get_list("set-cookie")
    session_cookie = next(value for value in cookie_headers if value.startswith("qe_session="))
    csrf_cookie = next(value for value in cookie_headers if value.startswith("qe_session_csrf="))
    assert "HttpOnly" in session_cookie
    assert "HttpOnly" not in csrf_cookie
    session_id = browser.cookies.get("qe_session")
    csrf_token = browser.cookies.get("qe_session_csrf")
    assert session_id and csrf_token and store.get(session_id) is not None
    forged = TestClient(app)
    assert forged.post("/auth/logout").status_code == 401
    browser.cookies.set("qe_session", session_id)
    assert browser.post("/auth/logout").status_code == 403
    assert browser.post("/auth/logout", headers={"X-CSRF-Token": csrf_token}).status_code == 204
    assert store.get(session_id) is None


def test_production_runtime_loads_configured_redirect_allowlist(monkeypatch, tmp_path):
    monkeypatch.setenv("QE_ENVIRONMENT", "production")
    monkeypatch.setenv("REFERENCE_AGENT_DATABASE", str(tmp_path / "agent.db"))
    monkeypatch.setenv("QE_TELEMETRY_DATABASE", str(tmp_path / "telemetry.db"))
    monkeypatch.setenv("QE_AUTH_DATABASE", str(tmp_path / "auth.db"))
    monkeypatch.setenv("OIDC_ISSUER", "https://issuer.example.test")
    monkeypatch.setenv("OIDC_AUDIENCE", "api-audience")
    monkeypatch.setenv("OIDC_CLIENT_ID", "browser-client")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "https://platform.example.test/auth/callback")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://issuer.example.test/jwks")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "session-secret")
    monkeypatch.setenv("QE_TELEMETRY_HASH_KEY", "hash-key")
    monkeypatch.setenv("QE_TELEMETRY_INGEST_TOKEN", "ingest-token")
    monkeypatch.setenv("OIDC_REDIRECT_ALLOWLIST", "https://console.example.test/return, https://other.example.test/done")

    runtime = AuthRuntime.from_environment()

    assert runtime.redirect_allowlist == ("https://console.example.test/return", "https://other.example.test/done")


def test_login_metadata_failure_returns_safe_unauthorized_response(tmp_path):
    class FailingMetadata:
        authorization_endpoint = property(lambda self: (_ for _ in ()).throw(RuntimeError("metadata-sentinel-secret")))

    runtime = AuthRuntime(
        session_store=SessionStore(tmp_path / "auth.db", clock=lambda: NOW), cookie_name="qe_session",
        environment="production", verifier=object(), metadata_client=FailingMetadata(),
        redirect_uri="https://platform.example.test/auth/callback", client_id="browser-client",
    )
    app = FastAPI()
    install_auth_routes(app, runtime)
    response = TestClient(app, raise_server_exceptions=False).get("/auth/login")

    assert response.status_code == 401
    assert "sentinel" not in response.text
