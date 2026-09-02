# Milestone 7: Tool Contract and Business Assertion Library Design

Date: 2026-09-02  
Issue: https://github.com/Neil558719/llm-test-framework/issues/11

## 1. Purpose

Milestone 7 adds deterministic, reusable validation for observed tool calls and
business state. The library serves three consumers without coupling them:

- Python and pytest tests in the current repository;
- the YAML scenario runner planned for milestone 8;
- structured reporting and CI gates planned for milestone 9.

Natural-language quality remains the responsibility of `llmtest`. Tool names,
arguments, order, execution status, and business state are validated only by
deterministic code.

## 2. Scope and Boundaries

The implementation belongs under `qe_platform/contracts/`. It consumes
`llmtest.specs.ToolCall` and ordinary mappings, but it does not change
`AppResponse`, `ResponseEnvelope`, the reference Agent, or the pytest plugin.

This milestone includes:

- declarative tool contracts based on JSON Schema;
- structured, serializable validation results;
- validation of tool name, argument schema, expected argument values, result
  schema, call order, and execution status;
- business-state lookup by dot path and deterministic comparisons;
- assertion wrappers that raise actionable `AssertionError` messages;
- integration tests using real ticket and approval call sequences.

This milestone excludes YAML parsing, workflow execution, persistence queries,
quality judging, report rendering, Dify-specific behavior, and all FastGPT
behavior.

## 3. Package Layout

```text
qe_platform/
  __init__.py
  contracts/
    __init__.py
    models.py
    tool_assertions.py
    business_assertions.py

tests/
  test_tool_contracts.py
  test_business_assertions.py
  test_contract_integration.py
```

`models.py` contains data only. Validation logic is split by subject so later
scenario execution can call it without importing pytest or the reference
Agent.

## 4. Public Models

### 4.1 `ToolContract`

```python
@dataclass(frozen=True)
class ToolContract:
    name: str
    arguments_schema: Mapping[str, Any]
    result_schema: Mapping[str, Any] | None = None
```

The schemas use JSON Schema Draft 2020-12 through the repository's existing
`jsonschema` dependency. Contract construction validates schema correctness so
an invalid test contract fails before an observed call is evaluated.

### 4.2 `AssertionResult`

```python
@dataclass(frozen=True)
class AssertionResult:
    assertion_type: str
    passed: bool
    message: str
    path: str = ""
    expected: Any = None
    actual: Any = None
```

`as_dict()` returns JSON-compatible fields with the same names. Values that are
already mappings, sequences, primitives, or `None` are preserved. The library
does not silently stringify arbitrary application objects.

All validation functions return one `AssertionResult` for one logical check.
Batch operations return `list[AssertionResult]` in deterministic input order.

## 5. Tool Validation API

The public validation functions are:

```python
validate_tool_contract(call, contract, *, call_index=0)
validate_tool_arguments(call, expected, *, call_index=0, allow_extra=True)
validate_tool_order(calls, expected_names, *, strict=True)
validate_tool_status(call, expected_status="succeeded", *, call_index=0)
```

`validate_tool_contract` checks, in order:

1. observed tool name equals the contract name;
2. arguments satisfy `arguments_schema`;
3. result satisfies `result_schema` when one is declared and the call status is
   `succeeded`.

It returns all results reached in that order. A name mismatch stops schema
validation because the remaining contract does not describe that call.
Argument failure does not suppress independent result validation.

`validate_tool_arguments` recursively compares expected values against the
observed argument mapping. With `allow_extra=True`, expected arguments form a
subset. With `allow_extra=False`, the complete structures must match. Paths use
JSON-style dot/index notation such as `tool_calls[2].arguments.asset_id`.

`validate_tool_order` has two explicit modes:

- `strict=True`: actual names must exactly equal the expected sequence;
- `strict=False`: expected names must occur as an ordered subsequence, allowing
  unrelated calls between them.

