# Milestone 13 Fault Injection and SLA/SLO Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver an authenticated request-scoped fault matrix and an independent SLA/SLO, recovery, and cost gate for the Reference Agent.

**Architecture:** The Reference Agent parses a disabled-by-default fault header into an immutable per-request profile and explicitly passes it through storage, model, tool, knowledge, and SSE boundaries. A separate `qe_platform.loadtest` gate suite reuses the milestone 12 runner, evaluates fault observations and thresholds, writes combined reports, and returns a dedicated gate-failure exit code.

**Tech Stack:** Python 3.9+, FastAPI, Pydantic, LangGraph, asyncio, httpx, PyYAML, pytest, Docker Compose, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-06-m13-fault-slo-gate-design.md`

## Global Constraints

- Preserve the public `AppResponse`/`ResponseEnvelope` contract and existing `llmtest-load` behavior.
- Keep all quality assertions in `qe_platform`; the Reference Agent only exposes authenticated test fault behavior.
- Fault controls default to disabled and require `REFERENCE_AGENT_TEST_FAULTS_ENABLED=true` plus a non-empty `REFERENCE_AGENT_TEST_FAULT_TOKEN`.
- Fault state is immutable and request-scoped; no shared mutable fault registry is allowed.
- Do not add FastGPT dependencies, adapters, scenarios, deployment steps, or CI jobs.
- Implement every production behavior with a focused red test before its implementation.
- Complete Issue → branch → local tests → push → PR → Actions → review → merge → Release → deployment and issue tracking before marking milestone 13 complete.

---

### Task 1: Strict authenticated fault profiles

**Files:**
- Create: `reference_agent/faults.py`
- Create: `tests/test_reference_agent_fault_controls.py`

**Interfaces:**
- Produces: `FaultControlSettings.from_env() -> FaultControlSettings`.
- Produces: `FaultControlSettings.resolve(token: str | None, raw_fault: str | None) -> FaultProfile | None`.
- Produces: immutable `FaultProfile(type, target, status_code, delay_seconds)` with `before_database()`, `before_model()`, and `before_service(name)` methods.
- Produces: `FaultControlError(status_code, message)`, `InjectedDatabaseError`, and `ModelRateLimitError`.

- [ ] **Step 1: Write failing security and validation tests**

```python
def test_fault_control_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("REFERENCE_AGENT_TEST_FAULTS_ENABLED", raising=False)
    settings = FaultControlSettings.from_env()
    with pytest.raises(FaultControlError) as error:
        settings.resolve("secret", '{"type":"model_timeout"}')
    assert error.value.status_code == 403

def test_fault_control_rejects_wrong_token_and_unknown_fields():
    settings = FaultControlSettings(True, "secret")
    with pytest.raises(FaultControlError, match="credentials"):
        settings.resolve("wrong", '{"type":"model_timeout"}')
    with pytest.raises(FaultControlError, match="unknown"):
        settings.resolve("secret", '{"type":"model_timeout","extra":1}')
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run: `python -m pytest -q tests/test_reference_agent_fault_controls.py`

Expected: collection fails because `reference_agent.faults` does not exist.

- [ ] **Step 3: Implement the strict parser and fault primitives**

```python
@dataclass(frozen=True)
class FaultControlSettings:
    enabled: bool = False
    token: str = ""

    def resolve(self, token: str | None, raw_fault: str | None) -> FaultProfile | None:
        if raw_fault is None:
            return None
        if not self.enabled or not token or not compare_digest(token, self.token):
            raise FaultControlError(403, "test fault credentials rejected")
        return FaultProfile.from_json(raw_fault)
```

Validate the seven exact types, target requirements, HTTP status range, finite delay range `0 < delay_seconds <= 5`, string keys, and no unknown keys. Make `from_env` reject an enabled configuration with an empty token.

- [ ] **Step 4: Run focused tests and confirm GREEN**

Run: `python -m pytest -q tests/test_reference_agent_fault_controls.py`

Expected: all fault-control parsing and primitive behavior tests pass.

- [ ] **Step 5: Commit the fault-profile unit**

```bash
git add reference_agent/faults.py tests/test_reference_agent_fault_controls.py
git commit -m "feat: add authenticated request fault profiles"
```

### Task 2: Reference Agent request-scoped fault execution

**Files:**
- Modify: `reference_agent/app.py`
- Modify: `reference_agent/graph.py`
- Modify: `reference_agent/runtime/agent.py`
- Modify: `docker-compose.yml`
- Modify: `tests/test_reference_agent_fault_controls.py`
- Create: `tests/test_reference_agent_fault_matrix.py`

