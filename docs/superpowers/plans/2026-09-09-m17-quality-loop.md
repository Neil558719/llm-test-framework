# M17 Quality Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Deliver the V3 quality loop that aggregates sanitized trends, links online feedback to offline promoted scenarios, and produces reproducible release validation evidence.

**Architecture:** Add a bounded `qe_platform/quality_loop/` package backed by the existing telemetry SQLite file. The package owns offline run imports, explicit links, trend aggregation, release gates, JSON/HTML reports, API routes, and CLI orchestration; it only reads existing sanitized telemetry/review/promotion rows and never reconstructs Trace text. Extend `RunReport` with optional release metadata while preserving all existing fields and constructors.

**Tech Stack:** Python 3.9+, dataclasses, sqlite3, FastAPI, argparse, JSON, HTML escaping, PyYAML-compatible existing scenario/telemetry validators, pytest.

**Spec:** `docs/superpowers/specs/2026-09-09-m17-quality-loop-design.md`

## Global Constraints

- Keep the Reference Agent separate from test assertions and quality-loop implementation.
- Do not change `AppResponse` or existing public report fields/constructor compatibility.
- Use temporary SQLite files and deterministic sanitized fixtures in tests and CI.
- Do not add FastGPT dependencies, adapters, deployment steps, tests, or CI jobs.
- Preserve the 30-day telemetry retention boundary and reject expired online records.
- Never persist or render raw request text, answer text, credentials, cookies, authorization headers, or telemetry tokens.
- M17 remains a `qe_platform` module and must not be moved into the `llmtest` pytest plugin.

---

### Task 1: Add release metadata and immutable M17 domain models

**Files:**
- Modify: `qe_platform/reporting/run_report.py`
- Modify: `qe_platform/reporting/__init__.py`
- Create: `qe_platform/quality_loop/__init__.py`
- Create: `qe_platform/quality_loop/models.py`
- Test: `tests/test_quality_loop_models.py`

**Interfaces:**
- `RunReport` gains optional `application`, `release_id`, `version`, and `environment` fields after the existing `scenarios` field; `as_dict()` includes them while old positional construction remains valid.
- Add frozen models `OfflineRun`, `QualityLink`, `TrendPoint`, `ReleaseGatePolicy`, `ReleaseCheck`, and `ReleaseValidation`, each with `as_dict()` and strict validation.
- `parse_run_report(payload: Mapping[str, Any], source_label: str) -> OfflineRun` validates a report payload without reading any source file.

- [ ] **Step 1: Write failing model and report metadata tests**

  Add tests proving a report round-trips metadata, old four-argument `RunReport` construction still works, invalid identifiers/timestamps/counts are rejected, and `ReleaseGatePolicy` rejects negative or non-numeric thresholds.

- [ ] **Step 2: Run the focused tests and confirm the expected missing-model failures**

  Run: `python -m pytest tests/test_quality_loop_models.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m17-task1-red`

  Expected: collection/import failures because `qe_platform.quality_loop` and the new parser do not yet exist.

- [ ] **Step 3: Implement the smallest models and backward-compatible report metadata**

  Keep validation deterministic, normalize UTC timestamps to `Z`, calculate failure/pass counts from the report, and store sorted scenario IDs as tuples internally.

- [ ] **Step 4: Run the focused tests and existing report tests**

  Run: `python -m pytest tests/test_quality_loop_models.py tests/test_run_reporting.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m17-task1-green`

  Expected: all focused tests pass.

- [ ] **Step 5: Commit**

  `git add qe_platform/reporting qe_platform/quality_loop tests/test_quality_loop_models.py && git commit -m "feat: add quality loop domain models"`

### Task 2: Persist offline runs, explicit links, and validations

**Files:**
- Create: `qe_platform/quality_loop/storage.py`
- Modify: `qe_platform/quality_loop/__init__.py`
- Test: `tests/test_quality_loop_storage.py`

