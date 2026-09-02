# Tool Contract and Business Assertion Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable deterministic contract and business-state assertion library for observed IT Agent tool calls.

**Architecture:** Add a framework-owned `qe_platform.contracts` package with data-only models, tool validators, and business-state validators. Validators return serializable `AssertionResult` objects; thin `assert_*` wrappers aggregate failures into actionable `AssertionError` exceptions. The package consumes existing `llmtest.ToolCall` and `ResponseEnvelope` without modifying the Agent or pytest plugin.

**Tech Stack:** Python 3.9+, dataclasses, `jsonschema` Draft 2020-12, pytest, FastAPI TestClient, existing reference Agent services.

**Spec:** `docs/superpowers/specs/2026-09-02-m7-tool-contracts-design.md`

## Global Constraints

- Keep `AppResponse`, `ResponseEnvelope`, and existing `llmtest` APIs backward compatible.
- Keep assertions outside `reference_agent`; the Agent must not import `qe_platform`.
- Validate tool names, arguments, order, statuses, and business state deterministically; do not use Judge for these checks.
- Do not add YAML execution, persistence, report rendering, Dify-specific logic, or FastGPT capability.
- Use TDD: write a focused failing test, run it, implement the smallest change, then rerun focused and regression tests.
- Preserve Python 3.9 compatibility in annotations and runtime behavior.

### Task 1: Contract Models and Package Exports

**Files:**
- Create: `qe_platform/__init__.py`
- Create: `qe_platform/contracts/__init__.py`
- Create: `qe_platform/contracts/models.py`
- Test: `tests/test_tool_contracts.py`

**Interfaces:**
- Produces `ToolContract(name, arguments_schema, result_schema=None)`, `AssertionResult(assertion_type, passed, message, path="", expected=None, actual=None)`, and `AssertionResult.as_dict()`.
- Exports both models from `qe_platform.contracts`.

- [ ] **Step 1: Write the failing test**

```python
from qe_platform.contracts import AssertionResult, ToolContract


def test_models_are_immutable_and_serializable():
    contract = ToolContract("query_user", {"type": "object"})
    result = AssertionResult("tool_name", True, "ok", expected="query_user", actual="query_user")
    assert contract.name == "query_user"
    assert result.as_dict() == {
        "assertion_type": "tool_name",
        "passed": True,
        "message": "ok",
        "path": "",
        "expected": "query_user",
        "actual": "query_user",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests/test_tool_contracts.py::test_models_are_immutable_and_serializable -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'qe_platform'`.

- [ ] **Step 3: Write minimal implementation**

Implement frozen dataclasses in `models.py`; copy schema mappings on construction only if needed to prevent accidental mutation, and implement `as_dict()` with the exact field names above. Add package `__init__.py` files and re-export the models.

- [ ] **Step 4: Run test to verify it passes**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests/test_tool_contracts.py::test_models_are_immutable_and_serializable -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add qe_platform tests/test_tool_contracts.py
git commit -m "feat: add contract result models"
```

### Task 2: Tool Contract Validators

**Files:**
- Create: `qe_platform/contracts/tool_assertions.py`
- Modify: `qe_platform/contracts/__init__.py`
- Test: `tests/test_tool_contracts.py`

**Interfaces:**
- Consumes `ToolContract`, `AssertionResult`, and `llmtest.ToolCall`.
- Produces `validate_tool_contract(call, contract, *, call_index=0) -> list[AssertionResult]`, `validate_tool_arguments(call, expected, *, call_index=0, allow_extra=True) -> AssertionResult`, `validate_tool_order(calls, expected_names, *, strict=True) -> AssertionResult`, `validate_tool_status(call, expected_status="succeeded", *, call_index=0) -> AssertionResult`.
- Produces matching `assert_tool_contract`, `assert_tool_arguments`, `assert_tool_order`, and `assert_tool_status` wrappers returning the same result shape or raising aggregated `AssertionError`.

- [ ] **Step 1: Write the failing tests**

Add tests for a valid contract, wrong name, required/missing and wrong-type arguments, nested expected argument values, optional result schema, strict order, subsequence order, duplicate names, and failed tool status. Assert failure messages contain `call[<index>]`, the relevant path, expected, and actual values.

```python
from llmtest import ToolCall
from qe_platform.contracts import ToolContract, assert_tool_contract, assert_tool_order


def test_contract_checks_name_arguments_and_result():
    call = ToolCall("create_ticket", {"priority": "high"}, {"ticket_id": "T-1", "status": "created"})
    contract = ToolContract(
        "create_ticket",
        {"type": "object", "required": ["priority"], "properties": {"priority": {"enum": ["high", "normal"]}}},
        {"type": "object", "required": ["ticket_id", "status"]},
    )
    results = assert_tool_contract(call, contract, call_index=2)
    assert all(item.passed for item in results)


