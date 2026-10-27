"""Application ownership is assigned by trusted server configuration."""

from datetime import timedelta
from dataclasses import replace
import json
import sqlite3

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from qe_platform.auth.dependencies import AuthRuntime
from qe_platform.auth.models import AuthenticatedPrincipal
from qe_platform.auth.session import SessionStore
from qe_platform.quality_loop.storage import SQLiteQualityRepository
from qe_platform.quality_loop.engine import validate_release
from qe_platform.quality_loop.models import ReleaseGatePolicy
from qe_platform.storage import SQLiteTelemetryRepository
from qe_platform.telemetry.api import create_telemetry_app
from qe_platform.telemetry.settings import TelemetrySettings
from tests.test_quality_loop_api import SCENARIO
from tests.test_quality_loop_models import _report_payload
from tests.report_integrity_fixtures import verified_payload, trusted_plan
from tests.test_telemetry_api import HASH_KEY, INGEST_TOKEN, safe_payload
from tests.test_telemetry_storage import utc


@pytest.fixture
def isolation(tmp_path, monkeypatch):
    now = utc("2026-09-10T00:00:00Z")
    database = tmp_path / "telemetry.db"
    settings = TelemetrySettings(str(database), HASH_KEY, INGEST_TOKEN, 30)
    repo = SQLiteTelemetryRepository(database, hash_key=HASH_KEY, clock=lambda: now)
    quality = SQLiteQualityRepository(database, clock=lambda: now)
    dev = TestClient(create_telemetry_app(settings, repo, quality, auth_runtime=AuthRuntime.disabled(), trusted_manifest_resolver=lambda payload: trusted_plan() if payload.get("schema_version") == "qe-run-v2" else None))
    token = {"X-QE-Telemetry-Token": INGEST_TOKEN}
    objects = {}
    for application in ("app-a", "app-b"):
        for index in (1, 2):
            trace_id = f"{application}-{index}"
            payload = safe_payload(trace_id, application)
            payload["timestamp"] = "2026-09-09T00:00:00Z"
            assert dev.post("/api/traces", headers=token, json=payload).status_code == 201
            feedback = dev.post(f"/api/traces/{trace_id}/feedback", json={
                "category": "hallucination", "reporter_id": "seed", "source": "ui",
            }).json()
            review = dev.post(f"/api/feedback/{feedback['feedback_id']}/review", json={
                "reviewer_id": "seed", "status": "confirmed", "attribution": "model", "priority": "high",
            }).json()
            promotion = dev.post(f"/api/reviews/{review['review_id']}/promote", json={"scenario": SCENARIO}).json()
            objects[trace_id] = {**feedback, **review, **promotion}
        for label in ("baseline", "candidate"):
            assert dev.post("/api/quality/offline-runs", headers=token, json=verified_payload(
                run_id=f"{application}-{label}", application=application,
            )).status_code == 201
        assert dev.post("/api/quality/links", headers=token, json={
            "promotion_id": objects[f"{application}-1"]["promotion_id"], "offline_run_id": f"{application}-candidate",
        }).status_code == 201
        # A fresh server-computed scoped artifact; legacy artifacts remain separate negative fixtures.
        validation = validate_release(quality, f"{application}-baseline", f"{application}-candidate",
            ReleaseGatePolicy(max_low_quality_rate_increase=1.0), allowed_applications=frozenset({application}))
        objects[application] = validation.as_dict()
    monkeypatch.setenv("QE_APPLICATION_ACCESS", json.dumps({"alice": ["app-a"], "bob": ["app-b"], "both": ["app-a", "app-b"]}))
    monkeypatch.setenv("QE_TELEMETRY_ALLOWED_APPLICATIONS", '["app-a"]')
    # Configuration is server-owned; never derived from request parameters/claims.
    configured = TelemetrySettings.from_environment({
        "QE_TELEMETRY_DATABASE": str(database), "QE_TELEMETRY_HASH_KEY": HASH_KEY,
        "QE_TELEMETRY_INGEST_TOKEN": INGEST_TOKEN, "QE_TELEMETRY_ALLOWED_APPLICATIONS": '["app-a"]',
    })
    sessions = SessionStore(tmp_path / "auth.db", clock=lambda: now)
    runtime = AuthRuntime(session_store=sessions, verifier=None, environment="production")

    def client(subject="alice", roles=("admin",), configured_policy=True):
        if not configured_policy:
            monkeypatch.delenv("QE_APPLICATION_ACCESS")
        api = TestClient(create_telemetry_app(configured, repo, quality, auth_runtime=runtime))
        if subject is not None:
            session = sessions.create(subject, roles, expires_at=now + timedelta(minutes=5), csrf_token="local-csrf")
            api.cookies.set("qe_session", session.session_id)
        return api

    return {"client": client, "dev": dev, "repo": repo, "quality": quality, "objects": objects, "settings": configured, "runtime": runtime,
            "token": token, "csrf": {"X-CSRF-Token": "local-csrf"}}


