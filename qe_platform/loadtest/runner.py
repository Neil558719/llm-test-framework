from __future__ import annotations

import asyncio
import json
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

import httpx

from .metrics import summarize
from .models import LoadTestConfig, LoadTestRun, SampleResult


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _observability(payload: Mapping[str, Any]) -> dict[str, Any]:
    usage = payload.get("usage") if isinstance(payload.get("usage"), Mapping) else {}
    cost = payload.get("cost") if isinstance(payload.get("cost"), Mapping) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}
    sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
    tool_calls = payload.get("tool_calls") if isinstance(payload.get("tool_calls"), list) else []
    observations = {
        key: str(metadata[key])
        for key in (
            "fallback_reason",
            "knowledge_status",
            "ticket_status",
            "approval_status",
        )
        if key in metadata
    }
    observations.update(
        {
            "source_count": len(sources),
            "failed_tool_count": sum(
                isinstance(call, Mapping) and call.get("status") == "failed"
                for call in tool_calls
            ),
        }
    )
    return {
        "trace_id": str(payload.get("trace_id", "")),
        "conversation_id": str(payload.get("conversation_id", "")),
        "prompt_tokens": int(usage.get("prompt_tokens", 0)),
        "completion_tokens": int(usage.get("completion_tokens", 0)),
        "cost_total": float(cost["total"]) if cost.get("total") is not None else None,
        "cost_currency": str(cost.get("currency", "")),
        "price_version": str(cost.get("price_version", "")),
        "observations": observations,
    }


def _validate_response(payload: Any) -> Mapping[str, Any]:
    """Reference chat contract, shared by HTTP and SSE completion."""
    if not isinstance(payload, Mapping) or not {"answer", "sources", "tool_calls", "conversation_id", "trace_id"} <= set(payload):
        raise ValueError("response is missing required fields")
    if not all(isinstance(payload[key], str) for key in ("answer", "conversation_id", "trace_id")):
        raise ValueError("response text or identifiers have an invalid type")
    if not isinstance(payload["sources"], list) or any(not isinstance(value, str) for value in payload["sources"]):
        raise ValueError("response sources must be textual")
    if not isinstance(payload["tool_calls"], list) or any(
        not isinstance(call, Mapping) or not isinstance(call.get("name"), str)
        or not isinstance(call.get("arguments", {}), Mapping) for call in payload["tool_calls"]
    ):
        raise ValueError("response tool calls have an invalid shape")
    for name in ("usage", "cost", "metadata"):
        if payload.get(name) is not None and not isinstance(payload[name], Mapping):
            raise ValueError("response observability must be an object")
    for key in ("prompt_tokens", "completion_tokens"):
        value = (payload.get("usage") or {}).get(key, 0)
        if type(value) is not int or value < 0:
            raise ValueError("token counts must be nonnegative integers")
    value = (payload.get("cost") or {}).get("total")
    if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
        raise ValueError("cost must be a finite nonnegative number")
    return payload


def _result(start, state, success, *, error_type="", error_message="", payload=None):
    content = state["content_first_event_ms"]
    # Keep the legacy network-first-content alias for unknown external streams.
    # A Reference simulated stream cannot supply model-side TTFT evidence.
    legacy_ttft = content if state["stream_mode"] != "simulated" else None
    return SampleResult(
        success, (time.perf_counter() - start) * 1000, legacy_ttft,
        status_code=state["status_code"], error_type=error_type, error_message=error_message,
        stream_interrupted=state["stream_established"] and not success,
        stream_established=state["stream_established"], content_first_event_ms=content,
        stream_mode=state["stream_mode"], ttft_source="client_first_content" if legacy_ttft is not None else "unavailable",
        **(_observability(payload) if payload is not None else {}),
    )


