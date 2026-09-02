# YAML Scenario DSL and Workflow Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a strict YAML scenario DSL and independent workflow runner that executes multi-turn Reference Agent API tests using milestone 7 contracts.

**Architecture:** `qe_platform.scenarios` owns typed YAML models, schema validation, and asset errors. `qe_platform.adapters` owns the application boundary and a Reference Agent TestClient adapter. `qe_platform.workflow_runner` executes steps and returns serializable results without importing pytest or changing the system under test.

**Tech Stack:** Python 3.9+, dataclasses, PyYAML safe loading, JSON Schema Draft 2020-12, FastAPI TestClient, existing `ResponseEnvelope` and `qe_platform.contracts`.

**Spec:** `docs/superpowers/specs/2026-09-02-m8-yaml-runner-design.md`

## Global Constraints

- Keep `reference_agent` free of test assertions and platform imports.
- Preserve `AppResponse`, `ResponseEnvelope`, and all existing `llmtest` APIs.
- YAML is declarative data only; no Python hooks, SQL, shell, or dynamic execution.
- Deterministic tool, business-state, and response checks reuse `qe_platform.contracts`.
- Quality/Judge expectations are preserved as `not_executed`; never report them as passed.
- FastGPT remains explicitly out of scope; Dify expansion remains milestone 14.
- Use TDD for every production behavior: failing test, red verification, minimal implementation, green verification, regression.
- Maintain Python 3.9 compatibility and include `qe_platform` plus built-in YAML assets in distributions.

### Task 1: Scenario Models and YAML Loader

**Files:**
- Create: `qe_platform/scenarios/__init__.py`
- Create: `qe_platform/scenarios/models.py`
- Create: `qe_platform/scenarios/schema.py`
- Create: `qe_platform/scenarios/loader.py`
- Modify: `qe_platform/__init__.py`
- Modify: `pyproject.toml`
- Test: `tests/test_scenario_loader.py`

**Interfaces:**
- Produces `ScenarioSpec`, `SetupSpec`, `ConversationStep`, `ExpectationSpec`, `ExpectedToolCall`, `BusinessStateExpectation`, `ResponseExpectation`, `QualityExpectation`, and `ScenarioLoadError`.
- Produces `load_scenarios(path: str | Path) -> list[ScenarioSpec]` and `load_scenario_text(text: str, *, source="<memory>") -> list[ScenarioSpec]`.
- Each model exposes `as_dict()` and uses Python 3.9-compatible annotations.

- [ ] **Step 1: Write the failing tests**

Cover one valid mapping, top-level `scenarios` list, lexical directory loading, unknown fields, missing/empty conversation, invalid YAML, duplicate IDs, unknown operators, invalid embedded schemas, unsupported paths/extensions, and stable source/path errors. Assert parsed nested expectations and `quality` preservation.

```python
def test_loader_parses_valid_multiturn_asset(tmp_path):
    path = tmp_path / "ticket.yaml"
    path.write_text("""id: ticket-1
name: Ticket
conversation:
  - user: VPN is down
  - user: make it high priority
expect:
  tool_order: [query_user, query_asset, create_ticket]
""", encoding="utf-8")
    scenarios = load_scenarios(path)
    assert scenarios[0].conversation[1].user == "make it high priority"
    assert scenarios[0].expect.tool_order == ["query_user", "query_asset", "create_ticket"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests/test_scenario_loader.py -q`
Expected: FAIL with `ModuleNotFoundError` or missing loader symbols.

- [ ] **Step 3: Write minimal implementation**

Add PyYAML to runtime dependencies. Define a Draft 2020-12 schema with `additionalProperties: false` at every object level. Parse mappings into frozen dataclasses, validate embedded tool schemas by constructing `ToolContract`, validate business operators, and include source plus JSON-style path in `ScenarioLoadError`. Normalize one-document and list-document forms and reject duplicate IDs across a directory.