@pytest.mark.parametrize("kind", ["trace", "review", "promotion", "validation"])
@pytest.mark.parametrize("subject", ["alice", "bob"])
def test_external_object_is_404_even_for_admin(isolation, kind, subject):
    own, other = ("app-a", "app-b") if subject == "alice" else ("app-b", "app-a")
    def path(app):
        obj = isolation["objects"][f"{app}-1"]
        return {"trace": f"/api/traces/{app}-1", "review": f"/api/reviews/{obj['review_id']}",
                "promotion": f"/api/promotions/{obj['promotion_id']}",
                "validation": f"/api/quality/release-validations/{isolation['objects'][app]['validation_id']}"}[kind]
    api = isolation["client"](subject)
    assert api.get(path(own)).status_code == 200
    assert api.get(path(other)).status_code == 404


@pytest.mark.parametrize("path", ["/api/traces?application=app-b", "/api/quality/trends?application=app-b"])
def test_explicit_application_is_not_a_permission_claim(isolation, path):
    assert isolation["client"]().get(path).status_code == 403
    assert isolation["client"](None).get(path).status_code == 401


@pytest.mark.parametrize("path,key", [("/api/traces?application=app-a&limit=1&offset=1", "traces"),
                                      ("/api/feedback?category=hallucination&limit=1&offset=1", "feedback"),
                                      ("/api/reviews?limit=1&offset=1", "reviews")])
def test_lists_filter_before_pagination(isolation, path, key):
    api = isolation["client"]()
    rows = api.get(path).json()[key]
    assert len(rows) == 1
    assert rows[0]["trace_id"].startswith("app-a-")
    assert api.get(path.replace("offset=1", "offset=2")).json()[key] == []


def test_trends_links_and_counts_only_include_authorized_application(isolation):
    api = isolation["client"]()
    # Simulate a historical cross-app association without rewriting business records.
    isolation["quality"].create_link(isolation["objects"]["app-b-2"]["promotion_id"], "app-a-candidate")
    result = api.get("/api/quality/trends").json()
    assert {point["application"] for point in result["trends"]} == {"app-a"}
    assert sum(point["online_trace_count"] for point in result["trends"]) == 2
    assert sum(point["feedback_count"] for point in result["trends"]) == 2
    assert sum(point["offline_run_count"] for point in result["trends"]) == 2
    assert len(result["links"]) == 1
    assert all(link["trace_id"].startswith("app-a-") for link in result["links"])
    assert api.get("/api/quality/links").json()["links"] == result["links"]


