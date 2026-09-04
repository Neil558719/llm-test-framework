from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_SENSITIVE_HEADERS = {"authorization", "proxy-authorization", "x-api-key", "api-key"}
_SENSITIVE_QUERY_PARTS = ("api_key", "apikey", "token", "key", "secret", "password", "signature", "credential")


def _sensitive_query_key(value: str) -> bool:
    normalized = value.lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_QUERY_PARTS)


def _public_url(value: str) -> str:
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    query = urlencode([
        (key, "[REDACTED]" if _sensitive_query_key(key) else item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
    ])
    return urlunsplit((parsed.scheme, host, parsed.path, query, ""))


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
        text_fields = {
            "target_url": self.target_url, "protocol": self.protocol,
            "user_id": self.user_id, "message": self.message,
            "json_report": self.json_report, "html_report": self.html_report,
        }
        for name, value in text_fields.items():
            if not isinstance(value, str):
                raise ValueError(f"{name} must be a string")
        numeric_types = {
            "requests": (self.requests, int, True),
            "duration_seconds": (self.duration_seconds, (int, float), True),
            "concurrency": (self.concurrency, int, False),
            "warmup_requests": (self.warmup_requests, int, False),
            "timeout_seconds": (self.timeout_seconds, (int, float), False),
        }
        for name, (value, expected, optional) in numeric_types.items():
            if value is None and optional:
                continue
            if isinstance(value, bool) or not isinstance(value, expected):
                raise ValueError(f"{name} has an invalid numeric type")
        if not self.target_url.startswith(("http://", "https://")):
            raise ValueError("target_url must use http or https")
        try:
            parsed_url = urlsplit(self.target_url)
            port = parsed_url.port
        except ValueError as exc:
            raise ValueError(f"target_url is invalid: {exc}") from exc
        if not parsed_url.hostname or port is not None and not 1 <= port <= 65535:
            raise ValueError("target_url must include a valid host and port")
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
            "target_url": _public_url(self.target_url),
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