**Interfaces:**
- Consumes: `FaultControlSettings.resolve`, `FaultProfile.before_database`, `FaultProfile.before_model`, and `FaultProfile.before_service` from Task 1.
- Produces: `create_app(..., fault_settings: FaultControlSettings | None = None)`.
- Produces: authenticated `X-QE-Test-Token` and `X-QE-Fault` handling only on `/api/chat` and `/api/chat/stream`.
- Produces: allowed observation metadata through existing fields and stable HTTP 503 for injected database failure.

- [ ] **Step 1: Write failing HTTP/SSE matrix and concurrency-isolation tests**

```python
@pytest.mark.parametrize("fault_type,expected", [
    ("model_timeout", (200, "TimeoutError")),
    ("model_429", (200, "ModelRateLimitError")),
    ("knowledge_unavailable", (200, "unavailable")),
    ("database_error", (503, None)),
])
def test_fault_is_observed_and_next_request_recovers(fault_type, expected, tmp_path):
    client = TestClient(create_app(str(tmp_path / "agent.db"), fault_settings=FaultControlSettings(True, "secret")))
    injected = client.post("/api/chat", headers=fault_headers(fault_type), json=knowledge_body("fault"))
    recovered = client.post("/api/chat", json=knowledge_body("recovery"))
    assert injected.status_code == expected[0]
    assert recovered.status_code == 200
    assert recovered.json()["metadata"]["knowledge_status"] == "answered"
```

Add dedicated cases for downstream ticket 5xx, a delayed asset tool, SSE ending before `complete`, malformed/disabled/wrong-token headers, database session recovery, and simultaneous injected and normal requests.

- [ ] **Step 2: Run the matrix tests and confirm RED**

Run: `python -m pytest -q tests/test_reference_agent_fault_controls.py tests/test_reference_agent_fault_matrix.py`

Expected: requests ignore or reject unsupported fault headers and matrix assertions fail.

- [ ] **Step 3: Pass the immutable profile through every injection boundary**

```python
def _run_chat(request: ChatRequest, fault: FaultProfile | None) -> dict[str, Any]:
    if fault is not None:
        fault.before_database()
    store.upsert_session(session_id, request.user_id)
    result = app.state.runtime.invoke({**state, "fault": fault})
```

Resolve headers before side effects. Call `before_model()` inside both model try blocks, call `before_service()` inside each existing service error boundary, stop the SSE generator after `start` for `sse_interruption`, and map only `InjectedDatabaseError` to HTTP 503. Keep real unexpected database failures unchanged.

- [ ] **Step 4: Run matrix and existing Agent regressions**

Run: `python -m pytest -q tests/test_reference_agent_fault_controls.py tests/test_reference_agent_fault_matrix.py tests/test_reference_agent_*.py`

Expected: all new and existing Reference Agent tests pass, including concurrent SQLite coverage.

- [ ] **Step 5: Commit request-scoped fault execution**

```bash
git add reference_agent docker-compose.yml tests/test_reference_agent_fault_controls.py tests/test_reference_agent_fault_matrix.py
git commit -m "feat: execute isolated Reference Agent fault scenarios"
```

### Task 3: Sample observations and SLA/SLO evaluator

**Files:**
- Modify: `qe_platform/loadtest/models.py`
- Modify: `qe_platform/loadtest/runner.py`
- Create: `qe_platform/loadtest/gate_models.py`
- Create: `qe_platform/loadtest/gates.py`
- Modify: `tests/test_loadtest_runner.py`
- Create: `tests/test_loadtest_gates.py`

**Interfaces:**
- Produces: `SampleResult.observations: Mapping[str, Any]` containing only allowed non-sensitive values.
- Produces: immutable `GateThresholds`, `SampleExpectation`, and `GateCheck` data classes.
- Produces: `evaluate_thresholds(summary, thresholds, stage) -> list[GateCheck]`.
- Produces: `evaluate_samples(samples, expectation, stage) -> list[GateCheck]`.

- [ ] **Step 1: Write failing observation and threshold tests**

