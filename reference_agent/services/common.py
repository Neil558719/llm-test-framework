"""Mock 服务共享的故障注入和响应辅助。"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class FailureConfig:
    """单次服务调用使用的可控故障配置。"""

    status_code: int | None = None
    message: str = ""
    delay_seconds: float = 0.0


class ServiceError(RuntimeError):
    """Mock 下游服务返回的可断言错误。"""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class MockServiceBase:
    def __init__(self, failure: FailureConfig | None = None) -> None:
        self.failure = failure or FailureConfig()

    def _before_call(self) -> None:
        if self.failure.delay_seconds > 0:
            time.sleep(self.failure.delay_seconds)
        if self.failure.status_code is not None:
            message = self.failure.message or "mock service failure"
            raise ServiceError(self.failure.status_code, message)
