import json

from tests.test_telemetry_api import INGEST_TOKEN, client_for, safe_payload


def create_feedback(client, category="inaccurate"):
    assert client.post(
        "/api/traces",
        headers={"X-QE-Telemetry-Token": INGEST_TOKEN},
        json=safe_payload(),
    ).status_code == 201
    response = client.post(
        "/api/traces/trace-1/feedback",
        json={"category": category, "reporter_id": "reporter-1", "source": "ui"},
    )
    assert response.status_code == 201
    return response.json()["feedback_id"]


SCENARIO = {
    "id": "promoted-api",
    "name": "Promoted API scenario",
    "tags": ["m16"],
    "conversation": [{"user": "VPN is unavailable"}],
    "expect": {"response": {"contains": ["ticket"]}},
}


def test_review_and_promotion_api_returns_safe_idempotent_yaml(tmp_path):
    client = client_for(tmp_path)
    feedback_id = create_feedback(client)
    review_payload = {
        "reviewer_id": "reviewer-1",
        "status": "confirmed",
        "attribution": "tool",
        "priority": "high",
    }

    created = client.post(f"/api/feedback/{feedback_id}/review", json=review_payload)
    assert created.status_code == 201
    review = created.json()
    assert review["status"] == "confirmed"
    assert "reviewer-1" not in json.dumps(review)

    repeated = client.post(f"/api/feedback/{feedback_id}/review", json=review_payload)
    assert repeated.status_code == 200
    assert repeated.json()["review_id"] == review["review_id"]

    promoted = client.post(f"/api/reviews/{review['review_id']}/promote", json={"scenario": SCENARIO})
    assert promoted.status_code == 201
    payload = promoted.json()
    assert payload["scenario_id"] == "promoted-api"
    assert "reviewer-1" not in json.dumps(payload)

    repeated_promotion = client.post(f"/api/reviews/{review['review_id']}/promote", json={"scenario": SCENARIO})
    assert repeated_promotion.status_code == 200
    assert repeated_promotion.json()["promotion_id"] == payload["promotion_id"]
    assert client.get(f"/api/promotions/{payload['promotion_id']}").json()["scenario_yaml"] == payload["scenario_yaml"]
    assert client.get(f"/api/reviews/{review['review_id']}").json()["promotion_id"] == payload["promotion_id"]

    listed = client.get("/api/reviews", params={"trace_id": "trace-1", "status": "confirmed"})
    assert listed.status_code == 200
    assert [item["review_id"] for item in listed.json()["reviews"]] == [review["review_id"]]
    status_only = client.get("/api/reviews", params={"status": "confirmed"})
    assert status_only.status_code == 200
    assert [item["review_id"] for item in status_only.json()["reviews"]] == [review["review_id"]]


def test_promotion_api_rejects_correct_feedback_and_sensitive_or_invalid_drafts(tmp_path):
    client = client_for(tmp_path)
    feedback_id = create_feedback(client, category="correct")
    review = client.post(
        f"/api/feedback/{feedback_id}/review",
        json={"reviewer_id": "reviewer-1", "status": "confirmed", "attribution": "unknown", "priority": "low"},
    ).json()
    assert client.post(f"/api/reviews/{review['review_id']}/promote", json={"scenario": SCENARIO}).status_code == 400

    feedback_id = create_feedback(client)
    review = client.post(
        f"/api/feedback/{feedback_id}/review",
        json={"reviewer_id": "reviewer-1", "status": "confirmed", "attribution": "model", "priority": "low"},
    ).json()
    sensitive = {"id": "s", "name": "S", "conversation": [{"user": "Bearer token=secret"}]}
    response = client.post(f"/api/reviews/{review['review_id']}/promote", json={"scenario": sensitive})
    assert response.status_code == 400
    assert "secret" not in response.text
    assert client.post(f"/api/reviews/{review['review_id']}/promote", json={"scenario": {"id": "s"}}).status_code == 400


def test_review_api_rejects_extra_fields_and_missing_records(tmp_path):
    client = client_for(tmp_path)
    response = client.post(
        "/api/feedback/missing/review",
        json={"reviewer_id": "r", "status": "confirmed", "attribution": "model", "priority": "low", "note": "free text"},
    )
    assert response.status_code == 400
    invalid = client.post(
        "/api/feedback/missing/review",
        json={"reviewer_id": "r", "status": "invalid", "attribution": "model", "priority": "low"},
    )
    assert invalid.status_code == 400
    assert client.get("/api/reviews/missing").status_code == 404