**Interfaces:**
- `SQLiteQualityRepository(database: str | Path, retention_days: int = 30)` creates `quality_offline_runs`, `quality_links`, and `quality_release_validations` tables in the shared SQLite file.
- `import_run(report: Mapping[str, Any], source_label: str) -> OfflineRun` is idempotent by `run_id` and rejects sensitive payload keys/values.
- `get_run(run_id: str, *, now: datetime | None = None) -> OfflineRun | None` and `list_runs(...) -> list[OfflineRun]` apply input validation.
- `create_link(promotion_id: str, offline_run_id: str, *, now: datetime | None = None) -> QualityLink` validates the unexpired promotion/scenario and is idempotent.
- `list_links(...) -> list[QualityLink]`, `save_validation(value: ReleaseValidation) -> ReleaseValidation`, and `get_validation(validation_id: str) -> ReleaseValidation | None` provide bounded access.
- `online_rows(...)` returns only aggregate-safe columns needed by the engine; it never returns Trace payload text.

- [ ] **Step 1: Write failing storage tests**

  Use a temporary database and existing M16 fixture helpers to prove run import/idempotency, sensitive payload rejection, expired promotion rejection, scenario mismatch rejection, link idempotency, retention filtering, and validation persistence.

- [ ] **Step 2: Run storage tests and confirm they fail for missing repository**

  Run: `python -m pytest tests/test_quality_loop_storage.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m17-task2-red`

  Expected: import/attribute failures for `SQLiteQualityRepository`.

- [ ] **Step 3: Implement schema, transactions, retention joins, and hydration**

  Use `PRAGMA foreign_keys=ON`, `BEGIN IMMEDIATE`, deterministic JSON serialization, and foreign keys from links to promotions/runs. Keep offline runs and validations auditable when an online row expires by making link reads omit unavailable rows rather than reconstructing them.

- [ ] **Step 4: Run focused storage and telemetry regression tests**

  Run: `python -m pytest tests/test_quality_loop_storage.py tests/test_telemetry_storage.py tests/test_telemetry_review_storage.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m17-task2-green`

  Expected: all tests pass.

- [ ] **Step 5: Commit**

  `git add qe_platform/quality_loop tests/test_quality_loop_storage.py && git commit -m "feat: persist quality loop runs and links"`

### Task 3: Implement trend aggregation and release validation engine

**Files:**
- Create: `qe_platform/quality_loop/engine.py`
- Modify: `qe_platform/quality_loop/__init__.py`
- Test: `tests/test_quality_loop_engine.py`

**Interfaces:**
- `build_trends(repository: SQLiteQualityRepository, *, application: str = "", version: str = "", start: datetime | None = None, end: datetime | None = None) -> list[TrendPoint]` aggregates UTC day/application/version buckets from sanitized online rows and offline runs.
- `build_quality_links(repository, *, offline_run_id: str = "", promotion_id: str = "") -> list[QualityLink]` reads explicit links only.
- `validate_release(repository, baseline_run_id: str, candidate_run_id: str, policy: ReleaseGatePolicy, *, validation_id: str | None = None) -> ReleaseValidation` checks completeness, scenario set, candidate failure rate, pass-rate drop, and linked online low-quality-rate increase, then persists the result.
- `quality_summary(repository, validation_id: str) -> Mapping[str, Any]` returns a report-safe structure.

- [ ] **Step 1: Write failing engine tests**

  Build two fixture reports and one linked promoted scenario; assert exact daily counts/rates, P95 latency, tokens/cost, a passing validation, a failure-rate failure, a missing-scenario failure, and a low-quality-rate threshold failure.

- [ ] **Step 2: Run engine tests and verify missing implementation failures**

  Run: `python -m pytest tests/test_quality_loop_engine.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m17-task3-red`

  Expected: import/attribute failures for engine functions.

- [ ] **Step 3: Implement deterministic aggregation and structured checks**

  Use exact decimal-safe float handling for report values, percentile interpolation documented in code, zero/null semantics for empty denominators, and stable check ordering. Never infer links from matching names.

- [ ] **Step 4: Run engine and storage tests together**

  Run: `python -m pytest tests/test_quality_loop_models.py tests/test_quality_loop_storage.py tests/test_quality_loop_engine.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m17-task3-green`

  Expected: all tests pass.

- [ ] **Step 5: Commit**

  `git add qe_platform/quality_loop tests/test_quality_loop_engine.py && git commit -m "feat: add quality trends and release gates"`