@pytest.mark.parametrize("kind", ["feedback", "review", "promote", "link", "validation"])
def test_external_ids_cannot_be_used_for_writes(isolation, kind):
    obj = isolation["objects"]["app-b-1"]
    path, payload = {
        "feedback": ("/api/traces/app-b-1/feedback", {"category": "correct", "source": "ui"}),
        "review": (f"/api/feedback/{obj['feedback_id']}/review", {"status": "confirmed", "attribution": "model", "priority": "high"}),
        "promote": (f"/api/reviews/{obj['review_id']}/promote", {"scenario": SCENARIO}),
        "link": ("/api/quality/links", {"promotion_id": obj["promotion_id"], "offline_run_id": "app-a-candidate"}),
        "validation": ("/api/quality/release-validations", {"baseline_run_id": "app-b-baseline", "candidate_run_id": "app-a-candidate"}),
    }[kind]
    assert isolation["client"]().post(path, headers=isolation["csrf"], json=payload).status_code == 404


@pytest.mark.parametrize("kind", ["link", "validation"])
def test_grants_to_both_apps_do_not_permit_cross_app_relationships(isolation, kind):
    if kind == "link":
        path, payload = "/api/quality/links", {"promotion_id": isolation["objects"]["app-a-2"]["promotion_id"], "offline_run_id": "app-b-candidate"}
    else:
        path, payload = "/api/quality/release-validations", {"baseline_run_id": "app-a-baseline", "candidate_run_id": "app-b-candidate", "max_low_quality_rate_increase": 1.0}
    assert isolation["client"]("both").post(path, headers=isolation["csrf"], json=payload).status_code == 400


def test_machine_ingest_and_existing_trace_owner_are_restricted(isolation):
    api = isolation["client"](None)
    for app, expected in [("app-a", 201), ("app-b", 403)]:
        payload = safe_payload(f"new-{app}", app)
        payload["timestamp"] = "2026-09-09T00:00:00Z"
        assert api.post("/api/traces", headers=isolation["token"], json=payload).status_code == expected
    payload = safe_payload("app-b-1", "app-a")
    payload["timestamp"] = "2026-09-09T00:00:00Z"
    assert api.post("/api/traces", headers=isolation["token"], json=payload).status_code == 404
    assert isolation["repo"].get_trace("app-b-1").application == "app-b"
    assert api.get("/api/traces/app-a-1", headers=isolation["token"]).status_code == 401


def test_import_cannot_claim_another_application_or_reassign_existing_run(isolation):
    api = isolation["client"]()
    assert api.post("/api/quality/offline-runs", headers=isolation["csrf"],
                    json=_report_payload(run_id="forged", application="app-b")).status_code == 403
    assert api.post("/api/quality/offline-runs", headers=isolation["csrf"],
                    json=_report_payload(run_id="app-b-candidate", application="app-a")).status_code == 404
    assert api.post("/api/quality/offline-runs", headers=isolation["csrf"],
                    json=_report_payload(run_id="valid", application="app-a")).status_code == 201


def test_missing_policy_denies_production_and_development_is_explicit(isolation):
    assert isolation["client"](configured_policy=False).get("/api/traces?application=app-a").status_code == 403
    assert isolation["dev"].get("/api/traces?application=app-b").status_code == 200


@pytest.mark.parametrize("mapping", [{"alice": "app-a"}, {"alice": [""]}, {"alice": [123]}, {"": ["app-a"]}, [], {"alice": {"app-a": True}}])
def test_access_policy_rejects_ambiguous_mapping(mapping):
    from qe_platform.auth.access import ApplicationAccessPolicy
    with pytest.raises(ValueError):
        ApplicationAccessPolicy(mapping)


def test_access_policy_copies_grants_and_admin_has_no_implicit_bypass():
    from qe_platform.auth.access import ApplicationAccessPolicy
    grants = {"alice": ["app-a"], "both": ["app-a", "app-b"]}
    policy = ApplicationAccessPolicy(grants)
    grants["alice"].append("app-b")
    principal = AuthenticatedPrincipal("alice", frozenset({"admin"}))
    assert policy.allowed_applications(principal) == frozenset({"app-a"})
    with pytest.raises(HTTPException) as error:
        policy.require_application(principal, "app-b")
    assert error.value.status_code == 403
    assert policy.allowed_applications(AuthenticatedPrincipal("both", frozenset({"admin"}))) == frozenset({"app-a", "app-b"})