Duplicate tool names are supported and matched by position. Empty expected and
actual sequences pass; an empty expectation with non-empty actual calls passes
only in subsequence mode.

`validate_tool_status` compares the observed status exactly. It does not infer
success from a non-empty result or failure from an error string.

## 6. Business-State Validation API

```python
validate_business_state(source, path, expected, *, operator="equals")
```

`source` may be a `ResponseEnvelope`, a `ToolCall`, or a mapping. It is first
normalized without mutating the caller's object:

- `ResponseEnvelope` exposes its serialized fields, including `metadata` and
  `tool_calls`;
- `ToolCall` exposes `name`, `arguments`, `result`, `status`, and `error`;
- mappings are used as supplied.

There is no hidden source-priority merge. Callers specify an unambiguous path,
for example `metadata.ticket_status`, `result.status`, or
`tool_calls[2].result.ticket_id`. This prevents an identically named field in
metadata from masking a tool result.

Supported operators are deliberately limited to:

- `equals`: actual value equals expected value;
- `exists`: the path exists; `expected` is ignored;
- `contains`: actual collection/string contains expected;
- `not_equals`: actual value differs from expected.

An unknown operator is a configuration error and raises `ValueError`. A missing
path is a normal failed `AssertionResult`, with a dedicated sentinel internally
so a present value of `None` is distinguishable from absence.

## 7. Assertion Wrappers and Failure Messages

Each validator has an `assert_*` wrapper with the same arguments. A wrapper
returns the successful structured result or result list. If any result fails,
it raises one `AssertionError` containing every failure in validation order.

Failure text must include, when applicable:

- assertion type;
- call index;
- full field path;
- expected value;
- actual value;
- the JSON Schema validation message.

The library has no dependency on pytest and does not write directly to the
current `llmtest` metrics tracker. Milestone 9 may translate
`AssertionResult.as_dict()` into unified report entries without changing this
API.

## 8. Error Handling

- Invalid JSON Schema: raise `jsonschema.SchemaError` during contract
  validation setup/use; this is a broken test asset, not a failed system under
  test assertion.
- Unsupported input type: raise `TypeError` with the accepted types.
- Unknown comparison operator: raise `ValueError`.
- Contract mismatch, missing path, wrong value, wrong order, or failed tool
  status: return a failed `AssertionResult`; assertion wrappers convert it to
  `AssertionError`.
- Failed tool calls do not have their result checked against a success result
  schema, because their error contract is represented by status and error.

## 9. Test Strategy

Unit tests cover:

- valid contracts and invalid schemas;
- unknown/wrong tool names;
- missing, extra, nested, and wrong-type arguments;
- optional result-schema validation;
- exact and subsequence order, including duplicates;
- success and failure statuses;
- mapping, `ToolCall`, and `ResponseEnvelope` business-state paths;
- present `None`, missing paths, each operator, and unknown operators;
- stable serialization and actionable aggregated assertion messages.

Integration tests construct the reference Agent's ticket and approval flows and
validate their actual `ToolCall` sequences and resulting business state using
only the public contract API. These tests demonstrate separation: the Agent
does not import or execute its test assertions.

Verification order:

1. run each new focused test and confirm it fails because the API is absent;
2. implement the smallest behavior that makes it pass;
3. run all milestone 7 tests;
4. run ticket, access, and response-envelope regressions;
5. run the complete test suite;
6. run `git diff --check` and independently inspect the diff.

## 10. Acceptance and Delivery

Milestone 7 functional acceptance requires all stated APIs and cases above to
pass while preserving the existing public response models. Delivery then
continues through Push, PR, GitHub Actions, code review, merge to `master`, a
post-merge full regression run, pre-release publication, and deployment/issue
tracking. Local and CI success alone do not establish production deployment.

The known missing Embedding model skip and upstream LangGraph deprecation
warnings remain recorded but do not block this deterministic offline library.
