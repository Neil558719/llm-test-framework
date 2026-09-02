from __future__ import annotations

from typing import Optional, Protocol

from llmtest import ResponseEnvelope


class ApplicationAdapter(Protocol):
    def send(self, message: str, *, user_id: str, session_id: str) -> ResponseEnvelope:
        ...


class ApplicationAdapterError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code
