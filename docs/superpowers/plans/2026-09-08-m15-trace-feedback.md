# Milestone 15 Trace and Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a privacy-safe SQLite Trace/feedback API and optional non-blocking Reference Agent telemetry emitter.

**Architecture:** `qe_platform.telemetry` owns immutable sanitized events, HMAC fingerprints, app factory, HTTP sink, configuration and retention CLI. `qe_platform.storage` owns the repository protocol and SQLite driver; `qe_platform.feedback` owns the seven-category contract. The Agent emits only after it has constructed the business `ResponseEnvelope`, and catches every telemetry error.

**Tech Stack:** Python 3.9+, FastAPI/TestClient, `sqlite3`, `urllib.request`, HMAC-SHA256, pytest.

**Spec:** `docs/superpowers/specs/2026-09-08-m15-trace-feedback-design.md`

## Global Constraints

- Use `QE_TELEMETRY_DATABASE`, never `REFERENCE_AGENT_DATABASE`; default retention is exactly 30 days and must be positive.
- Never persist plaintext message, answer, user/session ID, token, authorization header, raw request/response, tool arguments/results, or free-text feedback.
- HMAC identifying/text values with `QE_TELEMETRY_HASH_KEY`; reject nested forbidden payload keys.
- `POST /api/traces` requires `X-QE-Telemetry-Token`, and the token must never appear in data or errors.
- Agent telemetry requires endpoint, ingest token and hash key; it is otherwise no-op and never changes business response/API/SSE behavior.
- Keep `ResponseEnvelope`, existing V1/UI/load/Dify tests and FastGPT exclusion intact. PostgreSQL has an interface only, not a working driver.

---

### Task 1: Trace, Feedback, and Redaction Contracts

**Files:**
- Create: `qe_platform/telemetry/__init__.py`, `qe_platform/telemetry/models.py`, `qe_platform/telemetry/redaction.py`
- Create: `qe_platform/feedback/__init__.py`, `qe_platform/feedback/models.py`
- Test: `tests/test_telemetry_models.py`

**Interfaces:** Produces `TelemetryTrace`, `ToolSummary`, `TelemetryQuery`, `build_trace_event(trace_id, application, user_id, session_id, request_text, answer_text, hash_key, *, tool_calls, metadata, usage, cost, model_version, latency)`, `assert_sanitized_payload`, `FeedbackKind`, `FeedbackInput`, `FeedbackRecord`, `FeedbackQuery`; storage and API consume these values.

- [ ] **Step 1: Write failing privacy and category tests**

```python
def test_trace_event_hmacs_plaintext_and_omits_tool_arguments():
    trace = build_trace_event("trace-1", "reference-agent", "U1001", "s1",
        "private request", "private answer", "hash-key", tool_calls=[{"name": "create_ticket", "arguments": {"secret": "x"}}])
    text = json.dumps(trace.as_dict())
    assert "private request" not in text and "private answer" not in text
    assert "arguments" not in text and trace.user_hash != "U1001"

def test_nested_authorization_field_is_rejected():
    with pytest.raises(ValueError, match="forbidden"):
        assert_sanitized_payload({"metadata": {"authorization": "Bearer secret"}})
```

- [ ] **Step 2: Verify red state**

Run: `python -m pytest tests/test_telemetry_models.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m15-t1-red`

Expected: FAIL because the contracts do not exist.

- [ ] **Step 3: Implement the minimal contracts**

```python
class FeedbackKind(str, Enum):
    CORRECT = "correct"; INACCURATE = "inaccurate"; IRRELEVANT = "irrelevant"
    INCOMPLETE = "incomplete"; HALLUCINATION = "hallucination"
    TOOL_EXECUTION_ERROR = "tool_execution_error"; SLOW_RESPONSE = "slow_response"

def fingerprint(value: str, hash_key: str) -> str:
    return hmac.new(hash_key.encode(), value.encode(), hashlib.sha256).hexdigest()
```

Validate nonempty IDs, UTC timestamps, nonnegative numeric values, finite cost, versions and tool summaries limited to name/status. Allow only declared top-level ingest keys and recursively refuse `message`, `answer`, `authorization`, `api_key`, `token`, `arguments`, `result`, and raw request/response keys. `FeedbackInput` has category, reporter identifier and source only.

- [ ] **Step 4: Verify green state and commit**

Run: `python -m pytest tests/test_telemetry_models.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m15-t1-green`

Expected: PASS for deterministic HMAC, all seven categories, JSON serialization and prohibited values.