- [ ] **Step 4: Run focused tests**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests/test_scenario_loader.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add qe_platform/scenarios qe_platform/__init__.py pyproject.toml tests/test_scenario_loader.py
git commit -m "feat: add yaml scenario models and loader"
```

### Task 2: Application Adapter and Response Conversion

**Files:**
- Create: `qe_platform/adapters/__init__.py`
- Create: `qe_platform/adapters/base.py`
- Create: `qe_platform/adapters/reference_agent.py`
- Test: `tests/test_reference_agent_adapter.py`

**Interfaces:**
- Produces `ApplicationAdapter` protocol, `ApplicationAdapterError`, and `ReferenceAgentAdapter.from_setup(setup: SetupSpec)`.
- `ReferenceAgentAdapter.send(message, *, user_id, session_id) -> ResponseEnvelope` calls the real `/api/chat` HTTP boundary.

- [ ] **Step 1: Write the failing tests**

Test setup records/failures are translated to real services, session/user IDs are sent unchanged, tool calls and metadata become `ResponseEnvelope`, and non-2xx or malformed responses raise `ApplicationAdapterError` with safe status/message data.

```python
def test_reference_adapter_returns_envelope_from_chat_api():
    setup = SetupSpec(user_id="U1001", session_id="adapter-1", users=[{"user_id": "U1001", "name": "张三"}])
    adapter = ReferenceAgentAdapter.from_setup(setup)
    envelope = adapter.send("VPN 无法连接", user_id="U1001", session_id="adapter-1")
    assert envelope.conversation_id == "adapter-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests/test_reference_agent_adapter.py -q`
Expected: FAIL because the adapter package and protocol are absent.

- [ ] **Step 3: Write minimal implementation**

Construct `UserService`, `AssetService`, `TicketService`, `ApprovalService`, and `KnowledgeBase` from setup data and `FailureConfig`. Use `create_app(":memory:", ...)` and FastAPI `TestClient`; convert the returned envelope dictionary, including nested tool calls, latency, usage, raw response, and metadata. Check HTTP status before JSON conversion and catch response validation errors as `ApplicationAdapterError`.

- [ ] **Step 4: Run focused and regression tests**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests/test_reference_agent_adapter.py tests/test_reference_agent_core.py tests/test_reference_agent_ticket.py tests/test_reference_agent_access.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add qe_platform/adapters tests/test_reference_agent_adapter.py
git commit -m "feat: add reference agent scenario adapter"
```

### Task 3: Workflow Runner and Structured Results

**Files:**
- Create: `qe_platform/workflow_runner/__init__.py`
- Create: `qe_platform/workflow_runner/models.py`
- Create: `qe_platform/workflow_runner/runner.py`
- Modify: `qe_platform/adapters/__init__.py`
- Test: `tests/test_workflow_runner.py`

**Interfaces:**
- Produces `StepResult`, `QualityCheckResult`, `ScenarioRunResult`, and `ScenarioRunner(adapter_factory).run(scenario)`.
- `ScenarioRunResult.passed` requires no execution error and all executed deterministic assertions to pass; `.complete` is false for any declared `not_executed` quality check.

- [ ] **Step 1: Write the failing tests**

Cover one-step response contains/not-contains/source checks, multi-turn session continuity, step and aggregate tool order/contracts/business state, assertion accumulation without stopping subsequent steps, adapter errors stopping dependent steps, and quality checks marked `not_executed`.

```python
def test_runner_reuses_session_and_marks_quality_not_executed():
    calls = []
    class Adapter:
        def send(self, message, *, user_id, session_id):
            calls.append((message, user_id, session_id))
            return ResponseEnvelope(answer="ok")
    scenario = ScenarioSpec.from_dict({"id": "s1", "name": "S", "conversation": [{"user": "one"}, {"user": "two"}], "quality": {"relevance": {"min_score": 0.8}}})
    result = ScenarioRunner(lambda setup: Adapter()).run(scenario)
    assert calls[0][2] == calls[1][2] == result.session_id
    assert result.complete is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests/test_workflow_runner.py -q`
Expected: FAIL because runner and result models are absent.

- [ ] **Step 3: Write minimal implementation**

Execute conversation in order through one adapter instance, generate a UUID only when setup has no session ID, evaluate response and business assertions into result lists, accumulate tool calls, and apply scenario-level tool expectations to the aggregate sequence. Catch adapter exceptions into `error` step results and stop dependent steps. Preserve quality declarations as `QualityCheckResult(status="not_executed")`. Implement `as_dict()` and properties without importing pytest.

- [ ] **Step 4: Run focused tests**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests/test_workflow_runner.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add qe_platform/workflow_runner qe_platform/adapters tests/test_workflow_runner.py
git commit -m "feat: add yaml scenario workflow runner"
```