### Task 4: Generate safe JSON/HTML evidence and CLI workflow

**Files:**
- Create: `qe_platform/quality_loop/reporting.py`
- Create: `qe_platform/quality_loop/cli.py`
- Modify: `pyproject.toml`
- Modify: `qe_platform/quality_loop/__init__.py`
- Test: `tests/test_quality_loop_cli.py`
- Test: `tests/test_quality_loop_reporting.py`

**Interfaces:**
- `write_quality_json(payload: Mapping[str, Any], path: str | Path) -> Path` and `write_quality_html(payload: Mapping[str, Any], path: str | Path) -> Path` emit deterministic, escaped artifacts.
- `quality-loop import-run --database DB --report REPORT.json --source-label LABEL` imports an offline report.
- `quality-loop link --database DB --promotion-id ID --offline-run-id ID` creates an explicit link.
- `quality-loop trends --database DB --json OUT --html OUT` writes trend/association evidence.
- `quality-loop validate-release --database DB --baseline ID --candidate ID --json OUT --html OUT [threshold flags]` writes evidence and returns 0/1/2 according to the spec.

- [ ] **Step 1: Write failing CLI/report tests**

  Assert JSON has only structured fields, HTML is self-contained and escapes `<script>`, CLI imports and links the fixture chain, and passing/failing validation returns the documented exit codes and artifacts.

- [ ] **Step 2: Run focused CLI/report tests and observe missing entry point failures**

  Run: `python -m pytest tests/test_quality_loop_cli.py tests/test_quality_loop_reporting.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m17-task4-red`

  Expected: import failures for reporting/CLI functions.

- [ ] **Step 3: Implement reporting and argparse commands**

  Read reports with UTF-8 JSON only, pass source labels instead of absolute paths, use HTML escaping for every dynamic cell, and preserve validation failures in the artifact before returning code 1.

- [ ] **Step 4: Run focused tests and `python -m pip install -e .` smoke**

  Run: `python -m pytest tests/test_quality_loop_cli.py tests/test_quality_loop_reporting.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m17-task4-green`; then `quality-loop --help`.

  Expected: tests pass and help lists all four subcommands.

- [ ] **Step 5: Commit**

  `git add qe_platform/quality_loop pyproject.toml tests/test_quality_loop_cli.py tests/test_quality_loop_reporting.py && git commit -m "feat: add quality loop evidence CLI"`

### Task 5: Add FastAPI quality routes and complete closed-loop contract

**Files:**
- Modify: `qe_platform/telemetry/api.py`
- Modify: `qe_platform/telemetry/__init__.py` if exports are needed
- Test: `tests/test_quality_loop_api.py`
- Test: `tests/test_quality_loop_contract.py`

**Interfaces:**
- Extend `create_telemetry_app(settings, repository=None, quality_repository=None)` without breaking existing callers.
- Add the six `/api/quality/...` routes defined in the spec. Write routes require the existing ingest token; validation failure responds 422 with the full `ReleaseValidation` JSON.
- Contract test constructs Trace -> Feedback -> Review -> Promotion, imports baseline/candidate runs, links a promoted scenario, fetches trends/links, and validates the candidate through both direct engine and API paths.

- [ ] **Step 1: Write failing API and end-to-end contract tests**

  Assert status codes for missing IDs, expired links, sensitive report payloads, passing validation, and failing validation. Assert no response body contains fixture request/answer text or credentials.

- [ ] **Step 2: Run API/contract tests and confirm routes are absent**

  Run: `python -m pytest tests/test_quality_loop_api.py tests/test_quality_loop_contract.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m17-task5-red`

  Expected: route 404/import failures.

- [ ] **Step 3: Implement route parsing and error mapping**

  Reuse existing token parsing and UTC/limit validation helpers; create a quality repository against `settings.database` when one is not supplied; map invalid input to 400, missing records to 404, gate failure to 422, and unexpected storage errors to 500.

- [ ] **Step 4: Run the API/contract tests and all prior M17 tests**

  Run: `python -m pytest tests/test_quality_loop_models.py tests/test_quality_loop_storage.py tests/test_quality_loop_engine.py tests/test_quality_loop_reporting.py tests/test_quality_loop_cli.py tests/test_quality_loop_api.py tests/test_quality_loop_contract.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m17-task5-green`

  Expected: all M17 tests pass.

