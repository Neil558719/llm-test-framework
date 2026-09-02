"""Deterministic assertions for business state snapshots."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Union

from llmtest import ResponseEnvelope, ToolCall

from .models import AssertionResult

_MISSING = object()
_SEGMENT = re.compile(r"([^.[\]]+)|\[(\d+)\]")
_OPERATORS = {"equals", "exists", "contains", "not_equals"}


Source = Union[ResponseEnvelope, ToolCall, Mapping[str, Any]]


def _normalize(source: Source) -> Mapping[str, Any]:
    if isinstance(source, ResponseEnvelope):
        return source.as_dict()
    if isinstance(source, ToolCall):
        return source.as_dict()
    if isinstance(source, Mapping):
        return source
    raise TypeError("source must be a ResponseEnvelope, ToolCall, or mapping")


def _segments(path: str) -> list[Union[str, int]]:
    if not path:
        raise ValueError(f"invalid business-state path: {path!r}")
    result: list[Union[str, int]] = []
    position = 0
    previous_was_index = False
    for match in _SEGMENT.finditer(path):
        separator = path[position:match.start()]
        if position and separator not in ("", "."):
            raise ValueError(f"invalid business-state path: {path!r}")
        if not position and separator:
            raise ValueError(f"invalid business-state path: {path!r}")
        current_is_index = match.group(2) is not None
        if position and not separator and previous_was_index and not current_is_index:
            raise ValueError(f"invalid business-state path: {path!r}")
        result.append(int(match.group(2)) if current_is_index else match.group(1))
        position = match.end()
        previous_was_index = current_is_index
    if position != len(path) or path.endswith("."):
        raise ValueError(f"invalid business-state path: {path!r}")
    return result


def _lookup(source: Any, path: str) -> Any:
    value = source
    for segment in _segments(path):
        if isinstance(segment, int):
            if not isinstance(value, (list, tuple)) or segment >= len(value):
                return _MISSING
            value = value[segment]
        elif isinstance(value, Mapping) and segment in value:
            value = value[segment]
        else:
            return _MISSING
    return value


def validate_business_state(source: Source, path: str, expected: Any, *, operator: str = "equals") -> AssertionResult:
    if operator not in _OPERATORS:
        raise ValueError(f"unknown business-state operator: {operator}")
    actual = _lookup(_normalize(source), path)
    if operator == "exists":
        passed = actual is not _MISSING
    elif actual is _MISSING:
        passed = False
    elif operator == "equals":
        passed = actual == expected
    elif operator == "not_equals":
        passed = actual != expected
    else:
        try:
            passed = expected in actual
        except TypeError:
            passed = False
    return AssertionResult("business_state", passed, "business state matched" if passed else f"business state {operator} mismatch", path, expected, None if actual is _MISSING else actual)


def assert_business_state(source: Source, path: str, expected: Any, *, operator: str = "equals") -> AssertionResult:
    result = validate_business_state(source, path, expected, operator=operator)
    if not result.passed:
        raise AssertionError(f"{result.assertion_type} failed at {result.path}: {result.message}; expected={result.expected!r}, actual={result.actual!r}")
    return result


__all__ = ["assert_business_state", "validate_business_state"]