```python
def test_thresholds_include_equal_boundary_and_fail_missing_metric():
    checks = evaluate_thresholds(summary(latency_p95=100), GateThresholds(max_latency_p95_ms=100), "fault")
    assert checks[0].passed is True
    missing = evaluate_thresholds(summary(ttft_p95=None), GateThresholds(max_ttft_p95_ms=100), "fault")
    assert missing[0].passed is False

def test_runner_extracts_only_allowlisted_observations():
    sample = run_payload({"metadata": {"fallback_reason": "TimeoutError", "private": "secret"}})
    assert sample.observations == {"fallback_reason": "TimeoutError", "failed_tool_count": 0, "source_count": 0}
```

Cover all maximum/minimum checks, exact boundaries, cost per success, missing cost, mixed currency, sample success/status/error, business status, source count, failed tool count, and minimum duration.

- [ ] **Step 2: Run evaluator tests and confirm RED**

Run: `python -m pytest -q tests/test_loadtest_runner.py tests/test_loadtest_gates.py`

Expected: new types/functions and observation fields are absent.

- [ ] **Step 3: Implement allowlisted extraction and pure gate evaluation**

```python
_THRESHOLD_RULES = {
    "max_error_rate": ("error_rate", "<=", lambda a, b: a <= b),
    "min_throughput_rps": ("throughput_rps", ">=", lambda a, b: a >= b),
    "max_latency_p95_ms": ("latency_ms.p95", "<=", lambda a, b: a <= b),
}
```

Return one immutable check per configured field. A configured threshold with `None` actual data fails with an explicit reason. Never mutate `LoadTestSummary` or reinterpret expected fault samples as successful load samples.

- [ ] **Step 4: Run focused evaluator tests and confirm GREEN**

Run: `python -m pytest -q tests/test_loadtest_runner.py tests/test_loadtest_gates.py`

Expected: observation extraction and all gate comparisons pass.

- [ ] **Step 5: Commit the evaluator**

```bash
git add qe_platform/loadtest/models.py qe_platform/loadtest/runner.py qe_platform/loadtest/gate_models.py qe_platform/loadtest/gates.py tests/test_loadtest_runner.py tests/test_loadtest_gates.py
git commit -m "feat: evaluate load-test SLO and fault expectations"
```

### Task 4: Strict gate-suite configuration and orchestration

**Files:**
- Create: `qe_platform/loadtest/gate_config.py`
- Create: `qe_platform/loadtest/gate_runner.py`
- Create: `tests/test_loadtest_gate_config.py`
- Create: `tests/test_loadtest_gate_runner.py`

**Interfaces:**
- Consumes: milestone 12 `LoadTestConfig`/`LoadTestRunner` and Task 3 evaluators.
- Produces: `load_gate_config(path) -> GateSuiteConfig` with strict nested validation.
- Produces: `GateSuiteRunner(config, client_factory=httpx.AsyncClient, environ=os.environ).run() -> GateSuiteResult`.
- Produces: sequential fault then recovery phases while continuing after failed checks.

- [ ] **Step 1: Write failing strict-config and orchestration tests**

```python
def test_gate_config_rejects_inline_secret_and_unknown_nested_field(tmp_path):
    path = write_gate(tmp_path, "fault_token: secret")
    with pytest.raises(ValueError, match="unknown"):
        load_gate_config(path)

def test_runner_executes_fault_then_recovery_and_continues_after_failure():
    result = asyncio.run(GateSuiteRunner(config, load_runner_factory=recording_factory).run())
    assert calls == [("model-timeout", True), ("model-timeout", False), ("database-error", True), ("database-error", False)]
    assert len(result.scenarios) == 2
```

Cover missing token environment variable, duplicate scenario IDs, unsupported fault/protocol combinations, inherited defaults, threshold override, and report path validation.

- [ ] **Step 2: Run gate configuration and runner tests and confirm RED**

Run: `python -m pytest -q tests/test_loadtest_gate_config.py tests/test_loadtest_gate_runner.py`

Expected: gate configuration and orchestration modules do not exist.

- [ ] **Step 3: Implement strict models, loader, and sequential phases**

```python
fault_headers = {
    **scenario.load.headers,
    "X-QE-Test-Token": token,
    "X-QE-Fault": json.dumps(scenario.fault.as_dict(), separators=(",", ":")),
}
fault_run = await self._run_load(replace(scenario.load, headers=fault_headers))
recovery_run = await self._run_load(replace(scenario.load, headers=scenario.load.headers)) if scenario.recovery else None
```

Store only the fault type in public suite output. Apply scenario thresholds over suite defaults, evaluate fault expectations on fault samples, evaluate recovery expectations and thresholds on recovery samples, and keep running remaining scenarios after a failed check.