def test_order_wrapper_reports_sequence_difference():
    calls = [ToolCall("query_user"), ToolCall("create_ticket")]
    with pytest.raises(AssertionError, match=r"call\[1\].*expected.*query_asset"):
        assert_tool_order(calls, ["query_user", "query_asset", "create_ticket"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests/test_tool_contracts.py -q`
Expected: FAIL because validator functions are not defined.

- [ ] **Step 3: Write minimal implementation**

Use `jsonschema.Draft202012Validator` and `iter_errors`, sorted by absolute path. Return one result per name/schema/status check with JSON-style paths. Implement recursive expected-argument comparison with subset semantics by default. Implement exact order and ordered-subsequence matching, preserving duplicate positions. Implement a shared wrapper helper that raises one `AssertionError` containing every failed result in input order.

- [ ] **Step 4: Run focused tests**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests/test_tool_contracts.py -q`
Expected: PASS.

- [ ] **Step 5: Run contract regression checks**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests/test_response_envelope.py tests/test_reference_agent_ticket.py tests/test_reference_agent_access.py -q`
Expected: Existing tests pass with no changes to Agent behavior.

- [ ] **Step 6: Commit**

```bash
git add qe_platform/contracts tests/test_tool_contracts.py
git commit -m "feat: add deterministic tool contract assertions"
```

### Task 3: Business State Assertions and Agent Integration

**Files:**
- Create: `qe_platform/contracts/business_assertions.py`
- Modify: `qe_platform/contracts/__init__.py`
- Create: `tests/test_business_assertions.py`
- Create: `tests/test_contract_integration.py`

**Interfaces:**
- Consumes `ResponseEnvelope`, `ToolCall`, and mappings.
- Produces `validate_business_state(source, path, expected, *, operator="equals") -> AssertionResult` and `assert_business_state(...) -> AssertionResult`.

- [ ] **Step 1: Write the failing tests**

Cover `metadata.ticket_status`, `ToolCall.result.status`, nested list paths such as `tool_calls[2].result.ticket_id`, mapping sources, present `None`, missing paths, `equals`, `not_equals`, `contains`, `exists`, unknown operator, and actionable assertion text. Add integration tests that invoke the existing ticket and approval graphs, then validate their real call sequences and `ResponseEnvelope` metadata only through the public contract API.

```python
def test_business_state_distinguishes_missing_from_none():
    source = {"metadata": {"value": None}}
    assert validate_business_state(source, "metadata.value", None).passed
    assert not validate_business_state(source, "metadata.missing", None).passed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests/test_business_assertions.py tests/test_contract_integration.py -q`
Expected: FAIL because the business assertion module and public functions are absent.

- [ ] **Step 3: Write minimal implementation**

Normalize `ResponseEnvelope` and `ToolCall` through `as_dict()`, accept mappings directly, parse dot segments and `[index]` segments, and use an internal missing sentinel. Implement the four specified operators and raise `TypeError` for unsupported sources or `ValueError` for unknown operators. Reuse the wrapper helper from `tool_assertions.py` or expose a small shared formatter without introducing pytest dependencies.

- [ ] **Step 4: Run focused tests**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests/test_business_assertions.py tests/test_contract_integration.py -q`
Expected: PASS.

- [ ] **Step 5: Run milestone regression and full suite**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests/test_response_envelope.py tests/test_reference_agent_ticket.py tests/test_reference_agent_access.py tests/test_reference_agent_knowledge.py -q`
Expected: PASS.

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest -q`
Expected: Existing 45 passing tests plus all new milestone 7 tests pass; the known Embedding skip and LangGraph warnings may remain.

- [ ] **Step 6: Update evidence and inspect diff**

Update `docs/AI应用全链路质量平台开发流程.md` milestone 7 row with exact focused/full test counts and remaining delivery work. Run `git diff --check` and inspect `git diff master...HEAD` for Agent/test-platform separation and excluded FastGPT scope.

- [ ] **Step 7: Commit**

```bash
git add qe_platform tests docs/AI应用全链路质量平台开发流程.md
git commit -m "feat: add business state assertions"
```

## Final Verification and Delivery

After all tasks pass, run the complete suite and `git diff --check` again. Push `codex/m7-tool-contracts`, open a PR linked to Issue #11, wait for both CI Python versions, add the independent review comment, merge to `master`, rerun the full suite on merged `master`, publish `v0.1.0-alpha.6` as a pre-release, and comment Issue #11 with evidence. Production deployment, smoke validation, and issue/telemetry tracking must remain explicitly pending unless actually executed.
