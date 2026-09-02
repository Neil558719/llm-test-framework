# Milestone 8: YAML Scenario DSL and Workflow Runner Design

Date: 2026-09-02
Issue: https://github.com/Neil558719/llm-test-framework/issues/13

## 1. Purpose

Milestone 8 lets test engineers describe and execute multi-turn AI application
business tests without writing Python test functions. YAML assets are loaded
into typed scenario models, executed through an application adapter, validated
with milestone 7 deterministic assertions, and returned as serializable run
results.

This milestone creates the execution substrate for milestone 9 reporting and
CI gates. It does not render reports or decide release policy itself.

## 2. Architecture and Boundaries

The implementation is split into three platform-owned packages:

```text
qe_platform/
  scenarios/          DSL models, schema, loading and asset errors
  adapters/           application boundary and Reference Agent API adapter
  workflow_runner/    ordered execution and structured results
```

The runner depends only on the adapter protocol, scenario models, the shared
`ResponseEnvelope`, and `qe_platform.contracts`. The Reference Agent never
imports the platform and remains the system under test.

Included:

- safe YAML loading and strict schema validation;
- typed scenario/setup/conversation/expectation models;
- deterministic Reference Agent test-data and fault setup;
- API-boundary execution through `POST /api/chat`;
- multi-turn session reuse;
- per-step and final/aggregate expectations;
- structured, serializable run/step/quality results;
- representative offline scenarios for all three Agent workflows.

Excluded:

- HTML rendering and CI release gates (milestone 9);
- live Judge or embedding execution;
- browser automation and load testing;
- arbitrary Python hooks, SQL, shell commands, or executable YAML;
- Dify adapter expansion (milestone 14);
- all FastGPT functionality.

## 3. YAML Document Format

A `.yaml` or `.yml` file contains either one scenario mapping or a top-level
`scenarios` list. A directory load processes both extensions in lexical path
order. Scenario IDs must be unique across the complete load operation.

```yaml
id: ticket-create-vpn
name: 创建 VPN 故障工单
tags: [ticket, happy_path]
setup:
  user_id: U1001
  session_id: ticket-create-vpn
  users:
    - user_id: U1001
      name: 张三
  assets:
    - asset_id: PC-1001
      owner_id: U1001
      status: active
  failures: {}
conversation:
  - user: "VPN 无法连接，设备 PC-1001，请创建工单，优先级高"
    expect:
      response:
        contains: ["工单", "已创建"]
      business_state:
        - path: metadata.ticket_status
          operator: equals
          value: created
expect:
  tools:
    - name: query_user
      status: succeeded
      arguments:
        user_id: U1001
    - name: query_asset
      arguments:
        asset_id: PC-1001
    - name: create_ticket
      arguments:
        priority: high
  tool_order: [query_user, query_asset, create_ticket]
  strict_tool_order: true
quality:
  relevance:
    min_score: 0.8
```

Unknown fields at every defined object level are rejected. Required fields are
`id`, `name`, and a non-empty `conversation`. IDs and names must be non-empty
strings. Tags default to an empty list. `setup`, step/final `expect`, and
`quality` are optional.

## 4. Scenario Models

Python 3.9-compatible frozen dataclasses represent the validated asset:

- `ScenarioSpec`: `id`, `name`, `tags`, `setup`, `conversation`, `expect`,
  `quality`, and `source`;
- `SetupSpec`: `user_id`, optional `session_id`, user records, asset records,
  knowledge documents, and service failures;
- `ConversationStep`: user text and optional step expectation;
- `ExpectationSpec`: tool expectations, tool order, strict-order flag,
  business-state expectations, and response expectations;
- `ExpectedToolCall`: name, expected argument subset, optional argument/result
  JSON Schema, and expected status;
- `BusinessStateExpectation`: path, operator, and value;
- `ResponseExpectation`: `contains`, `not_contains`, and optional
  `sources_present`;
- `QualityExpectation`: preserved mapping of declared metrics and thresholds.

`source` is the input file path or `<memory>` and is included in all asset
errors. Models expose `as_dict()` for report consumers; no model retains a
PyYAML-specific object.

## 5. Setup and Fault Model

YAML setup is declarative data only. Supported service names are `user`,
`asset`, `ticket`, `approval`, and `knowledge`. Each entry in `failures` has:

```yaml
failures:
  ticket:
    status_code: 500
    message: ticket database unavailable
    delay_seconds: 0
```

`status_code` is optional when only delay is needed. `delay_seconds` is
non-negative. Unsupported service names are rejected during loading.

The Reference Agent adapter factory translates setup records and failure
settings into existing `UserService`, `AssetService`, `TicketService`,
`ApprovalService`, and `KnowledgeBase` instances. It does not add assertion
logic to those services. Defaults remain deterministic when records are not
provided.

This setup boundary intentionally excludes arbitrary database mutation and
custom hooks. SQLite persistence setup beyond normal Agent session behavior is
deferred until a scenario requires a documented platform-owned fixture API.

## 6. Loading and Asset Validation

`load_scenarios(path) -> list[ScenarioSpec]` accepts one file or one directory.
It uses `yaml.safe_load` and JSON Schema Draft 2020-12. `PyYAML>=6.0` becomes a
runtime dependency and `qe_platform*` remains included in built distributions.

`ScenarioLoadError` includes source, a JSON-style asset path, and a stable
message. It is raised for:

