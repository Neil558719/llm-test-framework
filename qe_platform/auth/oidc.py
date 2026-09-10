"""OIDC/JWKS verification without retaining bearer tokens or IdP bodies."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

import jwt

from .models import AuthenticatedPrincipal, RoleMapper


class OidcMetadataClient(Protocol):
    issuer: str
    audience: str
    allowed_algorithms: tuple[str, ...]

    def get_jwks(self, *, force_refresh: bool = False) -> Mapping[str, Any]: ...


class OidcVerificationError(ValueError):
    """A deliberately payload-free authentication failure."""

    def __init__(self) -> None:
        super().__init__("invalid access token")


class OidcVerifier:
    """Validates signed bearer tokens against cached, refreshable JWKS data."""

    def __init__(
        self,
        metadata_client: OidcMetadataClient,
        clock: Callable[[], datetime] | None = None,
        *,
        role_mapper: RoleMapper | None = None,
    ) -> None:
        self._metadata_client = metadata_client
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._role_mapper = role_mapper or RoleMapper()
        self._jwks: Mapping[str, Any] | None = None

    def verify_access_token(self, token: str) -> AuthenticatedPrincipal:
        return self._verify(token)

    def verify_id_token(self, token: str, nonce: str) -> AuthenticatedPrincipal:
        return self._verify(token, nonce=nonce)

    def _verify(self, token: str, *, nonce: str | None = None) -> AuthenticatedPrincipal:
        if not isinstance(token, str) or not token:
            raise OidcVerificationError()
        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            kid = header.get("kid")
            allowed = tuple(getattr(self._metadata_client, "allowed_algorithms", ("RS256",)))
            if not isinstance(kid, str) or algorithm not in allowed:
                raise OidcVerificationError()
            key = self._key_for(kid)
            claims = jwt.decode(
                token,
                key,
                algorithms=list(allowed),
                audience=self._metadata_client.audience,
                issuer=self._metadata_client.issuer,
                options={"verify_exp": False, "require": ["sub", "exp", "iss", "aud"]},
            )
            subject = claims.get("sub")
            expires_at = claims.get("exp")
            if not isinstance(subject, str) or not subject or isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)):
                raise OidcVerificationError()
            now = self._clock()
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            if float(expires_at) <= now.astimezone(timezone.utc).timestamp():
                raise OidcVerificationError()
            if nonce is not None and claims.get("nonce") != nonce:
                raise OidcVerificationError()
            return AuthenticatedPrincipal(subject, self._role_mapper.roles_from_claims(claims))
        except OidcVerificationError:
            raise
        except Exception as exc:
            # Do not propagate decoder, key, or metadata text to API callers.
            raise OidcVerificationError() from exc

    def _key_for(self, kid: str) -> Any:
        key = self._find_key(self._cached_jwks(False), kid)
        if key is None:
            key = self._find_key(self._cached_jwks(True), kid)
        if key is None:
            raise OidcVerificationError()
        return jwt.PyJWK.from_dict(dict(key)).key

    def _cached_jwks(self, force_refresh: bool) -> Mapping[str, Any]:
        if force_refresh or self._jwks is None:
            value = self._metadata_client.get_jwks(force_refresh=force_refresh)
            if not isinstance(value, Mapping):
                raise OidcVerificationError()
            self._jwks = value
        return self._jwks

    @staticmethod
    def _find_key(jwks: Mapping[str, Any], kid: str) -> Mapping[str, Any] | None:
        keys = jwks.get("keys")
        if not isinstance(keys, list):
            return None
        for candidate in keys:
            if isinstance(candidate, Mapping) and candidate.get("kid") == kid:
                return candidate
        return None


class DiscoveryOidcMetadataClient:
    """Small generic OIDC Discovery client, lazy so startup never fetches IdP data."""

    allowed_algorithms = ("RS256", "RS384", "RS512", "ES256", "ES384", "ES512")

    def __init__(self, *, issuer: str, audience: str, client_id: str, redirect_uri: str, jwks_url: str = "") -> None:
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self._jwks_url = jwks_url
        self._metadata: Mapping[str, Any] | None = None

    @property
    def authorization_endpoint(self) -> str:
        return str(self._discovery().get("authorization_endpoint", ""))

    def get_jwks(self, *, force_refresh: bool = False) -> Mapping[str, Any]:
        address = self._jwks_url or str(self._discovery().get("jwks_uri", ""))
        return self._read_json(address)

    def exchange_code(self, *, code: str, code_verifier: str, redirect_uri: str) -> Mapping[str, Any]:
        endpoint = str(self._discovery().get("token_endpoint", ""))
        if not endpoint.startswith("https://"):
            raise OidcVerificationError()
        body = urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.client_id,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            }
        ).encode("ascii")
        request = UrlRequest(endpoint, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        with urlopen(request, timeout=5) as response:  # nosec B310 - endpoint is validated as HTTPS
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, Mapping):
            raise OidcVerificationError()
        return payload

    def _discovery(self) -> Mapping[str, Any]:
        if self._metadata is None:
            metadata = self._read_json(self.issuer + "/.well-known/openid-configuration")
            if metadata.get("issuer") != self.issuer:
                raise OidcVerificationError()
            self._metadata = metadata
        return self._metadata

    @staticmethod
    def _read_json(address: str) -> Mapping[str, Any]:
        if not isinstance(address, str) or not address.startswith("https://"):
            raise OidcVerificationError()
        with urlopen(address, timeout=5) as response:  # nosec B310 - OIDC settings validate HTTPS URLs
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, Mapping):
            raise OidcVerificationError()
        return payload