@pytest.mark.parametrize("application", [[], {}, None, 123])
def test_malformed_application_is_a_controlled_bad_request(isolation, application):
    api = isolation["client"]()
    response = api.post("/api/quality/offline-runs", headers=isolation["csrf"],
                        json=_report_payload(run_id="malformed", application=application))
    assert response.status_code == 400


def test_expired_trace_and_run_ids_cannot_be_reassigned_to_another_application(isolation):
    # Historical records remain intact; exercise replay using the same identifiers.
    payload = safe_payload("expired-b", "app-b")
    payload["timestamp"] = "2026-07-01T00:00:00Z"
    assert isolation["dev"].post("/api/traces", headers=isolation["token"], json=payload).status_code == 201
    isolation["quality"].import_run(_report_payload(run_id="expired-run-b", application="app-b",
        started_at="2026-07-01T00:00:00Z", finished_at="2026-07-01T00:00:02Z"),
        source_label="api-report", now=utc("2026-07-02T00:00:00Z"))
    api = isolation["client"](None)
    payload["application"] = "app-a"
    payload["timestamp"] = "2026-09-09T00:00:00Z"
    assert api.post("/api/traces", headers=isolation["token"], json=payload).status_code == 404
    assert api.post("/api/quality/offline-runs", headers=isolation["token"],
                    json=_report_payload(run_id="expired-run-b", application="app-a")).status_code == 404


@pytest.mark.parametrize("role", ["viewer", "reviewer", "releaser", "admin"])
def test_all_roles_share_same_application_boundary_and_admin_can_be_explicitly_granted_both(isolation, role):
    api = isolation["client"]("alice", (role,))
    assert api.get("/api/traces/app-a-1").status_code == 200
    assert api.get("/api/traces/app-b-1").status_code == 404
    both = isolation["client"]("both", (role,))
    assert both.get("/api/traces/app-b-1").status_code == 200
    assert {point["application"] for point in both.get("/api/quality/trends").json()["trends"]} == {"app-a", "app-b"}


@pytest.mark.parametrize("path", ["/api/traces?trace_id=app-b-1", "/api/feedback?trace_id=app-b-1",
                                  "/api/reviews?trace_id=app-b-1", "/api/quality/links?offline_run_id=app-b-candidate"])
def test_filtered_external_object_ids_remain_hidden(isolation, path):
    assert isolation["client"]().get(path).status_code == 404


def test_missing_machine_scope_does_not_inherit_human_grants_and_owner_is_immutable(isolation):
    settings = replace(isolation["settings"], allowed_applications=frozenset())
    api = TestClient(create_telemetry_app(settings, isolation["repo"], isolation["quality"], auth_runtime=isolation["runtime"]))
    payload = safe_payload("new", "app-a")
    payload["timestamp"] = "2026-09-09T00:00:00Z"
    assert api.post("/api/traces", headers=isolation["token"], json=payload).status_code == 403
    both = replace(settings, allowed_applications=frozenset({"app-a", "app-b"}))
    api = TestClient(create_telemetry_app(both, isolation["repo"], isolation["quality"], auth_runtime=isolation["runtime"]))
    payload["trace_id"] = "app-b-1"
    assert api.post("/api/traces", headers=isolation["token"], json=payload).status_code == 400
    assert isolation["repo"].get_trace("app-b-1").application == "app-b"


