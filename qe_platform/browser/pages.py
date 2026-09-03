from __future__ import annotations

from typing import Any


class ReferenceAgentPage:
    """Page object for the Reference Agent's user-visible workflows."""

    def __init__(self, page: Any, base_url: str):
        self.page = page
        self.base_url = base_url.rstrip("/")

    def open(self) -> None:
        self.page.goto(self.base_url + "/")

    def login(self, user_id: str = "U1001") -> None:
        self.page.locator("#user-id").select_option(user_id)
        self.page.locator("#login-button").click()
        self.page.locator("#chat-panel").wait_for(state="visible")

    def send(self, message: str) -> None:
        self.page.locator("#message-input").fill(message)
        self.page.locator("#send-button").click()

    def wait_for_completion(self) -> None:
        self.page.locator("#stream-status").filter(has_text="trace").wait_for()

    def transcript(self) -> str:
        return self.page.locator("#conversation").inner_text()

    def trace_status(self) -> str:
        return self.page.locator("#stream-status").inner_text()

    def trace_id(self) -> str:
        return str(self.page.locator("#stream-status").get_attribute("data-trace-id") or "")
