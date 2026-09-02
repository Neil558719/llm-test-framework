import pytest

from qe_platform.contracts import AssertionResult, ToolContract


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