def test_machine_quality_writes_and_validation_counts_follow_real_owners(isolation):
    api = isolation["client"](None)
    assert api.post("/api/quality/offline-runs", headers=isolation["token"],
                    json=_report_payload(run_id="machine-b", application="app-b")).status_code == 403
    assert api.post("/api/quality/links", headers=isolation["token"], json={
        "promotion_id": isolation["objects"]["app-b-1"]["promotion_id"], "offline_run_id": "app-a-candidate",
    }).status_code == 404
    isolation["quality"].create_link(isolation["objects"]["app-b-2"]["promotion_id"], "app-a-candidate")
    response = api.post("/api/quality/release-validations", headers=isolation["token"], json={
        "baseline_run_id": "app-a-baseline", "candidate_run_id": "app-a-candidate", "max_low_quality_rate_increase": 1.0,
    })
    assert response.status_code == 201
    assert response.json()["linked_count"] == 1
    assert api.post("/api/quality/release-validations", headers=isolation["token"], json={
        "baseline_run_id": "app-b-baseline", "candidate_run_id": "app-b-candidate",
    }).status_code == 404


def test_legacy_cross_app_validation_and_foreign_validation_id_cannot_be_reused(isolation):
    quality = isolation["quality"]
    original = quality.get_validation(isolation["objects"]["app-a"]["validation_id"])
    legacy = quality.save_validation(replace(original, validation_id="legacy-cross-app", candidate_run_id="app-b-candidate"))
    assert isolation["client"]("both").get(f"/api/quality/release-validations/{legacy.validation_id}").status_code == 404
    assert isolation["client"]().post("/api/quality/release-validations", headers=isolation["csrf"], json={
        "baseline_run_id": "app-a-baseline", "candidate_run_id": "app-a-candidate",
        "validation_id": isolation["objects"]["app-b"]["validation_id"],
    }).status_code == 404


def test_request_cannot_self_grant_or_override_injected_policy(isolation, monkeypatch):
    from qe_platform.auth.access import ApplicationAccessPolicy
    monkeypatch.setenv("QE_APPLICATION_ACCESS", '{"alice":["app-a","app-b"]}')
    api = isolation["client"]()
    isolated = TestClient(create_telemetry_app(isolation["settings"], isolation["repo"], isolation["quality"],
        auth_runtime=isolation["runtime"], access_policy=ApplicationAccessPolicy({"alice": ["app-a"]})))
    isolated.cookies.update(api.cookies)
    result = isolated.get('/api/reviews?allowed_applications=app-b&subject=both').json()
    assert len(result["reviews"]) == 2
    assert all(row["trace_id"].startswith("app-a-") for row in result["reviews"])
    assert isolated.get("/api/traces/app-b-1").status_code == 404
    assert isolated.post("/api/traces/app-a-1/feedback", headers=isolation["csrf"], json={
        "category": "correct", "source": "ui", "application": "app-b",
    }).status_code == 400


@pytest.mark.parametrize("text", ['"app-a"', '{"alice":"app-a"}', '{"alice":["app-a"],"alice":["app-b"]}',
                                  '{"alice":["*"]}', '{"alice":[" app-a"]}', '{"alice":[null]}', 'bad JSON'])
def test_server_policy_json_is_strict(text):
    from qe_platform.auth.access import ApplicationAccessPolicy
    with pytest.raises(ValueError):
        ApplicationAccessPolicy.from_environment({"QE_APPLICATION_ACCESS": text})


@pytest.mark.parametrize("text", ['"app-a"', '{"app-a":true}', '[null]', '[1]', '[""]', '["*"]', 'null'])
def test_machine_application_json_is_strict(text):
    with pytest.raises(ValueError):
        TelemetrySettings.from_environment({"QE_TELEMETRY_DATABASE": "unused.db", "QE_TELEMETRY_HASH_KEY": HASH_KEY,
            "QE_TELEMETRY_INGEST_TOKEN": INGEST_TOKEN, "QE_TELEMETRY_ALLOWED_APPLICATIONS": text})


def test_empty_query_scope_never_falls_back_to_unrestricted_storage(isolation):
    from qe_platform.telemetry import TelemetryQuery
    from qe_platform.feedback import FeedbackQuery, FeedbackKind
    empty = frozenset()
    assert isolation["repo"].list_traces(TelemetryQuery(application="app-a"), allowed_applications=empty) == []
    assert isolation["repo"].list_feedback(FeedbackQuery(category=FeedbackKind.HALLUCINATION), allowed_applications=empty) == []
    assert isolation["repo"].list_reviews(allowed_applications=empty) == []
    assert isolation["quality"].list_runs(allowed_applications=empty) == []
    assert isolation["quality"].list_links(allowed_applications=empty) == []
    assert isolation["quality"].online_rows(allowed_applications=empty) == []


