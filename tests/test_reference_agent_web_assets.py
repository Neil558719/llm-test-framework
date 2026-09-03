from fastapi.testclient import TestClient

from reference_agent.deployment import create_deployment_app


def test_root_serves_reference_agent_web_ui_with_required_controls():
    client = TestClient(create_deployment_app( ))

    response = client.get("/")

    assert response.status_code == 200
    assert 'id="login-form"' in response.text
    assert 'id="user-id"' in response.text
    assert 'id="message-input"' in response.text
    assert 'id="send-button"' in response.text
    assert 'id="stream-status"' in response.text


def test_web_script_uses_login_session_and_stream_endpoints():
    client = TestClient(create_deployment_app())

    script = client.get("/app.js")

    assert script.status_code == 200
    assert "/api/login" in script.text
    assert "/api/sessions/" in script.text
    assert "/api/chat/stream" in script.text
    assert "trace_id" in script.text