- unreadable or syntactically invalid YAML;
- an empty document;
- schema violations or unknown fields;
- duplicate IDs;
- unknown business-state operators;
- invalid embedded JSON Schemas;
- nonexistent path, unsupported extension, or a directory with no YAML files.

Files are completely loaded and validated before any scenario executes. Asset
errors therefore cannot create partial business state.

## 7. Adapter Protocol and Reference Agent Adapter

```python
class ApplicationAdapter(Protocol):
    def send(
        self,
        message: str,
        *,
        user_id: str,
        session_id: str,
    ) -> ResponseEnvelope: ...
```

`ReferenceAgentAdapter.from_setup(setup)` creates a FastAPI `TestClient` around
`reference_agent.create_app` with setup-controlled services and an in-memory
database. `send()` calls `/api/chat` and converts the HTTP JSON response into a
`ResponseEnvelope`, including `ToolCall`, usage, latency, raw response, and
metadata fields when present.

Non-2xx HTTP status or malformed response JSON raises
`ApplicationAdapterError`, carrying status and a safe message. The runner
captures it as a step execution error rather than allowing the test process to
crash.

Adapters are created once per scenario using an injected
`adapter_factory(SetupSpec)`. This provides isolation between scenarios and
session continuity within one scenario.

## 8. Workflow Execution

`ScenarioRunner(adapter_factory).run(scenario)` performs:

1. choose `setup.session_id` or generate a stable run-local UUID;
2. create one adapter for the scenario;
3. send conversation steps sequentially with the same user/session IDs;
4. evaluate each step's expectations against that step response;
5. append all observed tool calls in execution order;
6. evaluate scenario-level expectations against the final response and the
   aggregate tool-call sequence;
7. return `ScenarioRunResult`.

Tool expectations are positional. Each declared tool is matched to the tool at
the same index in the relevant call sequence and validated using milestone 7:

- `ToolContract` when argument/result schemas are present;
- `validate_tool_arguments` for expected values;
- `validate_tool_status` for explicit/default `succeeded` status;
- `validate_tool_order` for the declared order.

Step expectations use only that step's calls. Scenario expectations use all
calls accumulated across steps. Business-state expectations evaluate the
current/final `ResponseEnvelope`. Response checks are deterministic substring
and source-presence checks and return `AssertionResult` entries.

If a step call raises `ApplicationAdapterError` or another application-boundary
exception, the step is recorded as `error`, later conversation steps are not
executed, and final assertions that require a response are recorded as failed
with the execution error context. Assertion failures do not raise out of the
runner and do not stop later conversation steps; they are accumulated so one
run exposes all observable quality defects.

## 9. Structured Results

- `StepResult`: index, user input, optional response, assertion results,
  `status` (`passed`, `failed`, or `error`), and error text;
- `QualityCheckResult`: metric, `status` (`not_executed` in milestone 8),
  declared expectation, and explanation;
- `ScenarioRunResult`: scenario ID/name/source, session ID, ordered steps,
  final assertions, quality checks, start/end timestamps, and aggregate calls.

All results expose `as_dict()` and contain JSON-compatible values.

`ScenarioRunResult.passed` is true only when every executed step and final
deterministic assertion passes and there is no execution error.
`ScenarioRunResult.complete` is false when any declared quality check is
`not_executed`. Thus an unconfigured Judge threshold can never be presented as
passed. Built-in milestone 8 acceptance scenarios do not declare live quality
metrics; a dedicated test verifies the `not_executed` behavior.

## 10. Built-in Offline Scenario Assets

Built-in assets live under
`qe_platform/scenarios/assets/reference_agent/` and are included as package
data so an installed wheel can execute them. User-owned assets may live in any
file or directory accepted by `load_scenarios`. The built-in assets cover:

- knowledge hit with source and out-of-scope refusal;
- ticket creation, missing asset ID, missing user, asset ownership denial,
  duplicate/idempotent request, and ticket service 5xx;
- access creation, multi-turn missing justification recovery, restricted
  resource handoff, missing user, and approval service 5xx.

Slow-response setup is represented and unit-tested without adding load-test
metrics. Knowledge timeout uses the existing failure controls. Empty-result
and handoff paths are part of the asset set. Load testing remains outside
pytest and outside this runner.

## 11. Testing Strategy

TDD proceeds in independently reviewable slices:

1. models, safe YAML loading, schema/path errors, duplicate IDs, and embedded
   schema validation;
2. adapter protocol and Reference Agent API conversion/setup behavior;
3. runner execution, multi-turn continuity, deterministic expectations,
   failure accumulation, adapter errors, and quality completeness;
4. built-in scenario assets and complete offline execution.

Every production behavior begins with a focused failing test. Required
regressions include milestone 7 contracts, all Reference Agent tests, response
compatibility, full pytest, `compileall`, `git diff --check`, and wheel content
inspection for all new packages and YAML assets needed at runtime.

## 12. Acceptance and Delivery

Functional acceptance requires a new valid YAML scenario to run without a new
Python test function; multi-turn session continuity and all deterministic
expectation types must work; failures must identify source/scenario/step/path;
and all built-in offline scenarios must pass.

Delivery then follows Issue #13 through branch Push, Pull Request, Python
3.12/3.14 GitHub Actions, independent review, merge to `master`, post-merge
verification, and pre-release publication. Production deployment, deployed
smoke validation, and telemetry/issue tracking remain explicit pending work
unless actually performed. The known missing Embedding-model skip and upstream
LangGraph warnings remain non-blocking but recorded.