@pytest.mark.parametrize("cross_link", [False, True])
def test_legacy_validation_without_creation_scope_is_hidden_even_if_links_now_look_safe(isolation, cross_link):
    quality = isolation["quality"]
    if cross_link:
        quality.create_link(isolation["objects"]["app-b-2"]["promotion_id"], "app-a-candidate")
    legacy = validate_release(quality, "app-a-baseline", "app-a-candidate", ReleaseGatePolicy(max_low_quality_rate_increase=1.0))
    assert "scope_application" not in legacy.as_dict()
    assert isolation["client"]().get(f"/api/quality/release-validations/{legacy.validation_id}").status_code == 404
    assert isolation["dev"].get(f"/api/quality/release-validations/{legacy.validation_id}").status_code == 200


def test_server_scope_proof_is_persisted_verified_and_cannot_be_supplied_by_request(isolation):
    api = isolation["client"]()
    payload = {"baseline_run_id": "app-a-baseline", "candidate_run_id": "app-a-candidate", "max_low_quality_rate_increase": 1.0}
    assert api.post("/api/quality/release-validations", headers=isolation["csrf"], json={
        **payload, "scope_application": "app-a", "scope_policy_version": 1,
    }).status_code == 400
    created = api.post("/api/quality/release-validations", headers=isolation["csrf"], json=payload)
    assert created.status_code == 201
    proof = created.json()
    assert proof["scope_application"] == "app-a" and proof["scope_policy_version"] == 1
    assert api.get(f"/api/quality/release-validations/{proof['validation_id']}").status_code == 200
    stored = isolation["quality"].get_validation(proof["validation_id"])
    for version, application in [(999, "app-a"), (1, "app-b")]:
        unknown = isolation["quality"].save_validation(replace(stored, validation_id=f"unknown-{version}",
            scope_policy_version=version, scope_application=application))
        assert api.get(f"/api/quality/release-validations/{unknown.validation_id}").status_code == 404


@pytest.mark.parametrize("operation", ["get", "post"])
@pytest.mark.parametrize("damage", ["string", "boolean", "object", "array", "unknown-field", "missing-checks", "invalid-json"])
def test_persisted_malformed_validation_is_hidden(isolation, operation, damage):
    original = isolation["objects"]["app-a"]
    payload = {**original, "validation_id": "malformed-proof"}
    versions = {"string": "1", "boolean": True, "object": {}, "array": []}
    if damage in versions:
        payload["scope_policy_version"] = versions[damage]
    elif damage == "unknown-field":
        payload["unknown_schema_field"] = 1
    elif damage == "missing-checks":
        del payload["checks"]
    serialized = "{" if damage == "invalid-json" else json.dumps(payload)
    # Insert a distinct persisted artifact: model construction correctly rejects these values.
    with sqlite3.connect(isolation["settings"].database) as connection:
        connection.execute(
            "INSERT INTO quality_release_validations (validation_id, baseline_run_id, candidate_run_id, created_at, payload) VALUES (?, ?, ?, ?, ?)",
            ("malformed-proof", original["baseline_run_id"], original["candidate_run_id"], original["created_at"], serialized),
        )
    if damage in versions:
        assert isolation["dev"].get("/api/quality/release-validations/malformed-proof").status_code == 400
    authenticated = isolation["client"]()
    api = TestClient(authenticated.app, raise_server_exceptions=False)
    api.cookies.update(authenticated.cookies)
    if operation == "get":
        response = api.get("/api/quality/release-validations/malformed-proof")
    else:
        response = api.post("/api/quality/release-validations", headers=isolation["csrf"], json={
            "baseline_run_id": "app-a-baseline", "candidate_run_id": "app-a-candidate",
            "validation_id": "malformed-proof", "max_low_quality_rate_increase": 1.0,
        })
    assert response.status_code == 404