### Task 4: Built-in Assets and End-to-End Acceptance

**Files:**
- Create: `qe_platform/scenarios/assets/reference_agent/knowledge-hit.yaml`
- Create: `qe_platform/scenarios/assets/reference_agent/ticket-create.yaml`
- Create: `qe_platform/scenarios/assets/reference_agent/access-handoff.yaml`
- Create: `tests/test_builtin_scenarios.py`
- Modify: `pyproject.toml`
- Modify: `docs/AI应用全链路质量平台开发流程.md`

**Interfaces:**
- Produces package-distributed YAML assets and a test helper that loads and runs every built-in asset through `ScenarioRunner`.

- [ ] **Step 1: Write the failing tests**

Assert the package asset directory contains all three workflow assets, each loads with no asset errors, each runs through the Reference Agent adapter, and each has `passed is True`. Assert `load_scenarios` rejects duplicate IDs across a temporary directory and that quality declarations do not make `.complete` true.

- [ ] **Step 2: Run tests to verify they fail**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests/test_builtin_scenarios.py -q`
Expected: FAIL because built-in assets and runner integration are absent.

- [ ] **Step 3: Write minimal implementation**

Create assets for knowledge hit/refusal, ticket success and failure recovery, and access approval plus handoff/missing-information paths. Add package-data configuration for `qe_platform/scenarios/assets/**/*.yaml`. Use only existing deterministic setup fields and no FastGPT references.

- [ ] **Step 4: Run focused, regression, and full tests**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests/test_scenario_loader.py tests/test_reference_agent_adapter.py tests/test_workflow_runner.py tests/test_builtin_scenarios.py -q`
Expected: PASS.

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests/test_tool_contracts.py tests/test_business_assertions.py tests/test_contract_integration.py tests/test_reference_agent_core.py tests/test_reference_agent_ticket.py tests/test_reference_agent_access.py tests/test_reference_agent_knowledge.py -q`
Expected: PASS.

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest -q`
Expected: Existing 72 passing tests plus all milestone 8 tests pass; the known Embedding skip and upstream warnings may remain.

- [ ] **Step 5: Update evidence and inspect diff**

Record exact focused/full test counts in the milestone 8 status row. Run `compileall`, `git diff --check`, and build a wheel to verify all `qe_platform` Python modules and YAML assets are included. Inspect the diff for Agent/platform separation and absence of FastGPT additions.

- [ ] **Step 6: Commit**

```bash
git add qe_platform tests pyproject.toml docs/AI应用全链路质量平台开发流程.md
git commit -m "feat: add built-in yaml scenario assets"
```

## Final Verification and Delivery

Run the full suite once more, then push `codex/m8-yaml-runner`, open a PR linked to Issue #13, wait for both CI Python versions, add an independent review comment, merge to `master`, rerun the full suite on merged `master`, publish `v0.1.0-alpha.7` as a pre-release, and comment Issue #13 with evidence. Production deployment, deployed smoke validation, and issue/telemetry tracking remain explicitly pending unless executed.
