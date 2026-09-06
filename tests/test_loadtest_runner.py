import asyncio
import json as jsonlib

from qe_platform.loadtest.models import LoadTestConfig
from qe_platform.loadtest.runner import LoadTestRunner


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _Stream:
    def __init__(self, lines, status_code=200):
        self.lines = lines
        self.status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def aiter_lines(self):
        for line in self.lines:
            await asyncio.sleep(0)
            yield line


class _Client:
    active = 0
    peak = 0
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json):
        type(self).calls.append(json)
        type(self).active += 1
        type(self).peak = max(type(self).peak, type(self).active)
        await asyncio.sleep(0)
        type(self).active -= 1
        return _Response(payload={"answer": "ok", "trace_id": "t1", "conversation_id": json["session_id"], "usage": {"prompt_tokens": 1, "completion_tokens": 2}, "cost": {"total": 0.01, "currency": "USD", "price_version": "p1"}})

    def stream(self, method, url, json):
        return _Stream([
            "data: {\"type\": \"start\"}",
            "data: {\"type\": \"chunk\", \"text\": \"ok\"}",
            "data: {\"type\": \"complete\", \"response\": {\"trace_id\": \"t2\", \"conversation_id\": " + jsonlib.dumps(json["session_id"]) + ", \"usage\": {\"prompt_tokens\": 2, \"completion_tokens\": 3}}}",
        ])


class _InterruptedClient(_Client):
    def stream(self, method, url, json):
        return _Stream(["data: {\"type\": \"start\"}"])


class _TimeoutStream(_Stream):
    async def aiter_lines(self):
        import httpx
        yield "data: {\"type\": \"start\"}"
        raise httpx.ReadTimeout("stream stalled")


class _TimeoutStreamClient(_Client):
    def stream(self, method, url, json):
        return _TimeoutStream([])


class _MalformedStreamClient(_Client):
    def stream(self, method, url, json):
        return _Stream(["data: {not-json}"])


class _RateLimitedClient(_Client):
    async def post(self, url, json):
        return _Response(status_code=429, payload={"detail": "limited"})


class _ObservationClient(_Client):
    async def post(self, url, json):
        return _Response(
            payload={
                "answer": "fallback answer",
                "trace_id": "trace-observed",
                "conversation_id": json["session_id"],
                "sources": ["KB-1"],
                "tool_calls": [
                    {"name": "query_user", "status": "succeeded"},
                    {"name": "create_ticket", "status": "failed", "error": "down"},
                ],
                "metadata": {
                    "fallback_reason": "TimeoutError",
                    "knowledge_status": "answered",
                    "ticket_status": "unavailable",
                    "approval_status": "",
                    "private_context": "must-not-leak",
                },
            }
        )


class _TimeoutClient(_Client):
    async def post(self, url, json):
        import httpx
        raise httpx.ReadTimeout("slow model")


def _factory(**kwargs):
    return _Client(**kwargs)


def test_runner_bounds_concurrency_and_isolates_sessions():
    _Client.active = _Client.peak = 0
    _Client.calls = []
    config = LoadTestConfig(target_url="http://test", requests=5, concurrency=2)
    result = asyncio.run(LoadTestRunner(config, client_factory=_factory).run())
    assert len(result.samples) == 5
    assert _Client.peak <= 2
    assert len({call["session_id"] for call in _Client.calls}) == 5
    assert result.summary.total_tokens == 15


def test_runner_parses_sse_ttft_and_completion():
    config = LoadTestConfig(target_url="http://test", protocol="sse", requests=1, concurrency=1)
    result = asyncio.run(LoadTestRunner(config, client_factory=_factory).run())
    sample = result.samples[0]
    assert sample.success is True
    assert sample.ttft_ms is not None
    assert sample.trace_id == "t2"


def test_runner_classifies_http_429():
    config = LoadTestConfig(target_url="http://test", requests=1)
    result = asyncio.run(LoadTestRunner(config, client_factory=lambda **kwargs: _RateLimitedClient(**kwargs)).run())
    assert result.samples[0].error_type == "http_error"
    assert result.summary.rate_429 == 1.0


def test_runner_counts_sse_without_complete_as_interrupted():
    config = LoadTestConfig(target_url="http://test", protocol="sse", requests=1)
    result = asyncio.run(LoadTestRunner(config, client_factory=lambda **kwargs: _InterruptedClient(**kwargs)).run())
    assert result.samples[0].stream_interrupted is True
    assert result.summary.stream_interruption_rate == 1.0


def test_runner_classifies_timeout():
    config = LoadTestConfig(target_url="http://test", requests=1)
    result = asyncio.run(LoadTestRunner(config, client_factory=lambda **kwargs: _TimeoutClient(**kwargs)).run())
    assert result.samples[0].error_type == "timeout"


def test_runner_extracts_only_allowlisted_fault_observations():
    config = LoadTestConfig(target_url="http://test", requests=1)

    result = asyncio.run(
        LoadTestRunner(
            config,
            client_factory=lambda **kwargs: _ObservationClient(**kwargs),
        ).run()
    )

    assert result.samples[0].observations == {
        "fallback_reason": "TimeoutError",
        "knowledge_status": "answered",
        "ticket_status": "unavailable",
        "approval_status": "",
        "source_count": 1,
        "failed_tool_count": 1,
    }
    assert "private_context" not in str(result.samples[0].as_dict())


def test_runner_counts_sse_timeout_as_stream_interruption():
    config = LoadTestConfig(target_url="http://test", protocol="sse", requests=1)
    result = asyncio.run(LoadTestRunner(config, client_factory=lambda **kwargs: _TimeoutStreamClient(**kwargs)).run())
    sample = result.samples[0]
    assert sample.error_type == "timeout"
    assert sample.stream_interrupted is True
    assert result.summary.stream_interruption_rate == 1.0


def test_runner_counts_malformed_sse_as_stream_interruption():
    config = LoadTestConfig(target_url="http://test", protocol="sse", requests=1)
    result = asyncio.run(LoadTestRunner(config, client_factory=lambda **kwargs: _MalformedStreamClient(**kwargs)).run())
    sample = result.samples[0]
    assert sample.error_type == "invalid_response"
    assert sample.stream_interrupted is True
    assert result.summary.stream_interruption_rate == 1.0


def test_fixed_count_runner_schedules_at_most_concurrency_workers(monkeypatch):
    observed = []
    original_gather = asyncio.gather

    async def bounded_gather(*items):
        observed.append(len(items))
        return await original_gather(*items)

    monkeypatch.setattr("qe_platform.loadtest.runner.asyncio.gather", bounded_gather)
    config = LoadTestConfig(target_url="http://test", requests=100, concurrency=3)
    result = asyncio.run(LoadTestRunner(config, client_factory=_factory).run())
    assert result.summary.completed == 100
    assert max(observed) <= 3


def test_runner_consumes_reference_agent_response_protocol(tmp_path):
    import httpx
    from reference_agent.app import create_app

    app = create_app(str(tmp_path / "loadtest-agent.db"))

    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", **kwargs)

    # Protocol integration stays single-threaded because Reference Agent SQLite
    # concurrency is a separately tracked system-under-test defect (Issue #41).
    config = LoadTestConfig(target_url="http://test", requests=2, concurrency=1)
    result = asyncio.run(LoadTestRunner(config, client_factory=factory).run())
    assert result.summary.completed == 2
    assert result.summary.succeeded == 2
    assert all(sample.trace_id and sample.conversation_id for sample in result.samples)