@pytest.mark.parametrize("version", ["1", True, {}, []])
def test_request_malformed_scope_proof_remains_bad_request(isolation, version):
    response = isolation["client"]().post("/api/quality/release-validations", headers=isolation["csrf"], json={
        "baseline_run_id": "app-a-baseline", "candidate_run_id": "app-a-candidate",
        "scope_application": "app-a", "scope_policy_version": version,
    })
    assert response.status_code == 400


@pytest.mark.parametrize("operation", ["get", "post", "import"])
@pytest.mark.parametrize("damage", ["schema", "null-ids", "numeric-ids"])
def test_unknown_persisted_run_proof_is_hidden_from_production_validation(isolation, operation, damage):
    quality = isolation["quality"]
    row = quality._connection.execute("SELECT payload FROM quality_offline_runs WHERE run_id='app-a-candidate'").fetchone()
    payload = json.loads(row[0])
    if damage == "schema":
        payload["evidence"]["schema_version"] = "qe-evidence-v999"
    else:
        payload["scenario_ids"] = None if damage == "null-ids" else 123
    quality._connection.execute("UPDATE quality_offline_runs SET payload=? WHERE run_id='app-a-candidate'", (json.dumps(payload),))
    authenticated = isolation["client"]()
    api = TestClient(authenticated.app, raise_server_exceptions=False)
    api.cookies.update(authenticated.cookies)
    if operation == "get":
        response = api.get(f"/api/quality/release-validations/{isolation['objects']['app-a']['validation_id']}")
    elif operation == "post":
        response = api.post("/api/quality/release-validations", headers=isolation["csrf"], json={
            "baseline_run_id": "app-a-baseline", "candidate_run_id": "app-a-candidate", "max_low_quality_rate_increase": 1.0,
        })
    else:
        response = api.post("/api/quality/offline-runs", headers=isolation["csrf"], json=verified_payload(run_id="app-a-candidate", application="app-a"))
    assert response.status_code == 404


@pytest.mark.parametrize("operation", ["get", "post", "import"])
def test_run_loading_programming_error_is_not_hidden_as_missing(isolation, monkeypatch, operation):
    def fail(_identifier):
        raise RuntimeError("unexpected programming error")
    monkeypatch.setattr(isolation["quality"], "get_run", fail)
    authenticated = isolation["client"]()
    api = TestClient(authenticated.app, raise_server_exceptions=False)
    api.cookies.update(authenticated.cookies)
    if operation == "get":
        response = api.get(f"/api/quality/release-validations/{isolation['objects']['app-a']['validation_id']}")
    elif operation == "post":
        response = api.post("/api/quality/release-validations", headers=isolation["csrf"], json={
            "baseline_run_id": "app-a-baseline", "candidate_run_id": "app-a-candidate"})
    else:
        response = api.post("/api/quality/offline-runs", headers=isolation["csrf"], json=verified_payload(run_id="app-a-candidate", application="app-a"))
    assert response.status_code == 500


@pytest.mark.parametrize("operation", ["get", "post"])
def test_validation_programming_error_is_not_hidden_as_missing(isolation, monkeypatch, operation):
    def fail(_identifier):
        raise RuntimeError("unexpected programming error")

    monkeypatch.setattr(isolation["quality"], "get_validation", fail)
    authenticated = isolation["client"]()
    api = TestClient(authenticated.app, raise_server_exceptions=False)
    api.cookies.update(authenticated.cookies)
    if operation == "get":
        response = api.get("/api/quality/release-validations/existing")
    else:
        response = api.post("/api/quality/release-validations", headers=isolation["csrf"], json={
            "baseline_run_id": "app-a-baseline", "candidate_run_id": "app-a-candidate", "validation_id": "existing",
        })
    assert response.status_code == 500