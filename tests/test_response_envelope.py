"""统一响应协议的兼容性契约测试。"""

from llmtest import (
    AppResponse,
    LatencyMetrics,
    ResponseEnvelope,
    TokenUsage,
    ToolCall,
)


def test_app_response_converts_without_losing_legacy_fields():
    legacy = AppResponse(answer="已找到资料", sources=["知识片段 A"])

    envelope = ResponseEnvelope.from_app_response(legacy)

    assert envelope.answer == legacy.answer
    assert envelope.sources == legacy.sources
    assert envelope.tool_calls == []
    assert envelope.conversation_id == ""
    assert envelope.trace_id == ""


def test_envelope_carries_tool_usage_latency_and_metadata():
    call = ToolCall(
        name="query_asset",
        arguments={"asset_id": "PC-1001"},
        result={"status": "active"},
        status="succeeded",
    )
    envelope = ResponseEnvelope(
        answer="资产正常",
        tool_calls=[call],
        usage=TokenUsage(prompt_tokens=12, completion_tokens=8),
        latency=LatencyMetrics(total_ms=420.0, ttft_ms=110.0),
        trace_id="trace-1",
        raw_response={"id": "resp-1"},
        metadata={"model_version": "mock-v1"},
    )

    assert envelope.tool_calls[0].name == "query_asset"
    assert envelope.usage.total_tokens == 20
    assert envelope.latency.total_ms == 420.0
    assert envelope.as_dict()["trace_id"] == "trace-1"
    assert envelope.as_dict()["tool_calls"][0]["arguments"] == {"asset_id": "PC-1001"}


def test_app_response_can_be_upgraded_to_envelope_explicitly():
    envelope = AppResponse(answer="ok").to_envelope(
        conversation_id="session-1",
        trace_id="trace-1",
    )

    assert isinstance(envelope, ResponseEnvelope)
    assert envelope.conversation_id == "session-1"
    assert envelope.trace_id == "trace-1"