- [ ] **Step 5: Commit**

  `git add qe_platform/telemetry/api.py qe_platform/quality_loop tests/test_quality_loop_api.py tests/test_quality_loop_contract.py && git commit -m "feat: expose quality loop API and contract"`

### Task 6: Document, add offline CI contract, and record local acceptance

**Files:**
- Create: `docs/趋势、线上离线关联与发布验证指南.md`
- Create: `docs/deployment/evidence/2026-09-09-m17-quality-loop.md`
- Modify: `README.md`
- Modify: `docs/AI应用全链路质量平台开发流程.md`
- Modify: `.github/workflows/loadtest.yml`
- Create: `tests/test_m17_docs.py`

**Interfaces:**
- Guide documents commands, policy defaults, API examples with placeholders, privacy/retention boundaries, and full fixture demonstration.
- CI adds a temporary-file-only M17 quality-loop contract command; it never uses real telemetry URLs, credentials, or committed data.
- Status table remains `进行中` until delivery lifecycle evidence exists, then is updated only in the closeout change set.

- [ ] **Step 1: Write failing docs/CI contract tests**

  Assert the guide links the CLI/API, excludes FastGPT, names M17 boundaries, and the workflow invokes only temporary offline fixtures.

- [ ] **Step 2: Run docs tests and verify the new guide/status assertions fail**

  Run: `python -m pytest tests/test_m17_docs.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m17-task6-red`

  Expected: missing guide/workflow assertions fail.

- [ ] **Step 3: Implement guide, CI contract, and in-progress evidence template**

  Include the baseline `406 passed, 4 deselected, 177 warnings` and the exact M17 focused command; do not claim PR, Release, deployment, or Issue completion yet.

- [ ] **Step 4: Run docs tests, focused M17 suite, compileall, Compose config, and diff check**

  Run: `python -m pytest tests/test_m17_docs.py tests/test_quality_loop_contract.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m17-task6-green`; `python -m compileall -q llmtest qe_platform reference_agent tests`; `docker compose config --quiet`; `git diff --check`.

  Expected: all commands exit 0.

- [ ] **Step 5: Commit**

  `git add docs README.md .github/workflows/loadtest.yml tests/test_m17_docs.py && git commit -m "docs: add milestone 17 quality loop guide"`

### Task 7: Delivery lifecycle and closeout

**Files:**
- Modify: `docs/deployment/evidence/2026-09-09-m17-quality-loop.md`
- Modify: `docs/AI应用全链路质量平台开发流程.md`

- [ ] **Step 1: Run the complete local suite and UI suite on the feature branch**

  Record exact results for default pytest, `pytest -m ui`, compileall, Compose config, and diff check.

- [ ] **Step 2: Push branch and create PR for Issue #58**

  Use the proxy-bypass Git commands; PR body must link Issue #58, scope, privacy boundary, tests, and M17 evidence.

- [ ] **Step 3: Wait for and inspect every GitHub Actions check and independent review**

  Do not merge while any check is pending/failed or any Critical/Important/Minor review item remains unresolved.

- [ ] **Step 4: Merge to master and verify merged master**

  Fast-forward the root master worktree; rerun the relevant M17 suite, complete suite, UI suite, compileall, Compose config, and diff check.

- [ ] **Step 5: Create prerelease, deploy the exact merged revision, and run smoke/integrity checks**

  Build the revision-tagged local image, wait for `healthy`, run `deploy/smoke.ps1`, and run SQLite `PRAGMA integrity_check`; capture exact revision and outputs in evidence.

- [ ] **Step 6: Close Issue #58 and update the status row in the same closeout change**

  Create a separate closeout branch/PR if needed, record PR/Actions/review/merge/Release/deployment/Issue evidence, mark M17 completed only after all checks are verified, and keep future limitations explicit.

- [ ] **Step 7: Final verification and cleanup**

  Confirm master is clean, Release target is the implementation merge commit, Issue #58 is closed, evidence links are valid, and no FastGPT change exists.
