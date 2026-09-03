from fastapi.testclient import TestClient

from reference_agent.app import create_app


def test_model_profiles_expose_only_mock_and_deepseek_without_secret(monkeypatch):
    monkeypatch.delenv("REFERENCE_AGENT_MODEL_API_KEY", raising=False)
    body = TestClient(create_app(":memory:")).get("/api/model-profiles").json()
    assert [p["name"] for p in body["profiles"]] == ["mock", "deepseek-official"]
    assert "api_key" not in body["current"]


def test_real_profile_requires_server_side_key(monkeypatch):
    monkeypatch.delenv("REFERENCE_AGENT_MODEL_API_KEY", raising=False)
    response = TestClient(create_app(":memory:")).put("/api/model-profile", json={"profile": "deepseek-official", "model": "deepseek-chat"})
    assert response.status_code == 409
    assert "key" in response.json()["detail"]


def test_invalid_profile_is_rejected(monkeypatch):
    response = TestClient(create_app(":memory:")).put("/api/model-profile", json={"profile": "anthropic"})
    assert response.status_code == 400