Commit: `git add qe_platform/telemetry qe_platform/feedback tests/test_telemetry_models.py; git commit -m "feat: add sanitized telemetry contracts"`

### Task 2: SQLite Repository and Retention Boundary

**Files:**
- Create: `qe_platform/storage/__init__.py`, `qe_platform/storage/telemetry.py`
- Test: `tests/test_telemetry_storage.py`

**Interfaces:** Consumes Task 1 values. Produces `TelemetryRepository`, `SQLiteTelemetryRepository`, `PostgreSQLTelemetryRepository`, `create_telemetry_repository` and `prune_expired`.

- [ ] **Step 1: Write failing storage tests**

```python
def test_sqlite_upserts_trace_links_feedback_and_removes_expired_rows(tmp_path):
    repo = SQLiteTelemetryRepository(tmp_path / "telemetry.db", retention_days=30)
    repo.upsert_trace(trace_at("2026-08-01T00:00:00+00:00"))
    repo.add_feedback(FeedbackInput(FeedbackKind.INACCURATE, "reporter", "ui"), "trace-1")
    assert repo.get_trace("trace-1").feedback_count == 1
    assert repo.prune_expired(now=utc("2026-09-01T00:00:00+00:00")) == 1
    assert repo.list_feedback(FeedbackQuery(trace_id="trace-1")) == []
```

- [ ] **Step 2: Verify red state**

Run: `python -m pytest tests/test_telemetry_storage.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m15-t2-red`

Expected: FAIL because no storage driver exists.

- [ ] **Step 3: Implement repository protocol and SQLite schema**

```python
class TelemetryRepository(Protocol):
    def upsert_trace(self, trace: TelemetryTrace) -> TelemetryTrace: ...
    def get_trace(self, trace_id: str, *, now: datetime | None = None) -> TelemetryTrace | None: ...
    def list_traces(self, query: TelemetryQuery, *, now: datetime | None = None) -> list[TelemetryTrace]: ...
    def add_feedback(self, value: FeedbackInput, trace_id: str) -> FeedbackRecord: ...
    def list_feedback(self, query: FeedbackQuery, *, now: datetime | None = None) -> list[FeedbackRecord]: ...
    def prune_expired(self, *, now: datetime) -> int: ...
```

Use one locked SQLite connection, `PRAGMA foreign_keys=ON`, parameterized SQL, transaction rollback, deterministic timestamp/ID pagination and `ON DELETE CASCADE`. Persist only `TelemetryTrace.as_dict()` safe fields. The PostgreSQL factory path raises `NotImplementedError("PostgreSQL telemetry storage is not enabled")`; unrecognized schemes raise `ValueError`.

- [ ] **Step 4: Verify green state and commit**

Run: `python -m pytest tests/test_telemetry_models.py tests/test_telemetry_storage.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m15-t2-green`

Expected: PASS for reopen persistence, filters/pagination, absent Trace, concurrent writes, feedback cascade, expiry boundary and PostgreSQL boundary.

Commit: `git add qe_platform/storage tests/test_telemetry_storage.py; git commit -m "feat: persist sanitized telemetry and feedback"`

### Task 3: Settings, Platform API, and Retention CLI

**Files:**
- Create: `qe_platform/telemetry/settings.py`, `qe_platform/telemetry/api.py`, `qe_platform/telemetry/cli.py`
- Modify: `pyproject.toml`
- Test: `tests/test_telemetry_api.py`, `tests/test_telemetry_cli.py`

**Interfaces:** Consumes Tasks 1-2. Produces `TelemetrySettings.from_environment`, `create_telemetry_app(settings, repository=None)` and script `telemetry-prune`.

- [ ] **Step 1: Write failing API and CLI tests**

```python
def test_ingest_requires_token_and_get_never_returns_forbidden_fields(tmp_path):
    app = create_telemetry_app(TelemetrySettings(str(tmp_path / "telemetry.db"), "hash-key", "ingest-token", 30))
    client = TestClient(app)
    assert client.post("/api/traces", json=safe_payload()).status_code == 401
    assert client.post("/api/traces", headers={"X-QE-Telemetry-Token": "ingest-token"}, json=safe_payload()).status_code == 201
    assert "answer" not in client.get("/api/traces/trace-1").json()
```

- [ ] **Step 2: Verify red state**

Run: `python -m pytest tests/test_telemetry_api.py tests/test_telemetry_cli.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m15-t3-red`

Expected: FAIL because no app/settings/CLI exists.

