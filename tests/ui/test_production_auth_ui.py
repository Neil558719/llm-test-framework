from __future__ import annotations

import socket
import threading
import time

import pytest
import uvicorn

from qe_platform.auth.dependencies import AuthRuntime
from qe_platform.auth.session import SessionStore
from reference_agent.app import create_app
from reference_agent.services import UserService

pytestmark = pytest.mark.ui


def test_production_browser_login_session_csrf_writes_and_logout(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    sync_playwright, expect = playwright.sync_playwright, playwright.expect
    class Metadata:
        authorization_endpoint = "https://idp.example.test/authorize"
    sessions = SessionStore(tmp_path / "auth.db")
    runtime = AuthRuntime(session_store=sessions, verifier=object(), environment="production",
                          cookie_secure=False, metadata_client=Metadata(), client_id="browser",
                          redirect_uri="http://127.0.0.1/auth/callback")
    app = create_app(str(tmp_path / "agent.db"), auth_runtime=runtime,
                     user_service=UserService({"U1001": {"user_id": "U1001", "name": "User"}}))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(.02)
    assert server.started
    url = f"http://127.0.0.1:{port}"
    try:
        with sync_playwright() as api:
            browser = api.chromium.launch()
            context = browser.new_context()
            page = context.new_page()
            def fake_idp_navigation(route):
                response = route.fetch(max_redirects=0)
                assert response.status == 302
                assert response.headers["location"].startswith("https://idp.example.test/authorize?")
                route.fulfill(status=200, content_type="text/html", body="IdP login")
            page.route("**/auth/login?**", fake_idp_navigation)
            page.goto(url)
            expect(page.locator("#oidc-login")).to_be_visible()
            expect(page.locator("#login-form")).to_be_hidden()
            page.locator("#oidc-login").click()
            page.wait_for_url("**/auth/login?**")
            # The real callback's signature/browser binding has separate HTTP tests.
            # Bootstrap its resulting opaque session to exercise the actual UI/API boundary.
            session = sessions.create("U1001", {"admin"}, csrf_token="csrf-ui-fixture")
            context.add_cookies([
                {"name": "qe_session", "value": session.session_id, "url": url, "httpOnly": True},
                {"name": "qe_session_csrf", "value": "csrf-ui-fixture", "url": url},
            ])
            page.goto(url)
            expect(page.locator("#chat-panel")).to_be_visible()
            page.locator("#message-input").fill("VPN")
            with page.expect_response("**/api/chat/stream") as stream:
                page.locator("#send-button").click()
            assert stream.value.status == 200
            assert stream.value.request.headers["x-csrf-token"] == "csrf-ui-fixture"
            with page.expect_response("**/api/model-profile") as update:
                page.locator("#save-model").click()
            assert update.value.status == 200
            page.locator("#logout").click()
            expect(page.locator("#oidc-login")).to_be_visible()
            assert sessions.get(session.session_id) is None
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        app.state.store.close()
