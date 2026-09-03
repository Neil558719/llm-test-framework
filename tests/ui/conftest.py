from __future__ import annotations

import socket
import threading
import time

import pytest
import uvicorn

from reference_agent.deployment import create_deployment_app
from qe_platform.browser import ReferenceAgentPage


try:
    from playwright import sync_api as playwright
except ImportError:  # pragma: no cover - exercised only without the optional extra
    playwright = None


@pytest.fixture(scope="session")
def app_server():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    config = uvicorn.Config(create_deployment_app(), host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    else:
        raise RuntimeError("UI test server did not start")
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture()
def browser_page(app_server):
    if playwright is None:
        pytest.skip("install the ui extra and browser binaries")
    with playwright.sync_playwright() as api:
        browser = api.chromium.launch()
        page = browser.new_page()
        yield ReferenceAgentPage(page, app_server)
        browser.close()
