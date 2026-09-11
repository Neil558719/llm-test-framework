"""Offline production-hardening contract using only ephemeral local inputs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from qe_platform.auth.dependencies import AuthRuntime
from qe_platform.auth.models import RoleMapper
from qe_platform.auth.oidc import OidcVerifier
from qe_platform.auth.session import SessionStore
from qe_platform.ops import backup_database, restore_database
from qe_platform.telemetry.api import create_telemetry_app
from qe_platform.telemetry.settings import TelemetrySettings
from qe_platform.telemetry.sink import HttpTelemetrySink, telemetry_sink_from_environment
from reference_agent.app import create_app
from reference_agent.services import ApprovalService, TicketService
from reference_agent.storage import SQLiteStore, _MIGRATIONS
from tests.test_telemetry_api import safe_payload


NOW = datetime(2026, 9, 10, tzinfo=timezone.utc)


class _FakeOidcMetadata:
    issuer = "https://issuer.example.test"
    audience = "qe-api"
    allowed_algorithms = ("RS256",)

    def __init__(self, jwk: dict[str, str]) -> None:
        self._jwk = jwk

    def get_jwks(self, *, force_refresh: bool = False) -> dict[str, list[dict[str, str]]]:
        return {"keys": [self._jwk]}


def _production_runtime(tmp_path: Path) -> tuple[AuthRuntime, rsa.RSAPrivateKey]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk.update({"kid": "contract-key", "alg": "RS256"})
    metadata = _FakeOidcMetadata(jwk)
    runtime = AuthRuntime(
        session_store=SessionStore(tmp_path / "auth.db", clock=lambda: NOW, session_secret="contract-session-secret"),
        cookie_name="qe_session",
        environment="production",
        metadata_client=metadata, client_id="browser-client",
        redirect_uri="https://platform.example.test/auth/callback",
        verifier=OidcVerifier(
            metadata,
            lambda: NOW,
            role_mapper=RoleMapper("roles", {"platform-admin": "admin", "quality-reviewer": "reviewer"}),
        ),
    )
    return runtime, key


def test_production_hardening_contract_covers_authenticated_api_machine_ingest_and_durable_restore(tmp_path):
    runtime, signing_key = _production_runtime(tmp_path)
    agent_database = tmp_path / "reference-agent.db"
    telemetry_database = tmp_path / "telemetry.db"
    secret_values = {"hash": "contract-hash-secret", "token": "contract-machine-token"}

    token = jwt.encode(
        {
            "sub": "release-manager",
            "iss": "https://issuer.example.test",
            "aud": "qe-api",
            "exp": int((NOW + timedelta(minutes=5)).timestamp()),
            "roles": ["platform-admin", "quality-reviewer"],
        },
        signing_key,
        algorithm="RS256",
        headers={"kid": "contract-key"},
    )
    agent = TestClient(create_app(str(agent_database), auth_runtime=runtime))

    assert agent.put("/api/model-profile", json={"profile": "mock"}).status_code == 401
    assert agent.put(
        "/api/model-profile",
        headers={"Authorization": f"Bearer {token}"},
        json={"profile": "mock"},
    ).status_code == 200

    for route in ("/api/chat", "/api/chat/stream"):
        response = agent.post(route, headers={"Authorization": f"Bearer {token}"}, json={"message": "VPN", "user_id": "forged-user"})
        assert response.status_code == 200
    assert agent.post("/api/chat", headers={"Authorization": "Bearer invalid"}, json={"message": "VPN"}).status_code == 401

    browser_session = runtime.session_store.create(
        "viewer", {"viewer"}, expires_at=NOW + timedelta(minutes=5), csrf_token="contract-csrf-token"
    )
    telemetry = TestClient(
        create_telemetry_app(
            TelemetrySettings(str(telemetry_database), secret_values["hash"], secret_values["token"], 30),
            auth_runtime=runtime,
        )
    )
    assert telemetry.post("/api/traces", json=safe_payload("contract-trace")).status_code == 401
    assert telemetry.post(
        "/api/traces",
        headers={"X-QE-Telemetry-Token": secret_values["token"]},
        json=safe_payload("contract-trace"),
    ).status_code == 201
    telemetry.cookies.set("qe_session", browser_session.session_id)
    assert telemetry.post(
        "/api/traces/contract-trace/feedback",
        headers={"X-CSRF-Token": "contract-csrf-token"},
        json={"category": "correct", "reporter_id": "reviewer", "source": "ui"},
    ).status_code == 201
    assert telemetry.get("/api/health/ready").status_code == 200

    store = SQLiteStore(agent_database)
    tickets = TicketService(repository=store)
    approvals = ApprovalService(repository=store)
    ticket = tickets.create_ticket("U1001", "PC-1001", "vpn", "high", "contract-ticket")
    approval = approvals.create_approval("U1001", "VPN", "remote work", "contract-approval")
    store.close()

    backup = tmp_path / "reference-agent.backup.db"
    result = backup_database(agent_database, backup)
    restored = tmp_path / "restored-reference-agent.db"
    restore_database(backup, restored, {"reference_agent": max(item.version for item in _MIGRATIONS)})
    restored_store = SQLiteStore(restored)
    try:
        assert restored_store.get_ticket(ticket["ticket_id"]) == ticket
        assert restored_store.get_approval(approval["approval_id"]) == approval
    finally:
        restored_store.close()

    assert agent.get("/api/health/ready").status_code == 200
    metrics = agent.get("/api/metrics", headers={"Authorization": f"Bearer {token}"})
    assert metrics.status_code == 200
    assert secret_values["hash"] not in metrics.text
    assert secret_values["token"] not in metrics.text
    assert result.integrity_ok is True


def test_production_hardening_contract_reads_machine_telemetry_secrets_from_ephemeral_files(tmp_path):
    """A missing secret-file lookup would silently disable production telemetry."""
    token_file = tmp_path / "machine-token"
    hash_file = tmp_path / "telemetry-hash"
    token_file.write_text("file-machine-token\n", encoding="utf-8")
    hash_file.write_text("file-hash-key\n", encoding="utf-8")

    sink = telemetry_sink_from_environment(
        {
            "QE_TELEMETRY_ENDPOINT": "http://127.0.0.1:9999/api/traces",
            "QE_TELEMETRY_INGEST_TOKEN_FILE": str(token_file),
            "QE_TELEMETRY_HASH_KEY_FILE": str(hash_file),
        }
    )

    assert isinstance(sink, HttpTelemetrySink)
    assert sink.ingest_token == "file-machine-token"
    assert sink.hash_key == "file-hash-key"
    assert "file-machine-token" not in repr(sink)
