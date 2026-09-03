from __future__ import annotations

import pytest

from qe_platform.browser.scenarios import first_message


pytestmark = pytest.mark.ui


def test_user_can_login_and_stream_knowledge_answer(browser_page):
    browser_page.open()
    browser_page.login()
    browser_page.send(first_message("knowledge-hit.yaml"))
    browser_page.wait_for_completion()

    assert "VPN" in browser_page.transcript()
    assert "引用：1 条" in browser_page.transcript()
    assert "trace" in browser_page.trace_status()


def test_user_can_create_ticket_and_see_business_result(browser_page):
    browser_page.open()
    browser_page.login()
    browser_page.send("VPN 无法连接，设备 PC-1001，请创建工单，优先级高")
    browser_page.wait_for_completion()

    assert "工单：created" in browser_page.transcript()


def test_user_sees_handoff_for_restricted_software(browser_page):
    browser_page.open()
    browser_page.login()
    browser_page.send("申请安装生产数据库，理由是远程办公")
    browser_page.wait_for_completion()

    assert "转人工：restricted_software" in browser_page.transcript()


def test_user_sees_stable_error_when_stream_request_fails(browser_page):
    browser_page.open()
    browser_page.login()
    browser_page.page.route("**/api/chat/stream", lambda route: route.fulfill(status=503, body="unavailable"))
    browser_page.send("VPN 帮助")

    browser_page.page.locator("#stream-status").filter(has_text="请求失败").wait_for()
    assert "服务暂时不可用" in browser_page.transcript()