- [ ] **Step 3: Implement safe endpoint and prune command**

```python
@app.post("/api/traces", status_code=201)
def ingest(payload: dict[str, Any], x_qe_telemetry_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_ingest_token(x_qe_telemetry_token, settings.ingest_token)
    return repository.upsert_trace(TelemetryTrace.from_dict(payload)).as_dict()

@app.post("/api/traces/{trace_id}/feedback", status_code=201)
def feedback(trace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return repository.add_feedback(FeedbackInput.from_dict(payload, settings.hash_key), trace_id).as_dict()
```

Return 400 for malformed/forbidden values, 401 for invalid token, 404 for absent Trace and generic payload-free 500 for unexpected storage failure. Limit list endpoints to 1..100 and parse only UTC ISO date filters. The command reads environment settings, calls `prune_expired(datetime.now(timezone.utc))`, prints deletion count and returns 2 without traceback on bad configuration. Add `telemetry-prune = "qe_platform.telemetry.cli:main"` to project scripts.

- [ ] **Step 4: Verify green state and commit**

Run: `python -m pytest tests/test_telemetry_models.py tests/test_telemetry_storage.py tests/test_telemetry_api.py tests/test_telemetry_cli.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m15-t3-green`

Expected: PASS for authentication, idempotency, safe query output, feedback types, filters, expiry, invalid settings and token-safe errors.

Commit: `git add qe_platform/telemetry pyproject.toml tests/test_telemetry_api.py tests/test_telemetry_cli.py; git commit -m "feat: expose telemetry trace feedback API"`

### Task 4: Optional Reference Agent Telemetry Sink

**Files:**
- Create: `qe_platform/telemetry/sink.py`
- Modify: `reference_agent/app.py`, `reference_agent/deployment.py`, `docker-compose.yml`
- Test: `tests/test_reference_agent_telemetry.py`, `tests/test_reference_agent_deployment_config.py`

**Interfaces:** Consumes `build_trace_event` and produces `TelemetrySink.emit`, `NoopTelemetrySink`, `HttpTelemetrySink`, `telemetry_sink_from_environment`, and optional `telemetry_sink` injection in `create_app`.

- [ ] **Step 1: Write failing Agent integration tests**

```python
def test_chat_emits_sanitized_trace_after_business_result():
    sink = RecordingSink()
    response = TestClient(create_app(":memory:", telemetry_sink=sink)).post("/api/chat", json={"message": "private request", "user_id": "U1001"})
    assert response.status_code == 200
    assert sink.events[0].trace_id == response.json()["trace_id"]
    assert "private request" not in json.dumps(sink.events[0].as_dict())

def test_sink_failure_does_not_change_chat_or_sse_response():
    assert TestClient(create_app(":memory:", telemetry_sink=FailingSink())).post("/api/chat", json={"message": "你好"}).status_code == 200
```

- [ ] **Step 2: Verify red state**

Run: `python -m pytest tests/test_reference_agent_telemetry.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m15-t4-red`

Expected: FAIL because `create_app` has no telemetry sink or event emission.

- [ ] **Step 3: Implement no-op/default/HTTP sink and post-response emission**

```python
def telemetry_sink_from_environment() -> TelemetrySink:
    return HttpTelemetrySink(endpoint, token, hash_key) if endpoint and token and hash_key else NoopTelemetrySink()

def _emit_telemetry(sink: TelemetrySink, request: ChatRequest, envelope: ResponseEnvelope) -> None:
    try:
        sink.emit(build_trace_event(envelope.trace_id, "reference-agent", request.user_id,
            envelope.conversation_id, request.message, envelope.answer, sink.hash_key,
            tool_calls=envelope.tool_calls, metadata=envelope.metadata, usage=envelope.usage,
            cost=envelope.cost, model_version=envelope.model_version, latency=envelope.latency))
    except Exception:
        pass
```

Emit once after cost calculation and before `envelope.as_dict()`. Use `urllib.request` with short timeout and put token only in outgoing header. Add only `QE_TELEMETRY_ENDPOINT`, `QE_TELEMETRY_INGEST_TOKEN`, `QE_TELEMETRY_HASH_KEY`, `QE_TELEMETRY_RETENTION_DAYS` Compose pass-through; do not return keys through health/profile endpoints.

- [ ] **Step 4: Verify green state and commit**

Run: `python -m pytest tests/test_reference_agent_telemetry.py tests/test_reference_agent_deployment_config.py tests/test_reference_agent_core.py tests/test_reference_agent_ui_api.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m15-t4-green`

