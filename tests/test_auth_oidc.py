from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from qe_platform.auth.models import AuthenticatedPrincipal, RoleMapper
from qe_platform.auth.oidc import OidcVerificationError, OidcVerifier
from qe_platform.auth.session import SessionStore


NOW = datetime(2026, 9, 10, tzinfo=timezone.utc)


class MetadataClient:
    issuer = "https://issuer.example.test"
    audience = "qe-platform"
    allowed_algorithms = ("RS256",)

    def __init__(self, jwks: dict[str, object]) -> None:
        self.jwks = jwks
        self.refreshes = 0

    def get_jwks(self, *, force_refresh: bool = False) -> dict[str, object]:
        if force_refresh:
            self.refreshes += 1
        return self.jwks


@pytest.fixture
def signing_material():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk.update({"kid": "key-1", "use": "sig", "alg": "RS256"})
    return private_key, {"keys": [public_jwk]}


def token(private_key, **claims):
    payload = {
        "sub": "alice",
        "iss": "https://issuer.example.test",
        "aud": "qe-platform",
        "exp": int((NOW + timedelta(minutes=5)).timestamp()),
        "roles": ["platform-reviewer", "unknown"],
        **claims,
    }
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "key-1"})


def test_verifier_checks_signature_issuer_audience_expiry_and_rotates_jwks(signing_material):
    private_key, jwks = signing_material
    metadata = MetadataClient(jwks)
    verifier = OidcVerifier(metadata, lambda: NOW, role_mapper=RoleMapper("roles", {"platform-reviewer": "reviewer"}))

    principal = verifier.verify_access_token(token(private_key))

    assert principal == AuthenticatedPrincipal("alice", frozenset({"reviewer"}))
    with pytest.raises(OidcVerificationError, match="invalid access token"):
        verifier.verify_access_token(token(private_key, iss="https://wrong.example.test"))
    with pytest.raises(OidcVerificationError, match="invalid access token"):
        verifier.verify_access_token(token(private_key, aud="other-audience"))
    with pytest.raises(OidcVerificationError, match="invalid access token"):
        verifier.verify_access_token(token(private_key, exp=int((NOW - timedelta(seconds=1)).timestamp())))
    with pytest.raises(OidcVerificationError, match="invalid access token"):
        verifier.verify_access_token("not.a.token")


def test_role_mapper_drops_unknown_roles_and_session_rows_never_store_raw_csrf(tmp_path):
    roles = RoleMapper("groups", {"qe-view": "viewer", "qe-admin": "admin"}).roles_from_claims(
        {"groups": ["qe-view", "not-a-role", "qe-admin"]}
    )
    assert roles == frozenset({"viewer", "admin"})
    assert RoleMapper("roles", {}).roles_from_claims({"roles": "admin"}) == frozenset()

    store = SessionStore(tmp_path / "auth.db", clock=lambda: NOW)
    created = store.create("alice", roles, expires_at=NOW + timedelta(minutes=5), csrf_token="csrf-raw-value")
    loaded = store.get(created.session_id)

    assert loaded is not None
    assert loaded.subject == "alice"
    assert loaded.roles == roles
    assert store.verify_csrf(loaded, "csrf-raw-value")
    assert not store.verify_csrf(loaded, "other")
    assert "csrf-raw-value" not in (tmp_path / "auth.db").read_bytes().decode("latin1")
    store.revoke(created.session_id)
    assert store.get(created.session_id) is None
