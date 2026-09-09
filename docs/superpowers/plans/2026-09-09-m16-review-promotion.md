# M16 Human Review and Regression Promotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add structured human review and privacy-safe promotion of reviewed feedback into executable YAML regression scenarios.

**Architecture:** Extend the M15 feedback/storage boundary with review and promotion records. Validate an explicitly supplied sanitized scenario draft with the existing scenario schema and loader, serialize it as safe YAML, and expose API operations that remain separate from Trace ingestion. Reuse the existing workflow runner for offline execution evidence.

**Tech Stack:** Python 3.9+, FastAPI/TestClient, sqlite3, PyYAML, jsonschema, pytest.

**Spec:** `docs/superpowers/specs/2026-09-09-m16-review-promotion-design.md`

## Global Constraints

- Preserve `AppResponse`, M15 telemetry payloads, existing YAML DSL, and existing workflow-runner behavior.
- Never derive a scenario from Trace plaintext; promotion requires an explicit sanitized scenario draft.
- Reject raw request/response, authorization, token, API key, secret, and free-text review fields.
- Only confirmed non-`correct` feedback can be promoted; one review and one promotion per feedback/review.
- Keep SQLite as the implementation and PostgreSQL as a not-enabled boundary; do not add FastGPT capability.
- M17 trends, online/offline comparison, and release gates remain out of scope.

### Task 1: Review and promotion domain contracts

**Files:**
- Create: `qe_platform/feedback/review.py`
- Modify: `qe_platform/feedback/__init__.py`
- Test: `tests/test_feedback_review_models.py`

**Interfaces:** Define `ReviewStatus`, `ReviewAttribution`, `ReviewPriority`, `FeedbackReview`, `PromotionRecord`, and validated request helpers. IDs and reviewer identity are nonempty; reviewer identity is stored only as a SHA-256 HMAC fingerprint; timestamps are UTC; serialized values contain no free text.

- [ ] Write failing tests for all enum values, invalid values, UTC validation, fingerprinting, and safe dictionaries.
- [ ] Run `python -m pytest tests/test_feedback_review_models.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m16-t1-red` and verify red.
- [ ] Implement the smallest immutable dataclasses and request validators using M15 `fingerprint`.
- [ ] Run the focused test again and verify green.
- [ ] Commit `feat: add structured feedback review contracts`.

### Task 2: SQLite review and promotion persistence

**Files:**
- Modify: `qe_platform/storage/telemetry.py`, `qe_platform/storage/__init__.py`
- Test: `tests/test_telemetry_review_storage.py`

**Interfaces:** Extend `TelemetryRepository` with review query/create and promotion create/get methods. Add `telemetry_reviews` and `telemetry_promotions` with foreign keys, unique constraints, cascade deletion, retention filtering, and transactions under the existing repository lock.

- [ ] Add failing tests for review creation, update/idempotency, missing feedback, list filters, promotion uniqueness, cascade deletion, expiry, and concurrent writes.
- [ ] Run the focused storage tests and verify red.
- [ ] Implement parameterized schema, hydration, and repository methods without changing M15 trace/feedback behavior.
- [ ] Run M15 storage tests plus the new tests and verify green.
- [ ] Commit `feat: persist feedback reviews and promotions`.

### Task 3: Scenario promotion service

**Files:**
- Create: `qe_platform/feedback/promotion.py`
- Modify: `qe_platform/feedback/__init__.py`
- Test: `tests/test_feedback_promotion.py`

**Interfaces:** Provide `promote_review(review, feedback, scenario_payload) -> PromotionRecord` and `scenario_yaml(payload, source=...)`. Require a confirmed non-`correct` review, validate through `load_scenario_text`, reject forbidden sensitive fields/values, use `yaml.safe_dump`, and verify YAML round-trip. Preserve `scenario_id` and source metadata without injecting secrets.

- [ ] Write failing tests for valid round-trip, rejected `correct` feedback, invalid DSL, sensitive fields/values, deterministic safe YAML, and runner compatibility.
- [ ] Run focused promotion tests and verify red.
- [ ] Implement validation and serialization using existing scenario loader/schema.
- [ ] Run focused tests and an offline `ScenarioRunner` smoke with a stub adapter; verify green.
- [ ] Commit `feat: validate and serialize promoted regression scenarios`.

### Task 4: Review and promotion API

**Files:**
- Modify: `qe_platform/telemetry/api.py`
- Test: `tests/test_telemetry_review_api.py`

**Interfaces:** Add `POST /api/feedback/{feedback_id}/review`, `GET /api/reviews`, `GET /api/reviews/{review_id}`, `POST /api/reviews/{review_id}/promote`, and `GET /api/promotions/{promotion_id}`. Return 201 for first writes, 200 for idempotent repeats, 400 for invalid payloads, 404 for missing/expired records, and generic 500 without sensitive detail for storage errors.

- [ ] Write failing TestClient tests for the full feedback -> review -> promotion path, filters, idempotency, low-quality restriction, malformed/sensitive payloads, and safe response fields.
- [ ] Run API tests and verify red.
- [ ] Implement strict payload parsing and map repository/domain errors to safe HTTP responses.
- [ ] Run new API tests plus all M15 telemetry API tests and verify green.
- [ ] Commit `feat: expose review and regression promotion API`.

### Task 5: Documentation, CI contract, status and evidence

**Files:**
- Create: `tests/test_m16_docs.py`, `docs/人工复核与回归晋级指南.md`
- Modify: `README.md`, `.github/workflows/loadtest.yml`, `docs/AI应用全链路质量平台开发流程.md`

**Interfaces:** Document structured review fields, sanitized scenario input, API examples with placeholders, offline execution command and M17 boundary. Add a temporary-file-only M16 contract job. Record branch evidence and keep M17 not started until M16 closes.

- [ ] Write failing documentation/workflow tests.
- [ ] Run the docs tests and verify red.
- [ ] Add guide, CI contract, and progress-row evidence without real credentials or raw Trace data.
- [ ] Run M16 focused tests, M15 regression, default full regression, compileall, Compose config, and diff check.
- [ ] Commit `docs: record milestone 16 review promotion acceptance`.

### Task 6: Review, merge, release and local deployment

**Files:**
- Create/modify: `docs/deployment/evidence/2026-09-09-m16-review-promotion.md`, status table as needed.

- [ ] Independently inspect the branch diff and reproduce every accepted review finding with a failing test before fixing it.
- [ ] Push `codex/m16-review-promotion`, open PR linked to Issue #55, and wait for all Actions checks.
- [ ] Merge only after checks and independent review are clean; fast-forward local `master` and rerun merged-master tests.
- [ ] Publish the next pre-release, build/deploy the exact merge revision locally, run smoke, verify health and SQLite integrity.
- [ ] Record only verified lifecycle evidence, close Issue #55, and keep M17 status as not started.
