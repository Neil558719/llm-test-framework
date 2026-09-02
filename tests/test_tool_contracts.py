import pytest
from jsonschema import SchemaError

from llmtest import ToolCall
from qe_platform.contracts import (
    AssertionResult,
    ToolContract,
    assert_tool_arguments,
    assert_tool_contract,
    assert_tool_order,
    assert_tool_status,
    validate_tool_arguments,
    validate_tool_contract,
    validate_tool_order,
    validate_tool_status,
)


def test_models_are_immutable_and_serializable():
    contract = ToolContract("query_user", {"type": "object"})
    result = AssertionResult(
        "tool_name",
        True,
        "ok",
        expected="query_user",
        actual="query_user",
    )

    assert contract.name == "query_user"
    assert result.as_dict() == {
        "assertion_type": "tool_name",
        "passed": True,
        "message": "ok",
        "path": "",
        "expected": "query_user",
        "actual": "query_user",
    }
    with pytest.raises(AttributeError):
        contract.name = "other"


def test_contract_checks_name_arguments_and_result():
    call = ToolCall(
        "create_ticket",
        {"priority": "high"},
        {"ticket_id": "T-1", "status": "created"},
    )
    contract = ToolContract(
        "create_ticket",
        {
            "type": "object",
            "required": ["priority"],
            "properties": {"priority": {"enum": ["high", "normal"]}},
        },
        {
            "type": "object",
            "required": ["ticket_id", "status"],
            "properties": {"ticket_id": {"type": "string"}},
        },
    )

    results = assert_tool_contract(call, contract, call_index=2)

    assert [result.assertion_type for result in results] == [
        "tool_name",
        "tool_arguments_schema",
        "tool_result_schema",
    ]
    assert all(result.passed for result in results)


def test_invalid_contract_schema_is_a_configuration_error():
    with pytest.raises(SchemaError):
        ToolContract("query_user", {"type": "not-a-json-schema-type"})


def test_contract_name_mismatch_stops_schema_validation():
    call = ToolCall("query_user", {"user_id": "U1001"})
    contract = ToolContract("query_asset", {"type": "object"})

    results = validate_tool_contract(call, contract, call_index=1)

    assert len(results) == 1
    assert not results[0].passed
    assert results[0].path == "tool_calls[1].name"
    with pytest.raises(AssertionError, match=r"tool_calls\[1\]\.name.*query_asset.*query_user"):
        assert_tool_contract(call, contract, call_index=1)


def test_contract_reports_nested_argument_and_result_schema_paths():
    call = ToolCall(
        "create_ticket",
        {"request": {"priority": 3}},
        {"ticket_id": 99},
    )
    contract = ToolContract(
        "create_ticket",
        {
            "type": "object",
            "properties": {
                "request": {
                    "type": "object",
                    "properties": {"priority": {"type": "string"}},
                }
            },
        },
        {
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}},
        },
    )

    results = validate_tool_contract(call, contract, call_index=3)

    assert [result.passed for result in results] == [True, False, False]
    assert results[1].path == "tool_calls[3].arguments.request.priority"
    assert results[2].path == "tool_calls[3].result.ticket_id"


def test_failed_call_skips_success_result_schema():
    call = ToolCall("create_ticket", {}, None, status="failed", error="down")
    contract = ToolContract(
        "create_ticket",
        {"type": "object"},
        {"type": "object", "required": ["ticket_id"]},
    )

    results = validate_tool_contract(call, contract)

    assert [result.assertion_type for result in results] == [
        "tool_name",
        "tool_arguments_schema",
    ]


def test_argument_values_support_nested_subset_and_strict_comparison():
    call = ToolCall(
        "create_ticket",
        {"request": {"asset_id": "PC-1001", "priority": "high"}, "retry": False},
    )

    subset = validate_tool_arguments(
        call,
        {"request": {"asset_id": "PC-1001"}},
        call_index=2,
    )
    strict = validate_tool_arguments(
        call,
        {"request": {"asset_id": "PC-1001"}},
        call_index=2,
        allow_extra=False,
    )

    assert subset.passed
    assert not strict.passed
    assert strict.path == "tool_calls[2].arguments.request"
    with pytest.raises(AssertionError, match=r"tool_calls\[2\]\.arguments\.request"):
        assert_tool_arguments(
            call,
            {"request": {"asset_id": "PC-1001"}},
            call_index=2,
            allow_extra=False,
        )


def test_argument_values_report_missing_nested_path():
    call = ToolCall("create_ticket", {"request": {}})

    result = validate_tool_arguments(
        call,
        {"request": {"asset_id": "PC-1001"}},
        call_index=4,
    )

    assert not result.passed
    assert result.path == "tool_calls[4].arguments.request.asset_id"
    assert result.expected == "PC-1001"


@pytest.mark.parametrize(
    ("strict", "expected", "passed"),
    [
        (True, ["query_user", "query_asset", "create_ticket"], True),
        (True, ["query_user", "create_ticket"], False),
        (False, ["query_user", "create_ticket"], True),
        (False, ["query_user", "query_user"], False),
        (False, [], True),
    ],
)
def test_tool_order_supports_exact_and_subsequence_modes(strict, expected, passed):
    calls = [
        ToolCall("query_user"),
        ToolCall("query_asset"),
        ToolCall("create_ticket"),
    ]

    result = validate_tool_order(calls, expected, strict=strict)

    assert result.passed is passed


def test_order_wrapper_reports_first_sequence_difference():
    calls = [ToolCall("query_user"), ToolCall("create_ticket")]

    with pytest.raises(
        AssertionError,
        match=r"tool_calls\[1\]\.name.*query_asset.*create_ticket",
    ):
        assert_tool_order(calls, ["query_user", "query_asset", "create_ticket"])


def test_tool_status_is_compared_without_inference():
    call = ToolCall("create_ticket", result={"ticket_id": "T-1"}, status="failed")

    result = validate_tool_status(call, call_index=5)

    assert not result.passed
    assert result.path == "tool_calls[5].status"
    with pytest.raises(AssertionError, match=r"succeeded.*failed"):
        assert_tool_status(call, call_index=5)