- [ ] **Step 4: Run gate-suite tests and existing load-test regressions**

Run: `python -m pytest -q tests/test_loadtest_*.py`

Expected: all milestone 12 and milestone 13 load-test tests pass.

- [ ] **Step 5: Commit gate-suite orchestration**

```bash
git add qe_platform/loadtest/gate_config.py qe_platform/loadtest/gate_runner.py tests/test_loadtest_gate_config.py tests/test_loadtest_gate_runner.py
git commit -m "feat: orchestrate fault and recovery gate suites"
```

### Task 5: Gate reports and deterministic CLI

**Files:**
- Create: `qe_platform/loadtest/gate_reporting.py`
- Create: `qe_platform/loadtest/gate_cli.py`
- Modify: `qe_platform/loadtest/__init__.py`
- Modify: `pyproject.toml`
- Create: `tests/test_loadtest_gate_reporting.py`
- Create: `tests/test_loadtest_gate_cli.py`

**Interfaces:**
- Consumes: `GateSuiteResult` from Task 4.
- Produces: `write_gate_reports(result) -> tuple[Path, Path]`.
- Produces: `gate_cli.main(argv: Sequence[str] | None = None) -> int` with exit codes 0/1/2/3.
- Produces: console command `llmtest-gate`.

- [ ] **Step 1: Write failing report, redaction, and exit-code tests**

```python
def test_gate_cli_returns_three_when_checks_fail(monkeypatch, tmp_path):
    monkeypatch.setattr(gate_cli, "load_gate_config", lambda _: config)
    monkeypatch.setattr(gate_cli, "GateSuiteRunner", failing_runner)
    assert gate_cli.main([str(tmp_path / "gate.yaml")]) == 3

def test_gate_report_contains_actual_limits_without_secrets(tmp_path):
    write_gate_reports(result_with_failed_latency_check(tmp_path))
    text = (tmp_path / "gate.html").read_text(encoding="utf-8")
    assert "max_latency_p95_ms" in text and "1000" in text and "FAILED" in text
    assert "top-secret" not in text
```

Cover success 0, runtime/report error 1, configuration error 2, gate failure 3, JSON schema content, self-contained HTML, fault and recovery sections, and absence of user message/control headers/token.

- [ ] **Step 2: Run report and CLI tests and confirm RED**

Run: `python -m pytest -q tests/test_loadtest_gate_reporting.py tests/test_loadtest_gate_cli.py`

Expected: report and CLI modules do not exist.

- [ ] **Step 3: Implement combined reports and CLI**

```python
if not result.gate_passed:
    print(f"Gate failed: {result.failed_checks} checks failed", file=sys.stderr)
    return 3
return 0
```

Write JSON from explicit `as_dict` methods. Escape every dynamic HTML value, embed all CSS, show actual/expected/operator/reason for every check, and use public load-run serialization only.

- [ ] **Step 4: Run CLI/report tests and all load-test regressions**

Run: `python -m pytest -q tests/test_loadtest_*.py`

Expected: every load-test configuration, runner, metric, report, gate, and CLI test passes.

- [ ] **Step 5: Commit the reports and CLI**

```bash
git add qe_platform/loadtest pyproject.toml tests/test_loadtest_gate_reporting.py tests/test_loadtest_gate_cli.py
git commit -m "feat: report and enforce milestone 13 quality gates"
```

### Task 6: Fixed fault matrix, CI gate, and user documentation

**Files:**
- Create: `configs/m13-reference-agent-gate.yaml`
- Modify: `.github/workflows/loadtest.yml`
- Modify: `README.md`
- Create: `tests/test_m13_gate_assets.py`
- Modify: `docs/AI应用全链路质量平台开发流程.md`

**Interfaces:**
- Consumes: `llmtest-gate` and Reference Agent fault environment variables.
- Produces: repository-owned seven-fault gate configuration.
- Produces: Linux CI service startup, health wait, gate execution, and JSON/HTML artifact upload.
- Produces: documented local commands and security boundary.

- [ ] **Step 1: Write failing asset and workflow contract tests**

```python
def test_fixed_gate_matrix_covers_every_required_fault():
    config = load_gate_config(ROOT / "configs/m13-reference-agent-gate.yaml")
    assert {scenario.fault.type for scenario in config.scenarios} == {
        "model_timeout", "model_429", "downstream_5xx", "tool_slow_response",
        "knowledge_unavailable", "sse_interruption", "database_error",
    }
    assert all(scenario.recovery for scenario in config.scenarios)
```

