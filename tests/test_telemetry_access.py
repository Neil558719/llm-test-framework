"""Production read access and authenticated attribution, using only local stores."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from qe_platform.auth.dependencies import AuthRuntime, install_auth_routes
from qe_platform.auth.models import AuthenticatedPrincipal
from qe_platform.auth.session import SessionStore
from qe_platform.quality_loop.storage import SQLiteQualityRepository
from qe_platform.storage import SQLiteTelemetryRepository
from qe_platform.telemetry.api import create_telemetry_app
from qe_platform.telemetry.redaction import fingerprint
from qe_platform.telemetry.settings import TelemetrySettings
from reference_agent.app import create_app
from tests.test_quality_loop_api import SCENARIO, _create_promotion
from tests.test_quality_loop_models import _report_payload
from tests.test_telemetry_api import HASH_KEY, INGEST_TOKEN
from tests.test_telemetry_storage import utc


READ_PATHS = (
    "/api/traces?trace_id=trace-1", "/api/traces/trace-1", "/api/feedback?trace_id=trace-1",
    "/api/reviews", "/api/reviews/{review_id}", "/api/promotions/{promotion_id}",
    "/api/quality/trends", "/api/quality/links",
    "/api/quality/release-validations/{validation_id}",
)
ROLES = ("viewer", "reviewer", "releaser", "admin")


@pytest.fixture
def access(tmp_path):
    now = utc("2026-09-10T00:00:00+00:00")
    database = tmp_path / "telemetry.db"
    settings = TelemetrySettings(str(database), HASH_KEY, INGEST_TOKEN, 30)
    repo = SQLiteTelemetryRepository(database, hash_key=HASH_KEY, clock=lambda: now)
    quality = SQLiteQualityRepository(database, clock=lambda: now)
    development = TestClient(create_telemetry_app(
        settings, repo, quality, auth_runtime=AuthRuntime.disabled(),
    ))
    promotion = _create_promotion(development)
    headers = {"X-QE-Telemetry-Token": INGEST_TOKEN}
    for run_id in ("baseline", "candidate"):
        assert development.post("/api/quality/offline-runs", headers=headers,
                                json=_report_payload(run_id=run_id)).status_code == 201
    validation = development.post("/api/quality/release-validations", headers=headers, json={
        "baseline_run_id": "baseline", "candidate_run_id": "candidate",
        "max_low_quality_rate_increase": 1.0,
    })
    assert validation.status_code == 201
    store = SessionStore(tmp_path / "auth.db", clock=lambda: now)
    runtime = AuthRuntime(session_store=store, verifier=None, environment="production")
    app = create_telemetry_app(settings, repo, quality, auth_runtime=runtime)
    install_auth_routes(app, runtime)
    client = TestClient(app)

    def login(roles):
        session = store.create("signed-in-subject", set(roles), expires_at=now + timedelta(minutes=5),
                               csrf_token="local-csrf")
        client.cookies.set(runtime.cookie_name, session.session_id)
        return {"X-CSRF-Token": "local-csrf"}

    return {
        "client": client, "development": development, "login": login, "runtime": runtime,
        "review_id": promotion["review_id"], "promotion_id": promotion["promotion_id"],
        "feedback_id": development.get("/api/feedback?trace_id=trace-1").json()["feedback"][0]["feedback_id"],
        "validation_id": validation.json()["validation_id"], "tmp_path": tmp_path,
    }


@pytest.mark.parametrize("path", READ_PATHS)
def test_anonymous_production_reads_are_401_before_lookup_or_query_validation(access, path):
    url = path.format(**access)
    assert access["development"].get(url).status_code == 200
    response = access["client"].get(url)
    assert response.status_code == 401
    assert response.json() == {"detail": "unauthorized"}


@pytest.mark.parametrize("path", READ_PATHS)
@pytest.mark.parametrize("role", ROLES)
def test_existing_business_roles_can_read_without_csrf(access, path, role):
    access["login"]({role})
    assert access["client"].get(path.format(**access)).status_code == 200


@pytest.mark.parametrize("path", READ_PATHS)
def test_authenticated_subject_without_business_role_cannot_read(access, path):
    access["login"](set())
    assert access["client"].get(path.format(**access)).status_code == 403


@pytest.mark.parametrize("path", ["/api/traces/missing", "/api/reviews/missing",
                                  "/api/promotions/missing", "/api/quality/release-validations/missing",
                                  "/api/traces?limit=bad", "/api/quality/trends?from=bad"])
def test_anonymous_read_errors_do_not_precede_authentication(access, path):
    assert access["client"].get(path).status_code == 401


@pytest.mark.parametrize("kind,role,actor", [("feedback", "viewer", "reporter_id"),
                                            ("review", "reviewer", "reviewer_id"),
                                            ("feedback", "admin", "reporter_id"),
                                            ("review", "admin", "reviewer_id")])
@pytest.mark.parametrize("identity", ["omitted", "same", "forged", "null", "number"])
def test_production_actor_is_bound_to_subject(access, kind, role, actor, identity):
    headers = access["login"]({role})
    if kind == "feedback":
        path = "/api/traces/trace-1/feedback"
        payload = {"category": "correct", "source": "ui"}
    else:
        path = f"/api/feedback/{access['feedback_id']}/review"
        payload = {"status": "confirmed", "attribution": "model", "priority": "high"}
    if identity != "omitted":
        payload[actor] = {"same": "signed-in-subject", "forged": "someone-else", "null": None, "number": 123}[identity]
    response = access["client"].post(path, headers=headers, json=payload)
    if identity in {"omitted", "same"}:
        assert response.status_code in {200, 201}
        field = "reporter_fingerprint" if kind == "feedback" else "reviewer_fingerprint"
        assert response.json()[field] == fingerprint("signed-in-subject", HASH_KEY)
        assert "signed-in-subject" not in response.text
    else:
        assert response.status_code == 400
        assert "someone-else" not in response.text


@pytest.mark.parametrize("kind,role", [("feedback", "viewer"), ("review", "reviewer")])
def test_actor_writes_authenticate_before_body_and_keep_csrf_and_roles(access, kind, role):
    path = "/api/traces/trace-1/feedback" if kind == "feedback" else f"/api/feedback/{access['feedback_id']}/review"
    assert access["client"].post(path, content="invalid JSON").status_code == 401
    assert access["client"].post(path, json={"reporter_id": "forged", "reviewer_id": "forged"}).status_code == 401
    access["login"]({role})
    assert access["client"].post(path, json={}).status_code == 403
    assert access["client"].post(path, headers={"X-CSRF-Token": "wrong"}, json={}).status_code == 403
    headers = access["login"]({"releaser"})
    assert access["client"].post(path, headers=headers, json={}).status_code == 403


@pytest.mark.parametrize("role", ROLES)
def test_metrics_remains_admin_only_and_health_and_auth_bootstrap_stay_public(access, role):
    client = access["client"]
    assert client.get("/api/metrics").status_code == 401
    assert client.get("/api/health/live").status_code == 200
    assert client.get("/api/health/ready").status_code == 503  # No real IdP configured.
    assert client.get("/auth/session").json()["authenticated"] is False
    assert client.get("/auth/callback?code=untrusted&state=untrusted").status_code == 401
    access["login"]({role})
    assert client.get("/api/metrics").status_code == (200 if role == "admin" else 403)


@pytest.mark.parametrize("kind", ["feedback", "review"])
def test_development_preserves_explicit_legacy_actor_and_required_field(access, kind):
    client = access["development"]
    if kind == "feedback":
        path, actor = "/api/traces/trace-1/feedback", "reporter_id"
        payload = {"category": "correct", "source": "ui"}
    else:
        path, actor = f"/api/feedback/{access['feedback_id']}/review", "reviewer_id"
        payload = {"status": "confirmed", "attribution": "tool", "priority": "low"}
    assert client.post(path, json=payload).status_code == 400
    response = client.post(path, json={**payload, actor: "legacy-caller"})
    assert response.status_code in {200, 201}
    field = "reporter_fingerprint" if kind == "feedback" else "reviewer_fingerprint"
    assert response.json()[field] == fingerprint("legacy-caller", HASH_KEY)


def test_reference_business_reads_require_role_but_static_login_shell_remains_available(access):
    app = create_app(str(access["tmp_path"] / "reference.db"), auth_runtime=access["runtime"])
    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/model-profiles").status_code == 401
    assert client.get("/api/sessions/missing").status_code == 401
    assert client.get("/api/metrics").status_code == 401
    access["login"](set())
    client.cookies.update(access["client"].cookies)
    assert client.get("/api/model-profiles").status_code == 403
    assert client.get("/api/sessions/missing").status_code == 403
    access["login"]({"viewer"})
    client.cookies.update(access["client"].cookies)
    assert client.get("/api/model-profiles").status_code == 200
    assert client.get("/api/sessions/missing").status_code == 404
    assert client.get("/api/metrics").status_code == 403
    access["login"]({"admin"})
    client.cookies.update(access["client"].cookies)
    assert client.get("/api/metrics").status_code == 200


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("kind,required", [("feedback", "viewer"), ("review", "reviewer"),
                                           ("promote", "releaser"), ("run", "releaser"),
                                           ("link", "releaser"), ("validation", "releaser")])
def test_cookie_write_role_matrix_and_csrf_are_preserved(access, role, kind, required):
    writes = {
        "feedback": ("/api/traces/trace-1/feedback", {"category": "correct", "source": "ui"}),
        "review": (f"/api/feedback/{access['feedback_id']}/review",
                   {"status": "confirmed", "attribution": "model", "priority": "high"}),
        "promote": (f"/api/reviews/{access['review_id']}/promote", {"scenario": SCENARIO}),
        "run": ("/api/quality/offline-runs", _report_payload(run_id="another-run")),
        "link": ("/api/quality/links", {"promotion_id": access["promotion_id"], "offline_run_id": "candidate"}),
        "validation": ("/api/quality/release-validations", {
            "baseline_run_id": "baseline", "candidate_run_id": "candidate", "max_low_quality_rate_increase": 1.0,
        }),
    }
    path, payload = writes[kind]
    client = access["client"]
    assert client.post(path, json=payload).status_code == 401
    headers = access["login"]({role})
    assert client.post(path, json=payload).status_code == 403
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code in ({200, 201} if role in {required, "admin"} else {403})


def test_machine_token_is_not_a_human_read_or_actor_credential(access):
    client = access["client"]
    headers = {"X-QE-Telemetry-Token": INGEST_TOKEN}
    assert client.get("/api/traces?trace_id=trace-1", headers=headers).status_code == 401
    assert client.post("/api/traces/trace-1/feedback", headers=headers,
                       json={"category": "correct", "source": "ui", "reporter_id": "forged"}).status_code == 401
    assert client.post("/api/quality/offline-runs", headers=headers,
                       json=_report_payload(run_id="machine-run")).status_code == 201


def test_verified_bearer_subject_is_used_without_cookie_csrf(access):
    class LocalVerifier:
        def verify_access_token(self, token):
            if token != "local-test-bearer":
                raise ValueError("invalid local token")
            return AuthenticatedPrincipal("verified-bearer-subject", frozenset({"viewer"}))

    access["runtime"].verifier = LocalVerifier()
    client = access["client"]
    assert client.get("/api/traces?trace_id=trace-1", headers={"Authorization": "Bearer invalid"}).status_code == 401
    headers = {"Authorization": "Bearer local-test-bearer"}
    assert client.get("/api/traces?trace_id=trace-1", headers=headers).status_code == 200
    response = client.post("/api/traces/trace-1/feedback", headers=headers, json={"category": "correct", "source": "ui"})
    assert response.status_code == 201
    assert response.json()["reporter_fingerprint"] == fingerprint("verified-bearer-subject", HASH_KEY)
    assert client.post("/api/traces/trace-1/feedback", headers=headers, json={
        "category": "correct", "source": "ui", "reporter_id": "signed-in-subject",
    }).status_code == 400


def test_invalid_revoked_and_disabled_production_sessions_fail_closed(access):
    client = access["client"]
    client.cookies.set("qe_session", "untrusted-session")
    assert client.get("/api/traces?trace_id=trace-1").status_code == 401
    access["login"]({"viewer"})
    access["runtime"].session_store.revoke(client.cookies.get("qe_session"))
    assert client.get("/api/traces?trace_id=trace-1").status_code == 401
    access["runtime"].session_store = None
    assert client.get("/api/traces?trace_id=trace-1").status_code == 401
    assert client.post("/api/traces/trace-1/feedback", json={"reporter_id": "forged"}).status_code == 401