from __future__ import annotations

import json

from tests.test_quality_loop_models import _report_payload
from tests.test_telemetry_api import INGEST_TOKEN, client_for, safe_payload


SCENARIO = {
    "id": "vpn-recovery-regression",
    "name": "VPN recovery",
    "conversation": [{"user": "VPN is unavailable"}],
}


def _create_promotion(client):
    assert client.post("/api/traces", headers={"X-QE-Telemetry-Token": INGEST_TOKEN}, json=safe_payload()).status_code == 201
    feedback_id = client.post(
        "/api/traces/trace-1/feedback",
        json={"category": "hallucination", "reporter_id": "reporter", "source": "ui"},
    ).json()["feedback_id"]
    review = client.post(
        f"/api/feedback/{feedback_id}/review",
        json={"reviewer_id": "reviewer", "status": "confirmed", "attribution": "model", "priority": "high"},
    ).json()
    promotion = client.post(f"/api/reviews/{review['review_id']}/promote", json={"scenario": SCENARIO})
    assert promotion.status_code == 201
    return promotion.json()


def test_quality_api_completes_online_offline_link_and_validation(tmp_path):
    client = client_for(tmp_path)
    promotion = _create_promotion(client)
    baseline = _report_payload(run_id="run-baseline", release_id="alpha-22", version="old", started_at="2026-09-08T00:00:00Z", finished_at="2026-09-08T00:00:02Z")
    candidate = _report_payload(run_id="run-candidate", release_id="alpha-23", version="new")
    headers = {"X-QE-Telemetry-Token": INGEST_TOKEN}
    assert client.post("/api/quality/offline-runs", headers=headers, json={**baseline, "source_label": "api-fixture"}).status_code == 201
    assert client.post("/api/quality/offline-runs", headers=headers, json={**candidate, "source_label": "api-fixture"}).status_code == 201
    linked = client.post(
        "/api/quality/links",
        headers=headers,
        json={"promotion_id": promotion["promotion_id"], "offline_run_id": "run-candidate", "scenario_id": SCENARIO["id"]},
    )
    assert linked.status_code == 201
    assert linked.json()["trace_id"] == "trace-1"
    assert client.post(
        "/api/quality/links",
        headers=headers,
        json={"promotion_id": promotion["promotion_id"], "offline_run_id": "run-candidate", "scenario_id": SCENARIO["id"]},
    ).status_code == 200

    trends = client.get("/api/quality/trends", params={"application": "service-desk"})
    assert trends.status_code == 200
    assert trends.json()["trends"]
    assert trends.json()["links"][0]["promotion_id"] == promotion["promotion_id"]
    assert client.get("/api/quality/links", params={"offline_run_id": "run-candidate"}).status_code == 200

    validated = client.post(
        "/api/quality/release-validations",
        headers=headers,
        json={
            "baseline_run_id": "run-baseline",
            "candidate_run_id": "run-candidate",
            "max_low_quality_rate_increase": 1.0,
        },
    )
    assert validated.status_code == 201
    assert validated.json()["passed"] is True
    validation_id = validated.json()["validation_id"]
    assert client.get(f"/api/quality/release-validations/{validation_id}").json()["passed"] is True

    strict = client.post(
        "/api/quality/release-validations",
        headers=headers,
        json={"baseline_run_id": "run-baseline", "candidate_run_id": "run-candidate"},
    )
    assert strict.status_code == 422
    assert strict.json()["passed"] is False


def test_quality_api_requires_token_for_writes_and_rejects_sensitive_runs(tmp_path):
    client = client_for(tmp_path)
    report = _report_payload()
    unauthorized = client.post("/api/quality/offline-runs", json={**report, "source_label": "fixture"})
    assert unauthorized.status_code == 401
    report["scenarios"] = [{"scenario_id": "s", "request": "raw secret"}, {"scenario_id": "t", "passed": True, "complete": True}]
    response = client.post("/api/quality/offline-runs", headers={"X-QE-Telemetry-Token": INGEST_TOKEN}, json={**report, "source_label": "fixture"})
    assert response.status_code == 400
    assert "raw secret" not in response.text


def test_quality_api_maps_missing_and_invalid_records(tmp_path):
    client = client_for(tmp_path)
    headers = {"X-QE-Telemetry-Token": INGEST_TOKEN}
    assert client.post("/api/quality/links", headers=headers, json={"promotion_id": "missing", "offline_run_id": "missing"}).status_code == 404
    assert client.get("/api/quality/release-validations/missing").status_code == 404
    assert client.get("/api/quality/trends", params={"from": "bad"}).status_code == 400