Assert the workflow enables fault controls only for the M13 service step, invokes `llmtest-gate`, waits for health, uploads both reports, and contains no literal production credential.

- [ ] **Step 2: Run asset tests and confirm RED**

Run: `python -m pytest -q tests/test_m13_gate_assets.py`

Expected: the fixed configuration and CI job are absent.

- [ ] **Step 3: Add the seven-fault config, CI job, and documentation**

```yaml
- name: Run milestone 13 network quality gate
  env:
    REFERENCE_AGENT_TEST_FAULT_TOKEN: ci-m13-ephemeral-token
  run: python -m qe_platform.loadtest.gate_cli configs/m13-reference-agent-gate.yaml
```

Start `uvicorn reference_agent.deployment:create_deployment_app --factory` with an ephemeral database and fault controls enabled, poll `/api/health` with a bounded loop, always upload `reports/m13-gate.json` and `reports/m13-gate.html`, and terminate the background process after the job. Document default-disabled behavior and local token setup without committing a real secret.

- [ ] **Step 4: Run focused and broad local verification**

Run: `python -m pytest -q tests/test_reference_agent_fault_controls.py tests/test_reference_agent_fault_matrix.py tests/test_loadtest_*.py tests/test_m13_gate_assets.py`

Run: `python -m compileall -q llmtest qe_platform reference_agent tests`

Run: `git diff --check`

Expected: all focused tests pass, byte compilation succeeds, and the diff has no whitespace errors.

- [ ] **Step 5: Mark status as implementation-complete but delivery-pending and commit**

Update milestone 13 in the progress table with exact local commands/results while stating Push, PR, Actions, review, merge, Release, and deployment remain pending.

```bash
git add configs/m13-reference-agent-gate.yaml .github/workflows/loadtest.yml README.md tests/test_m13_gate_assets.py docs/AI应用全链路质量平台开发流程.md
git commit -m "ci: run milestone 13 fault and SLO gate"
```

### Task 7: Full verification, review, release, and deployment evidence

**Files:**
- Create: `docs/deployment/evidence/2026-09-06-m13-fault-slo-gate.md`
- Modify: `docs/AI应用全链路质量平台开发流程.md`
- Modify: GitHub Issue #46, Pull Request, Release, and deployment state.

**Interfaces:**
- Consumes: all milestone 13 commands and reports.
- Produces: independently reviewed PR, merged master, prerelease tag, candidate/release-image reports, and local deployment evidence.

- [ ] **Step 1: Execute all local acceptance gates**

Run non-UI pytest with a unique absolute system `--basetemp` and `-p no:cacheprovider`; run UI tests with `-m ui`; run `python -m qe_platform.v1_gate`; run the M13 gate against a candidate Docker image; run `compileall`, Compose config validation, and `git diff --check`.

Expected: no failed test or gate; seven fault and seven recovery scenarios pass; JSON/HTML contain no configured token.

- [ ] **Step 2: Perform independent diff and acceptance review**

Review every changed file against the design, Issue #46, security defaults, API compatibility, all seven faults, all thresholds, report redaction, and lifecycle evidence. Correct findings and rerun affected checks before continuing.

- [ ] **Step 3: Push, open PR, wait for Actions, and merge**

Push `codex/m13-fault-slo-gate`, create a PR linked to Issue #46, wait for every required GitHub Action, record independent review, and merge only while all checks are green.

- [ ] **Step 4: Verify merged master and publish the prerelease**

Fast-forward local `master`, rerun the full non-UI suite and V1/M13 gates, build an image from the exact merge SHA, and publish the next `v0.2.0-alpha.*` prerelease with JSON/HTML reports attached.

- [ ] **Step 5: Deploy and record durable evidence**

Back up and integrity-check the existing SQLite database. Run the exact release image in an isolated validation Compose project with fault controls enabled and repeat the full matrix; deploy the release image to the local main service with controls disabled, then verify health, smoke, revision, fault rejection, and SQLite integrity.

- [ ] **Step 6: Finalize status and tracking**

Write `docs/deployment/evidence/2026-09-06-m13-fault-slo-gate.md` with exact commands, counts, SHAs, report assets, security checks, remaining cloud limitations, PR/Release/Issue links, and deployment results. Update the status table to completed, deliver the evidence through a reviewed docs change if needed, close Issue #46, and verify local `master` equals `origin/master` with a clean worktree.
