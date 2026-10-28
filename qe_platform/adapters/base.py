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


class AsyncApplicationAdapter(Protocol):
    """Cooperative native async I/O; retry safety must be explicitly declared."""
    retry_safe: bool

    async def send(self, message: str, *, user_id: str, session_id: str) -> ResponseEnvelope:
        ...

    async def aclose(self) -> None:
        ...


class AsyncApplicationAdapterError(ApplicationAdapterError):
    def __init__(self, message: str, status_code: Optional[int] = None, *, retryable: bool = False, effect_unknown: bool = False):
        super().__init__(message, status_code)
        self.retryable = retryable
        self.effect_unknown = effect_unknown