class LoadTestRunner:
    def __init__(self, config: LoadTestConfig, *, client_factory: Callable[..., Any] = httpx.AsyncClient):
        self.config = config
        self.client_factory = client_factory

    async def run(self) -> LoadTestRun:
        started_at = _utc_now()
        async with self.client_factory(headers=dict(self.config.headers), timeout=self.config.timeout_seconds) as client:
            for _ in range(self.config.warmup_requests):
                await self._sample(client)
            semaphore = asyncio.Semaphore(self.config.concurrency)

            async def bounded() -> SampleResult:
                async with semaphore:
                    return await self._sample(client)

            wall_start = time.perf_counter()
            if self.config.requests is not None:
                next_index = 0

                async def fixed_worker() -> list[SampleResult]:
                    nonlocal next_index
                    worker_samples = []
                    while next_index < self.config.requests:
                        next_index += 1
                        worker_samples.append(await self._sample(client))
                    return worker_samples

                batches = await asyncio.gather(*(fixed_worker() for _ in range(min(self.config.concurrency, self.config.requests))))
                samples = [sample for batch in batches for sample in batch]
            else:
                deadline = wall_start + float(self.config.duration_seconds)

                async def duration_worker() -> list[SampleResult]:
                    worker_samples = []
                    while time.perf_counter() < deadline:
                        worker_samples.append(await self._sample(client))
                    return worker_samples

                batches = await asyncio.gather(*(duration_worker() for _ in range(self.config.concurrency)))
                samples = [sample for batch in batches for sample in batch]
            wall_time_ms = (time.perf_counter() - wall_start) * 1000
        return LoadTestRun(self.config, started_at, _utc_now(), samples, summarize(samples, self.config, wall_time_ms=wall_time_ms))

    async def _sample(self, client: Any) -> SampleResult:
        session_id = str(uuid.uuid4())
        body = {"message": self.config.message, "user_id": self.config.user_id, "session_id": session_id}
        start = time.perf_counter()
        state = dict(status_code=None, stream_established=False, content_first_event_ms=None, stream_mode="unknown")
        try:
            if self.config.protocol == "sse":
                return await self._sample_sse(client, body, start, state)
            response = await client.post(self.config.endpoint, json=body)
            state["status_code"] = response.status_code
            if response.status_code < 200 or response.status_code >= 300:
                return _result(start, state, False, error_type="http_error", error_message=f"HTTP {response.status_code}")
            return _result(start, state, True, payload=_validate_response(response.json()))
        except httpx.TimeoutException as exc:
            return _result(start, state, False, error_type="timeout", error_message=type(exc).__name__)
        except (json.JSONDecodeError, TypeError, ValueError, KeyError, OverflowError) as exc:
            return _result(start, state, False, error_type="invalid_response", error_message=type(exc).__name__)
        except httpx.HTTPError as exc:
            return _result(start, state, False, error_type="transport_error", error_message=type(exc).__name__)

    async def _sample_sse(self, client: Any, body: dict[str, str], start: float, state: dict[str, Any]) -> SampleResult:
        async with client.stream("POST", self.config.endpoint, json=body) as response:
            state["status_code"] = response.status_code
            if response.status_code < 200 or response.status_code >= 300:
                return _result(start, state, False, error_type="http_error", error_message=f"HTTP {response.status_code}")
            if response.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "text/event-stream":
                raise ValueError("response is not an SSE stream")
            state["stream_established"] = True
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:].strip())
                if not isinstance(event, Mapping):
                    raise ValueError("SSE data is not an object")
                event_type = event.get("type")
                if event.get("stream_mode") == "simulated":
                    state["stream_mode"] = "simulated"
                if event_type == "chunk":
                    text = event.get("text")
                    if not isinstance(text, str):
                        raise ValueError("SSE chunk must contain text")
                    if text and state["content_first_event_ms"] is None:
                        state["content_first_event_ms"] = (time.perf_counter() - start) * 1000
                if event_type == "complete":
                    payload = _validate_response(event.get("response"))
                    if (payload.get("metadata") or {}).get("stream_mode") == "simulated":
                        state["stream_mode"] = "simulated"
                    return _result(start, state, True, payload=payload)
        return _result(start, state, False, error_type="stream_interrupted", error_message="SSE stream ended before complete event")
