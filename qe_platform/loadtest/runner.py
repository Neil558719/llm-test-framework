from __future__ import annotations

import asyncio
import json
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
        try:
            if self.config.protocol == "sse":
                return await self._sample_sse(client, body, start)
            response = await client.post(self.config.endpoint, json=body)
            duration = (time.perf_counter() - start) * 1000
            if response.status_code < 200 or response.status_code >= 300:
                return SampleResult(False, duration, None, status_code=response.status_code, error_type="http_error", error_message=f"HTTP {response.status_code}")
            payload = response.json()
            if not isinstance(payload, Mapping):
                raise ValueError("response is not a JSON object")
            return SampleResult(True, duration, None, status_code=response.status_code, **_observability(payload))
        except httpx.TimeoutException as exc:
            return SampleResult(
                False, (time.perf_counter() - start) * 1000, None,
                error_type="timeout", error_message=str(exc),
                stream_interrupted=self.config.protocol == "sse",
            )
        except (json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
            return SampleResult(
                False, (time.perf_counter() - start) * 1000, None,
                error_type="invalid_response", error_message=str(exc),
                stream_interrupted=self.config.protocol == "sse",
            )
        except httpx.HTTPError as exc:
            return SampleResult(
                False, (time.perf_counter() - start) * 1000, None,
                error_type="transport_error", error_message=str(exc),
                stream_interrupted=self.config.protocol == "sse",
            )

    async def _sample_sse(self, client: Any, body: dict[str, str], start: float) -> SampleResult:
        ttft_ms = None
        status_code = None
        saw_event = False
        async with client.stream("POST", self.config.endpoint, json=body) as response:
            status_code = response.status_code
            if status_code < 200 or status_code >= 300:
                return SampleResult(False, (time.perf_counter() - start) * 1000, None, status_code=status_code, error_type="http_error", error_message=f"HTTP {status_code}")
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                saw_event = True
                event = json.loads(line[5:].strip())
                if not isinstance(event, Mapping):
                    raise ValueError("SSE data is not an object")
                event_type = event.get("type")
                if event_type in {"chunk", "complete"} and ttft_ms is None:
                    ttft_ms = (time.perf_counter() - start) * 1000
                if event_type == "complete":
                    payload = event.get("response")
                    if not isinstance(payload, Mapping):
                        raise ValueError("SSE completion has no response object")
                    return SampleResult(True, (time.perf_counter() - start) * 1000, ttft_ms, status_code=status_code, **_observability(payload))
        return SampleResult(False, (time.perf_counter() - start) * 1000, ttft_ms, status_code=status_code, error_type="stream_interrupted", error_message="SSE stream ended before complete event", stream_interrupted=True)