Expected: PASS for no-op config, event shape, tool/usage/cost/version capture, sink/network failure, HTTP/SSE compatibility and Compose declarations.

Commit: `git add qe_platform/telemetry/sink.py reference_agent/app.py reference_agent/deployment.py docker-compose.yml tests/test_reference_agent_telemetry.py tests/test_reference_agent_deployment_config.py; git commit -m "feat: emit optional sanitized agent telemetry"`

### Task 5: Guide, CI Contract, Status Record, and Lifecycle

**Files:**
- Create: `docs/Trace 与反馈 API 指南.md`, `tests/test_m15_docs.py`
- Modify: `README.md`, `.github/workflows/loadtest.yml`, `docs/AI应用全链路质量平台开发流程.md`

**Interfaces:** Documents the delivered API/CLI environment names and creates an offline `M15 telemetry contract` CI job.

- [ ] **Step 1: Write failing guide/workflow tests**

```python
def test_m15_guide_uses_environment_only_for_secrets_and_records_limits():
    guide = Path("docs/Trace 与反馈 API 指南.md").read_text(encoding="utf-8")
    assert "QE_TELEMETRY_INGEST_TOKEN" in guide and "--token" not in guide
    assert "30" in guide and "人工复核" in guide and "FastGPT" not in guide
```

- [ ] **Step 2: Verify red state**

Run: `python -m pytest tests/test_m15_docs.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m15-t5-red`

Expected: FAIL because guide and status evidence do not exist.

- [ ] **Step 3: Implement documentation and CI job**

Document separate database, environment-only secrets, 30-day policy, CLI, placeholder-only API examples, current read/feedback authorization limit, PostgreSQL boundary and M16/M17 exclusions. CI must use temporary local files and ephemeral values only, never external URL/credentials. Set progress row to `实现完成（交付进行中）` with modules, branch test command/results and all pending lifecycle stages.

- [ ] **Step 4: Verify branch acceptance and commit**

Run:

```powershell
python -m pytest tests/test_telemetry_models.py tests/test_telemetry_storage.py tests/test_telemetry_api.py tests/test_telemetry_cli.py tests/test_reference_agent_telemetry.py tests/test_m15_docs.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m15-acceptance
python -m pytest --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m15-full
python -m pytest -m ui --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m15-ui
python -m compileall -q llmtest qe_platform reference_agent tests
docker compose config --quiet
git diff --check
```

Expected: relevant tests, default regression and UI pass; compile, Compose and whitespace checks return zero.

Commit: `git add docs README.md .github/workflows/loadtest.yml tests/test_m15_docs.py; git commit -m "docs: record milestone 15 telemetry acceptance"`

### Task 6: Review, Merge, Release, Deployment, and Closeout

**Files:**
- Modify: `docs/deployment/evidence/2026-09-08-m15-trace-feedback.md`, `docs/AI应用全链路质量平台开发流程.md`

**Interfaces:** Converts verified review, PR, Actions, merge, release and deployment facts into the authoritative delivery record.

- [ ] **Step 1: Request independent review and test each accepted finding**

Run: independent review against `master...codex/m15-trace-feedback`; each accepted finding must first reproduce in a focused failing test, then pass with a minimal fix.

- [ ] **Step 2: Push branch and create Issue #52 PR**

Run: `git -c http.proxy= -c https.proxy= push -u origin codex/m15-trace-feedback`, then create a PR titled `feat: add trace storage and feedback API` with Issue #52, privacy boundary, 30-day policy, tests and M16/M17 exclusions.

- [ ] **Step 3: Merge only with clean Actions and diff**

Run: `gh pr checks "$(gh pr view --json number --jq .number)"` and `gh pr view --json mergeStateStatus,statusCheckRollup`.

Expected: Offline, V1, load-test, M13, M15, Playwright and Container Readiness checks succeed; state is `CLEAN`.

- [ ] **Step 4: Verify merged master, release and deploy exact image**

Run default/UI regression and V1 gate on master, tag the next pre-release at merge SHA, build matching `BUILD_REV`, back up SQLite, run `docker compose -p llmbackup up -d --no-build --wait`, run smoke and `PRAGMA integrity_check`.

Expected: healthy image revision equals release SHA, smoke 4/4, integrity `ok`, telemetry remains disabled without explicit valid configuration.

- [ ] **Step 5: Merge closeout evidence and close Issue #52**

Use only verified results in evidence/status, verify its tests on master, and close the Issue if PR auto-close did not do so.
