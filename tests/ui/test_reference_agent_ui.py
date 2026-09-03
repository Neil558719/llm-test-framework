from __future__ import annotations

import pytest

from qe_platform.browser.scenarios import first_message, expected_contains


pytestmark = pytest.mark.ui


def test_user_can_login_and_stream_knowledge_answer(browser_page):
    browser_page.open()
    browser_page.login()
    browser_page.send(first_message("knowledge-hit.yaml", "knowledge-hit"))
    browser_page.wait_for_completion()

    assert all(text in browser_page.transcript() for text in expected_contains("knowledge-hit.yaml", "knowledge-hit"))
    assert "引用：1 条" in browser_page.transcript()
    assert browser_page.trace_id()


def test_user_can_create_ticket_and_see_business_result(browser_page):
    browser_page.open()
    browser_page.login()
    browser_page.send(first_message("ticket-create.yaml", "ticket-create"))
    browser_page.wait_for_completion()

    assert "工单：created" in browser_page.transcript()


def test_user_sees_handoff_for_restricted_software(browser_page):
    browser_page.open()
    browser_page.login()
    browser_page.send(first_message("access-handoff.yaml", "access-handoff"))
    browser_page.wait_for_completion()

    assert "转人工：restricted_software" in browser_page.transcript()


def test_user_sees_stable_error_when_stream_request_fails(browser_page):
    browser_page.open()
    browser_page.login()
    browser_page.page.route("**/api/chat/stream", lambda route: route.fulfill(status=503, body="unavailable"))
    browser_page.send("VPN 帮助")

    browser_page.page.locator("#stream-status").filter(has_text="请求失败").wait_for()
    assert "服务暂时不可用" in browser_page.transcript()
