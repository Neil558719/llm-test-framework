"""FastAPI integration for OIDC bearer tokens and opaque browser sessions."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from typing import Any, Mapping
from urllib.parse import urlencode

from fastapi import Depends, Header, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from .models import AuthenticatedPrincipal, RoleMapper, VALID_ROLES
from .oidc import DiscoveryOidcMetadataClient, OidcVerifier
from .session import SessionStore


def _unauthorized() -> None:
    raise HTTPException(status_code=401, detail="unauthorized")


def _forbidden() -> None:
    raise HTTPException(status_code=403, detail="forbidden")


class AuthRuntime:
    """The app-facing authentication boundary.

    A disabled runtime is only permissive for explicitly selected development
    mode. This preserves local fixtures while making an accidentally disabled
    production auth configuration fail closed.
    """

    def __init__(
        self,
        *,
        session_store: SessionStore | None,
        cookie_name: str = "qe_session",
        environment: str = "production",
        verifier: OidcVerifier | None,
        cookie_secure: bool = True,
        cookie_samesite: str = "lax",
        metadata_client: Any | None = None,
        redirect_uri: str = "",
        client_id: str = "",
        redirect_allowlist: tuple[str, ...] = (),
    ) -> None:
        self.session_store = session_store
        self.cookie_name = cookie_name
        self.csrf_cookie_name = cookie_name + "_csrf"
        self.environment = environment
        self.verifier = verifier
        self.cookie_secure = cookie_secure
        self.cookie_samesite = cookie_samesite
        self.metadata_client = metadata_client
        self.redirect_uri = redirect_uri
        self.client_id = client_id
        self.redirect_allowlist = redirect_allowlist

    @classmethod
    def disabled(cls, *, environment: str = "development") -> "AuthRuntime":
        return cls(session_store=None, verifier=None, environment=environment, cookie_secure=False)

    @classmethod
    def from_environment(cls) -> "AuthRuntime":
        environment = os.getenv("QE_ENVIRONMENT", "development").strip().lower()
        if environment == "development":
            return cls.disabled(environment=environment)
        from qe_platform.production import ProductionSettings

        settings = ProductionSettings.from_environment()
        raw_mapping = os.getenv("OIDC_ROLE_MAPPING", "")
        try:
            parsed = json.loads(raw_mapping) if raw_mapping else {role: role for role in VALID_ROLES}
        except json.JSONDecodeError as exc:
            raise ValueError("OIDC_ROLE_MAPPING must be a JSON object") from exc
        if not isinstance(parsed, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in parsed.items()):
            raise ValueError("OIDC_ROLE_MAPPING must be a JSON object")
        metadata = DiscoveryOidcMetadataClient(
            issuer=settings.oidc_issuer,
            audience=settings.oidc_audience,
            client_id=settings.oidc_client_id,
            redirect_uri=settings.oidc_redirect_uri,
            jwks_url=settings.oidc_jwks_url,
        )
        return cls(
            session_store=SessionStore(settings.auth_database, session_secret=settings.auth_session_secret),
            cookie_name=settings.auth_cookie_name,
            environment=settings.environment,
            verifier=OidcVerifier(metadata, role_mapper=RoleMapper(settings.oidc_roles_claim, parsed)),
            cookie_secure=settings.auth_cookie_secure,
            cookie_samesite=settings.auth_cookie_samesite,
            metadata_client=metadata,
            redirect_uri=settings.oidc_redirect_uri,
            client_id=settings.oidc_client_id,
            redirect_allowlist=tuple(
                value.strip()
                for value in os.getenv("OIDC_REDIRECT_ALLOWLIST", "").split(",")
                if value.strip()
            ),
        )

    @property
    def development_mode(self) -> bool:
        return self.environment == "development"

    def principal_from_request(self, request: Request | None, authorization: str | None) -> AuthenticatedPrincipal | None:
        if self.development_mode:
            return AuthenticatedPrincipal("development", frozenset({"viewer", "reviewer", "releaser", "admin"}))
        if isinstance(authorization, str) and authorization.startswith("Bearer "):
            if self.verifier is None:
                return None
            token = authorization[7:].strip()
            try:
                return self.verifier.verify_access_token(token)
            except Exception:
                return None
        if request is None or self.session_store is None:
            return None
        session = self.session_store.get(request.cookies.get(self.cookie_name, ""))
        if session is None:
            return None
        return AuthenticatedPrincipal(session.subject, session.roles)

    def require(self, request: Request, role: str | None = None, authorization: str | None = None) -> AuthenticatedPrincipal:
        principal = self.principal_from_request(request, authorization or request.headers.get("Authorization"))
        if principal is None:
            _unauthorized()
        if role is not None and not principal.has_role(role):
            _forbidden()
        return principal

    def require_csrf(self, request: Request, authorization: str | None = None, csrf_token: str | None = None) -> None:
        if self.development_mode or (isinstance(authorization, str) and authorization.startswith("Bearer ")):
            return
        if self.session_store is None:
            _unauthorized()
        session = self.session_store.get(request.cookies.get(self.cookie_name, ""))
        supplied = csrf_token if csrf_token is not None else request.headers.get("X-CSRF-Token")
        if session is None:
            _unauthorized()
        if not self.session_store.verify_csrf(session, supplied):
            _forbidden()

    def authorize_redirect(self, target: str) -> str:
        if not self._login_available() or self.session_store is None:
            _unauthorized()
        if not self._valid_redirect_target(target):
            _forbidden()
        attempt = self.session_store.create_authorization_attempt(target)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(attempt.code_verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
        try:
            endpoint = getattr(self.metadata_client, "authorization_endpoint", "")
        except Exception:
            raise HTTPException(status_code=401, detail="unauthorized") from None
        if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
            _unauthorized()
        return endpoint + ("&" if "?" in endpoint else "?") + urlencode(
            {
                "response_type": "code",
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "scope": "openid",
                "state": attempt.state,
                "nonce": attempt.nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )

    def complete_authorization(self, code: str, state: str) -> tuple[AuthenticatedPrincipal, str, str, str]:
        if not self._login_available() or self.session_store is None:
            _unauthorized()
        attempt = self.session_store.consume_authorization_attempt(state)
        exchange = getattr(self.metadata_client, "exchange_code", None)
        if attempt is None or not isinstance(code, str) or not code or not callable(exchange):
            _unauthorized()
        try:
            tokens = exchange(code=code, code_verifier=attempt.code_verifier, redirect_uri=self.redirect_uri)
            id_token = tokens.get("id_token") if isinstance(tokens, Mapping) else None
            principal = self.verifier.verify_id_token(id_token, attempt.nonce, audience=self.client_id) if self.verifier is not None else None
        except Exception:
            raise HTTPException(status_code=401, detail="unauthorized") from None
        if principal is None:
            _unauthorized()
        # The raw token exists only long enough to bootstrap the browser. The
        # store receives its hash and no IdP-provided value can influence it.
        csrf_token = secrets.token_urlsafe(32)
        session = self.session_store.create(principal.subject, principal.roles, csrf_token=csrf_token)
        return principal, session.session_id, csrf_token, attempt.redirect_target

    def _login_available(self) -> bool:
        return self.verifier is not None and self.metadata_client is not None and bool(self.redirect_uri and self.client_id)

    def _valid_redirect_target(self, target: str) -> bool:
        if target.startswith("/") and not target.startswith("//"):
            return True
        return target in self.redirect_allowlist


def require_user(runtime: AuthRuntime):
    def dependency(request: Request, authorization: str | None = Header(default=None, alias="Authorization")) -> AuthenticatedPrincipal:
        return runtime.require(request, authorization=authorization)

    return dependency


def require_role(runtime: AuthRuntime, role: str):
    def dependency(principal: AuthenticatedPrincipal = Depends(require_user(runtime))) -> AuthenticatedPrincipal:
        if not principal.has_role(role):
            _forbidden()
        return principal

    return dependency


def require_csrf(runtime: AuthRuntime):
    def dependency(
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    ) -> None:
        runtime.require_csrf(request, authorization=authorization, csrf_token=x_csrf_token)

    return dependency


def install_auth_routes(app, runtime: AuthRuntime) -> None:
    """Install browser login endpoints without exposing tokens in responses."""

    @app.get("/auth/login")
    def auth_login(next: str = "/") -> Response:
        return RedirectResponse(runtime.authorize_redirect(next), status_code=302)

    @app.get("/auth/callback")
    def auth_callback(code: str = "", state: str = "") -> Response:
        _principal, session_id, csrf_token, redirect_target = runtime.complete_authorization(code, state)
        response = RedirectResponse(redirect_target, status_code=302)
        response.set_cookie(
            runtime.cookie_name,
            session_id,
            httponly=True,
            secure=runtime.cookie_secure,
            samesite=runtime.cookie_samesite,
            path="/",
        )
        # This separate SameSite cookie is readable by same-origin browser code;
        # only its hash is stored, while the authenticated cookie stays HttpOnly.
        response.set_cookie(
            runtime.csrf_cookie_name,
            csrf_token,
            httponly=False,
            secure=runtime.cookie_secure,
            samesite=runtime.cookie_samesite,
            path="/",
        )
        return response

    @app.post("/auth/logout")
    def auth_logout(request: Request) -> Response:
        runtime.require(request)
        runtime.require_csrf(request)
        if runtime.session_store is not None:
            runtime.session_store.revoke(request.cookies.get(runtime.cookie_name, ""))
        response = Response(status_code=204)
        response.delete_cookie(runtime.cookie_name, path="/")
        response.delete_cookie(runtime.csrf_cookie_name, path="/")
        return response
