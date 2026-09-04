from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional


_SENSITIVE_HEADERS = {"authorization", "proxy-authorization", "x-api-key", "api-key"}


@dataclass(frozen=True)
class LoadTestConfig:
    target_url: str
    protocol: str = "http"
    requests: Optional[int] = 1
    duration_seconds: Optional[float] = None
    concurrency: int = 1
    warmup_requests: int = 0
    timeout_seconds: float = 30.0
    user_id: str = "U1001"
    message: str = "VPN 无法连接，请帮我处理"
    headers: Mapping[str, str] = field(default_factory=dict)
    json_report: str = "reports/loadtest.json"
    html_report: str = "reports/loadtest.html"

    def __post_init__(self) -> None:
        if not self.target_url.startswith(("http://", "https://")):
            raise ValueError("target_url must use http or https")
        if self.protocol not in {"http", "sse"}:
            raise ValueError("protocol must be 'http' or 'sse'")
        if self.requests is None and self.duration_seconds is None:
            raise ValueError("requests or duration_seconds must be configured")
        if self.requests is not None and self.requests < 1:
            raise ValueError("requests must be at least 1")
        if self.duration_seconds is not None and self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        if self.requests is not None and self.duration_seconds is not None:
            raise ValueError("configure requests or duration_seconds, not both")
        if self.concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        if self.warmup_requests < 0:
            raise ValueError("warmup_requests must not be negative")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not self.user_id or not self.message:
            raise ValueError("user_id and message must not be empty")

    @property
    def endpoint(self) -> str:
        suffix = "/api/chat/stream" if self.protocol == "sse" else "/api/chat"
        return f"{self.target_url.rstrip('/')}" + suffix

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "target_url": self.target_url,
            "protocol": self.protocol,
            "requests": self.requests,
            "duration_seconds": self.duration_seconds,
            "concurrency": self.concurrency,
            "warmup_requests": self.warmup_requests,
            "timeout_seconds": self.timeout_seconds,
            "user_id": self.user_id,
            "message": "[REDACTED]",
            "headers": {key: "[REDACTED]" if key.lower() in _SENSITIVE_HEADERS else value for key, value in self.headers.items()},
            "json_report": self.json_report,
            "html_report": self.html_report,
        }


@dataclass(frozen=True)
class SampleResult:
    success: bool
    duration_ms: float
    ttft_ms: Optional[float]
    status_code: Optional[int] = None
    error_type: str = ""
    error_message: str = ""
    stream_interrupted: bool = False
    trace_id: str = ""
    conversation_id: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_total: Optional[float] = None
    cost_currency: str = ""
    price_version: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "success": self.success, "duration_ms": self.duration_ms, "ttft_ms": self.ttft_ms,
            "status_code": self.status_code, "error_type": self.error_type,
            "error_message": self.error_message, "stream_interrupted": self.stream_interrupted,
            "trace_id": self.trace_id, "conversation_id": self.conversation_id,
            "usage": {"prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens,
                      "total_tokens": self.prompt_tokens + self.completion_tokens},
            "cost": None if self.cost_total is None else {"total": self.cost_total, "currency": self.cost_currency, "price_version": self.price_version},
        }


@dataclass(frozen=True)
class LoadTestSummary:
    requested: Optional[int]
    completed: int
    succeeded: int
    failed: int
    wall_time_ms: float
    throughput_rps: float
    error_rate: float
    rate_429: float
    stream_interruption_rate: float
    latency_ms: Mapping[str, Optional[float]]
    ttft_ms: Mapping[str, Optional[float]]
    status_codes: Mapping[str, int]
    errors: Mapping[str, int]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_total: Optional[float]
    cost_currency: str = ""
    price_version: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}


@dataclass(frozen=True)
class LoadTestRun:
    config: LoadTestConfig
    started_at: str
    finished_at: str
    samples: List[SampleResult]
    summary: LoadTestSummary

    def as_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.as_public_dict(),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "summary": self.summary.as_dict(),
            "samples": [sample.as_dict() for sample in self.samples],
        }
