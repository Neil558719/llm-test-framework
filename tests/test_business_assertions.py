import pytest

from llmtest import ResponseEnvelope, ToolCall
from qe_platform.contracts import (
    assert_business_state,
    validate_business_state,
)


def test_business_state_reads_mapping_and_distinguishes_missing_from_none():
    source = {"metadata": {"value": None}}

    assert validate_business_state(source, "metadata.value", None).passed
    missing = validate_business_state(source, "metadata.missing", None)
    assert not missing.passed
    assert missing.path == "metadata.missing"


def test_business_state_reads_response_envelope_and_nested_tool_result():
    envelope = ResponseEnvelope(
        answer="created",
        tool_calls=[
            ToolCall("query_user"),
            ToolCall("query_asset"),
            ToolCall("create_ticket", result={"ticket_id": "T-0001", "status": "created"}),
        ],
        metadata={"ticket_status": "created"},
    )

    assert validate_business_state(envelope, "metadata.ticket_status", "created").passed
    assert validate_business_state(envelope, "tool_calls[2].result.ticket_id", "T-0001").passed
    assert validate_business_state(envelope.tool_calls[2], "result.status", "created").passed


@pytest.mark.parametrize(
    ("operator", "expected", "passed"),
    [("equals", "created", True), ("not_equals", "pending", True), ("contains", "VPN", True), ("exists", True, True)],
)
def test_business_state_supports_explicit_operators(operator, expected, passed):
    source = {"tags": ["VPN", "network"], "status": "created"}
    path = "tags" if operator == "contains" else "status"

    result = validate_business_state(source, path, expected, operator=operator)

    assert result.passed is passed


def test_business_state_rejects_unknown_operator_and_asserts_actionably():
    with pytest.raises(ValueError, match="unknown business-state operator"):
        validate_business_state({"status": "created"}, "status", "created", operator="matches")

    with pytest.raises(AssertionError, match=r"metadata\.ticket_status.*expected='created'.*actual='pending'"):
        assert_business_state({"metadata": {"ticket_status": "pending"}}, "metadata.ticket_status", "created")


def test_business_state_rejects_unsupported_source_type():
    with pytest.raises(TypeError, match="ResponseEnvelope, ToolCall, or mapping"):
        validate_business_state(object(), "status", "created")


def test_business_state_rejects_invalid_path_syntax():
    with pytest.raises(ValueError, match="invalid business-state path"):
        validate_business_state({"metadata": {}}, "metadata..status", "created")
