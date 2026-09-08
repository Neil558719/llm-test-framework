import json
from datetime import datetime, timezone

import pytest

from qe_platform.feedback import FeedbackInput, FeedbackKind, FeedbackQuery, FeedbackRecord
from qe_platform.telemetry import TelemetryQuery, ToolSummary, assert_sanitized_payload, build_trace_event


HASH_KEY = "test-key"
REQUEST_HASH = "16beff55fc64e01d89cc0941bbf8541e361565d6a790aa6391c62b79a7d6c08b"
ANSWER_HASH = "1f6565182de5ba4d5480090c0b6b8290a6c8ac3604d9a4ca08f3ebe219851ac2"
REPORTER_HASH = "5c046d19135216cdd4c36c9f12f9b7fc330e0376daf2c086970e850a753d09e7"


def test_trace_serialization_fingerprints_text_and_drops_tool_arguments():
    trace = build_trace_event(
        "trace-1", "service-desk", "U1001", "s1", "private request", "private answer", HASH_KEY,
        tool_calls=[{"name": "create_ticket", "status": "succeeded", "arguments": {"description": "private request"}}],
        metadata={"environment": "test", "request_id": "req-1"},
        usage={"prompt_tokens": 3, "completion_tokens": 5},
        cost={"input": 0.01, "output": 0.02, "total": 0.03, "currency": "USD", "price_version": "p1"},
        model_version={"provider": "mock", "model": "mock-v1", "prompt": "prompt-v1", "knowledge_base": "kb-v1", "tools": "tools-v1"},
        latency={"total_ms": 12.5, "ttft_ms": 4.0, "status": "succeeded"},
    )

    payload = trace.as_dict()
    assert trace.request_fingerprint == REQUEST_HASH
    assert payload["answer_fingerprint"] == ANSWER_HASH
    assert payload["request_length"] == len("private request")
    assert payload["answer_length"] == len("private answer")
    assert payload["source"] == {"user_fingerprint": REPORTER_HASH, "session_fingerprint": "28a69be031b9e50ebdb451f1371b5afa9e872ef50935f3d0b21affa1e4df010f"}
    assert payload["tool_calls"] == [{"name": "create_ticket", "status": "succeeded"}]
    assert payload["metadata"] == {"environment": "test", "request_id": "req-1"}
    assert "private request" not in json.dumps(payload)
    assert "private answer" not in json.dumps(payload)
    assert "arguments" not in json.dumps(payload)
    assert_sanitized_payload(payload)


def test_redaction_rejects_nested_forbidden_fields():
    with pytest.raises(ValueError, match="forbidden"):
        build_trace_event(
            "trace-1", "service-desk", "U1001", "s1", "private request", "private answer", HASH_KEY,
            tool_calls=[], metadata={"nested": {"authorization": "Bearer secret"}}, usage={}, cost=None,
            model_version={}, latency={"total_ms": 1, "status": "succeeded"},
        )


@pytest.mark.parametrize("kind", list(FeedbackKind))
def test_feedback_accepts_exactly_the_seven_declared_categories(kind):
    assert FeedbackInput(category=kind, reporter_id="U1001", source="user").category is kind


def test_feedback_serialization_hashes_reporter_and_supports_safe_queries():
    record = FeedbackRecord.from_input(
        "feedback-1", "trace-1", FeedbackInput(FeedbackKind.INACCURATE, "U1001", "user"), HASH_KEY,
        created_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
    )
    payload = record.as_dict()
    assert payload["reporter_fingerprint"] == REPORTER_HASH
    assert "U1001" not in json.dumps(payload)
    assert FeedbackQuery(trace_id="trace-1", category=FeedbackKind.INACCURATE).as_dict() == {"trace_id": "trace-1", "category": "inaccurate"}
    assert TelemetryQuery(application="service-desk", trace_id="trace-1").as_dict() == {"application": "service-desk", "trace_id": "trace-1"}


def test_models_reject_invalid_timestamps_numbers_and_payloads():
    with pytest.raises(ValueError):
        ToolSummary(name="", status="succeeded")
    with pytest.raises(ValueError):
        build_trace_event("", "service-desk", "U1001", "s1", "x", "y", HASH_KEY, tool_calls=[], metadata={}, usage={}, cost=None, model_version={}, latency={"total_ms": 1, "status": "succeeded"})
    with pytest.raises(ValueError):
        build_trace_event("trace-1", "service-desk", "U1001", "s1", "x", "y", HASH_KEY, tool_calls=[], metadata={}, usage={"prompt_tokens": -1}, cost=None, model_version={}, latency={"total_ms": 1, "status": "succeeded"})
    with pytest.raises(ValueError):
        build_trace_event("trace-1", "service-desk", "U1001", "s1", "x", "y", HASH_KEY, tool_calls=[], metadata={}, usage={}, cost={"total": float("inf")}, model_version={}, latency={"total_ms": 1, "status": "succeeded"})
