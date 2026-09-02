"""Deterministic assertions for observed tool calls."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence, Union

import jsonschema

from llmtest import ToolCall

from .models import AssertionResult, ToolContract


def _path(root: str, parts: Iterable[Any]) -> str:
    value = root
    for part in parts:
        value += f"[{part}]" if isinstance(part, int) else f".{part}"
    return value


def _failure(result: AssertionResult) -> str:
    return (
        f"{result.assertion_type} failed at {result.path or '$'}: {result.message}; "
        f"expected={result.expected!r}, actual={result.actual!r}"
    )


def _raise_failures(results: Union[AssertionResult, Sequence[AssertionResult]]):
    items = list(results) if isinstance(results, (list, tuple)) else [results]
    failures = [item for item in items if not item.passed]
    if failures:
        raise AssertionError("\n".join(_failure(item) for item in failures))
    return results


def _schema_result(assertion_type: str, value: Any, schema: Mapping[str, Any], path: str) -> AssertionResult:
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(value), key=lambda error: list(error.absolute_path))
    if not errors:
        return AssertionResult(assertion_type, True, "schema validation passed", path=path, actual=value)
    error = errors[0]
    error_path = _path(path, error.absolute_path)
    return AssertionResult(
        assertion_type,
        False,
        error.message,
        path=error_path,
        expected=error.validator_value,
        actual=error.instance,
    )


def validate_tool_contract(call: ToolCall, contract: ToolContract, *, call_index: int = 0) -> list[AssertionResult]:
    base = f"tool_calls[{call_index}]"
    if call.name != contract.name:
        return [AssertionResult("tool_name", False, "tool name mismatch", f"{base}.name", contract.name, call.name)]
    results = [AssertionResult("tool_name", True, "tool name matched", f"{base}.name", contract.name, call.name)]
    results.append(_schema_result("tool_arguments_schema", call.arguments, contract.arguments_schema, f"{base}.arguments"))
    if contract.result_schema is not None and call.status == "succeeded":
        results.append(_schema_result("tool_result_schema", call.result, contract.result_schema, f"{base}.result"))
    return results


def _compare(expected: Any, actual: Any, path: str, allow_extra: bool) -> Union[AssertionResult, None]:
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            return AssertionResult("tool_arguments", False, "expected an object", path, expected, actual)
        for key, value in expected.items():
            child = _path(path, [key])
            if key not in actual:
                return AssertionResult("tool_arguments", False, "missing argument", child, value, None)
            failure = _compare(value, actual[key], child, allow_extra)
            if failure:
                return failure
        if not allow_extra and set(actual) != set(expected):
            return AssertionResult("tool_arguments", False, "unexpected or missing arguments", path, expected, actual)
        return None
    if isinstance(expected, Sequence) and not isinstance(expected, (str, bytes)):
        if not isinstance(actual, Sequence) or isinstance(actual, (str, bytes)) or len(actual) != len(expected):
            return AssertionResult("tool_arguments", False, "sequence mismatch", path, expected, actual)
        for index, (want, got) in enumerate(zip(expected, actual)):
            failure = _compare(want, got, _path(path, [index]), allow_extra)
            if failure:
                return failure
        return None
    if expected != actual:
        return AssertionResult("tool_arguments", False, "argument value mismatch", path, expected, actual)
    return None


def validate_tool_arguments(call: ToolCall, expected: Mapping[str, Any], *, call_index: int = 0, allow_extra: bool = True) -> AssertionResult:
    path = f"tool_calls[{call_index}].arguments"
    failure = _compare(expected, call.arguments, path, allow_extra)
    return failure or AssertionResult("tool_arguments", True, "argument values matched", path, expected, call.arguments)


def validate_tool_order(calls: Sequence[ToolCall], expected_names: Sequence[str], *, strict: bool = True) -> AssertionResult:
    actual = [call.name for call in calls]
    expected = list(expected_names)
    if strict:
        if actual == expected:
            return AssertionResult("tool_order", True, "tool order matched", "tool_calls", expected, actual)
        index = next((i for i, pair in enumerate(zip(actual, expected)) if pair[0] != pair[1]), min(len(actual), len(expected)))
        got = actual[index] if index < len(actual) else None
        want = expected[index] if index < len(expected) else None
        return AssertionResult("tool_order", False, "tool order mismatch", f"tool_calls[{index}].name", want, got)
    cursor = 0
    for name in expected:
        try:
            cursor = actual.index(name, cursor) + 1
        except ValueError:
            return AssertionResult("tool_order", False, "expected ordered tool call was not found", f"tool_calls[{min(cursor, len(actual))}].name", name, actual[cursor] if cursor < len(actual) else None)
    return AssertionResult("tool_order", True, "tool subsequence matched", "tool_calls", expected, actual)


def validate_tool_status(call: ToolCall, expected_status: str = "succeeded", *, call_index: int = 0) -> AssertionResult:
    return AssertionResult("tool_status", call.status == expected_status, "tool status matched" if call.status == expected_status else "tool status mismatch", f"tool_calls[{call_index}].status", expected_status, call.status)


def assert_tool_contract(call: ToolCall, contract: ToolContract, *, call_index: int = 0):
    return _raise_failures(validate_tool_contract(call, contract, call_index=call_index))


def assert_tool_arguments(call: ToolCall, expected: Mapping[str, Any], *, call_index: int = 0, allow_extra: bool = True):
    return _raise_failures(validate_tool_arguments(call, expected, call_index=call_index, allow_extra=allow_extra))


def assert_tool_order(calls: Sequence[ToolCall], expected_names: Sequence[str], *, strict: bool = True):
    return _raise_failures(validate_tool_order(calls, expected_names, strict=strict))


def assert_tool_status(call: ToolCall, expected_status: str = "succeeded", *, call_index: int = 0):
    return _raise_failures(validate_tool_status(call, expected_status, call_index=call_index))


__all__ = [
    "assert_tool_arguments", "assert_tool_contract", "assert_tool_order",
    "assert_tool_status", "validate_tool_arguments", "validate_tool_contract",
    "validate_tool_order", "validate_tool_status",
]
