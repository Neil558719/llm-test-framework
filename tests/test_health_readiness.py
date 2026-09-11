from __future__ import annotations

from fastapi.testclient import TestClient

from qe_platform.auth.dependencies import AuthRuntime
from qe_platform.ops.metrics import MetricsRegistry
from qe_platform.ops.readiness import readiness
from qe_platform.quality_loop.storage import SQLiteQualityRepository
from qe_platform.telemetry.api import create_telemetry_app
from qe_platform.telemetry.settings import TelemetrySettings
from reference_agent.app import create_app


def test_readiness_distinguishes_database_failure_from_liveness(tmp_path):
    result = readiness({"reference_agent": tmp_path / "missing" / "agent.db"})

    assert result.ready is False
    assert result.checks == {"reference_agent": "unavailable"}


def test_reference_agent_has_compatible_liveness_and_database_readiness(tmp_path):
    client = TestClient(create_app(str(tmp_path / "agent.db")))

    assert client.get("/api/health").json() == {"status": "ok", "service": "reference-agent"}
    assert client.get("/api/health/live").json() == {"status": "ok", "service": "reference-agent"}
    ready = client.get("/api/health/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "service": "reference-agent", "checks": {"database": "ok"}}


def test_metrics_registry_has_no_arbitrary_labels_or_payload_values():
    registry = MetricsRegistry()
    registry.increment("http_requests_total")
    registry.observe_latency("http_request_latency_ms", 12.5)

    assert registry.snapshot() == {
        "counters": {"http_requests_total": 1},
        "latencies": {"http_request_latency_ms": {"count": 1, "sum_ms": 12.5}},
    }


def test_telemetry_metrics_are_admin_protected_and_secret_free(tmp_path):
    runtime = AuthRuntime.disabled(environment="development")
    app = create_telemetry_app(
        TelemetrySettings(str(tmp_path / "telemetry.db"), "hash-key-should-not-leak", "ingest-token-should-not-leak"),
        auth_runtime=runtime,
    )
    client = TestClient(app)

    client.get("/api/health/live")
    response = client.get("/api/metrics")

    assert response.status_code == 200
    assert response.json()["counters"]["telemetry_requests_total"] > 0
    assert response.json()["latencies"]["telemetry_request_latency_ms"]["count"] > 0
    assert response.headers["content-type"].startswith("application/json")
    assert "hash-key-should-not-leak" not in response.text
    assert "ingest-token-should-not-leak" not in response.text


def test_telemetry_readiness_fails_when_quality_repository_is_unavailable(tmp_path):
    quality_repository = SQLiteQualityRepository(tmp_path / "quality.db")
    quality_repository.close()
    app = create_telemetry_app(
        TelemetrySettings(str(tmp_path / "telemetry.db"), "hash", "ingest"),
        quality_repository=quality_repository,
        auth_runtime=AuthRuntime.disabled(environment="development"),
    )

    response = TestClient(app).get("/api/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "service": "qe-telemetry",
        "checks": {"configuration": "ok", "telemetry": "ok", "quality": "unavailable"},
    }
