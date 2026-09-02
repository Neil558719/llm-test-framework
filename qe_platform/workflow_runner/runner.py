from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, List, Optional

from llmtest import ResponseEnvelope, ToolCall
from qe_platform.adapters import ApplicationAdapterError
from qe_platform.contracts import (
    AssertionResult, ToolContract, validate_business_state, validate_tool_arguments,
    validate_tool_contract, validate_tool_order, validate_tool_status,
)
from qe_platform.scenarios import ConversationStep, ExpectedToolCall, ScenarioSpec

from .models import QualityCheckResult, ScenarioRunResult, StepResult


class ScenarioRunner:
    def __init__(self, adapter_factory: Callable[[Any], Any]):
        self.adapter_factory = adapter_factory

    def run(self, scenario: ScenarioSpec) -> ScenarioRunResult:
        session_id = scenario.setup.session_id or str(uuid.uuid4())
        user_id = scenario.setup.user_id
        started_at = datetime.now(timezone.utc).isoformat()
        result = ScenarioRunResult(
            scenario.id, scenario.name, scenario.source, session_id, started_at,
            expected_step_count=len(scenario.conversation),
        )
        try:
            adapter = self.adapter_factory(scenario.setup)
        except Exception as exc:
            result.steps.append(StepResult(index=0, user="", status="error", error=str(exc)))
            result.final_assertions.append(AssertionResult("execution", False, str(exc), path="adapter"))
            result.finished_at = datetime.now(timezone.utc).isoformat()
            return result
        for index, step in enumerate(scenario.conversation):
            step_result = StepResult(index=index, user=step.user, status="passed")
            try:
                response = adapter.send(step.user, user_id=user_id, session_id=session_id)
            except Exception as exc:
                step_result.status = "error"
                step_result.error = str(exc)
                result.steps.append(step_result)
                result.final_assertions.append(AssertionResult("execution", False, str(exc), path=f"steps[{index}]"))
                break
            step_result.response = response
            result.tool_calls.extend(response.tool_calls)
            if step.expect:
                step_result.assertions.extend(self._check_expectation(step.expect, response))
            if any(not item.passed for item in step_result.assertions):
                step_result.status = "failed"
            result.steps.append(step_result)
        final_response = result.steps[-1].response if result.steps and result.steps[-1].response else None
        execution_error = next((step.error for step in result.steps if step.status == "error"), "")
        result.final_assertions.extend(self._check_expectation(scenario.expect, final_response, result.tool_calls, execution_error=execution_error))
        result.quality_checks = [QualityCheckResult(metric=name, expectation=value) for name, value in scenario.quality.metrics.items()]
        result.finished_at = datetime.now(timezone.utc).isoformat()
        return result

    def _check_expectation(self, expect, response: Optional[ResponseEnvelope], calls: Optional[List[ToolCall]] = None, state_response: Optional[ResponseEnvelope] = None, execution_error: str = "") -> List[AssertionResult]:
        checks: List[AssertionResult] = []
        if response is not None:
            for text in expect.response.contains:
                checks.append(AssertionResult("response_contains", text in response.answer, "response contains value" if text in response.answer else "response missing value", "answer", text, response.answer))
            for text in expect.response.not_contains:
                checks.append(AssertionResult("response_not_contains", text not in response.answer, "response excludes value" if text not in response.answer else "response contains forbidden value", "answer", text, response.answer))
            if expect.response.sources_present is not None:
                actual = bool(response.sources)
                wanted = expect.response.sources_present
                checks.append(AssertionResult("sources_present", actual == wanted, "source presence matched" if actual == wanted else "source presence mismatch", "sources", wanted, actual))
            state_response = response
        elif execution_error:
            message = f"not evaluated because of execution error: {execution_error}"
            for text in expect.response.contains:
                checks.append(AssertionResult("response_contains", False, message, "answer", text, None))
            for text in expect.response.not_contains:
                checks.append(AssertionResult("response_not_contains", False, message, "answer", text, None))
            if expect.response.sources_present is not None:
                checks.append(AssertionResult("sources_present", False, message, "sources", expect.response.sources_present, None))
        calls = calls if calls is not None else (response.tool_calls if response else [])
        for position, item in enumerate(expect.tools):
            if position >= len(calls):
                checks.append(AssertionResult("tool_name", False, "expected tool call was not found", f"tool_calls[{position}]", item.name, None))
                continue
            call = calls[position]
            if call.name != item.name:
                checks.append(AssertionResult("tool_name", False, "tool name mismatch", f"tool_calls[{position}].name", item.name, call.name))
            checks.append(validate_tool_arguments(call, item.arguments, call_index=position))
            checks.append(validate_tool_status(call, item.status, call_index=position))
            if item.arguments_schema or item.result_schema:
                schema = item.arguments_schema or {"type": "object"}
                checks.extend(validate_tool_contract(call, ToolContract(item.name, schema, item.result_schema), call_index=position))
        if expect.tool_order:
            checks.append(validate_tool_order(calls, expect.tool_order, strict=expect.strict_tool_order))
        if state_response is not None:
            for item in expect.business_state:
                checks.append(validate_business_state(state_response, item.path, item.value, operator=item.operator))
        elif execution_error:
            for item in expect.business_state:
                checks.append(AssertionResult("business_state", False, f"not evaluated because of execution error: {execution_error}", item.path, item.value, None))
        return checks
