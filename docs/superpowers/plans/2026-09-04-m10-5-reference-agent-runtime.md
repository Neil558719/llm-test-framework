# Milestone 10.5 Reference Agent Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the reusable `llmtest` model client to the Reference Agent intent, parameter, and answer path with controlled Mock/DeepSeek switching.

**Architecture:** Add a provider/profile registry and `AgentRuntime` boundary under `reference_agent/runtime/`. The runtime asks an injected `LLMClient` for structured intent and parameters, delegates all business decisions and tool execution to the existing graph, and optionally generates the final wording. FastAPI owns the active profile; the browser selects only server-approved profiles and never receives a secret.

**Tech Stack:** Python, FastAPI, LangGraph, llmtest LLMClient, vanilla JavaScript, pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-04-m10-5-reference-agent-runtime-design.md`

## Global Constraints

- Default execution is offline Mock.
- The only built-in real provider in 10.5 is official DeepSeek at `https://api.deepseek.com`.
- Provider implementations are registered behind a factory interface; graph and UI code contain no provider-specific branching.
- API keys are server-side only and are never accepted, returned, logged, or persisted by UI APIs.
- Deterministic code retains authority over identity, asset ownership, tool execution, idempotency, and handoff decisions.
- Existing `/api/chat`, `/api/chat/stream`, `AppResponse`, `ResponseEnvelope`, V1 scenarios, and default CI remain compatible.
- Current delivery acceptance is the local production-like Docker Compose drill; no independent cloud server is planned in this phase.
- Container configuration, persistent volume, environment injection, backup/restore, smoke scripts, and migration/rollback docs must remain portable to a future independent cloud server.

---

### Task 1: Configuration and Provider Registry

**Files:**
- Create: `reference_agent/runtime/config.py`
- Create: `reference_agent/runtime/providers.py`
- Create: `reference_agent/runtime/__init__.py`
- Test: `tests/test_reference_agent_runtime_config.py`

**Interfaces:**
- Produces: `AgentModelConfig.from_env()`, `ModelProfile`, `ModelProviderRegistry.register()`, `resolve()`, and `create_client()`.

- [ ] Write failing tests for Mock defaults, DeepSeek environment mapping, unknown profile rejection, secret-safe serialization, and registering a synthetic provider.
- [ ] Run `python -m pytest tests/test_reference_agent_runtime_config.py -q` and confirm failure because runtime modules do not exist.
- [ ] Implement immutable configuration and a registry seeded with `mock` and `deepseek-official` profiles.
- [ ] Run the focused tests and confirm they pass.
- [ ] Commit configuration and registry behavior.

### Task 2: Structured Runtime Orchestration

**Files:**
- Create: `reference_agent/runtime/models.py`
- Create: `reference_agent/runtime/prompts.py`
- Create: `reference_agent/runtime/agent.py`
- Modify: `reference_agent/graph.py`
- Test: `tests/test_reference_agent_runtime.py`

**Interfaces:**
- Consumes: `LLMClient.complete(messages, temperature=0, max_tokens=N)` and existing graph services.
- Produces: `AgentRuntime.invoke(state) -> dict` with intent, parameter, generation, fallback, usage, and latency metadata.

- [ ] Write failing Fake-client tests for model classification, extracted ticket/access fields, prompt order, generated answers, trace propagation, and malformed/timeout fallback.
- [ ] Run focused tests and confirm missing behavior failures.
- [ ] Implement strict structured-output parsing and normalized state fields.
- [ ] Extend graph routing/extraction to accept validated runtime hints while retaining all deterministic business checks.
- [ ] Generate final wording only after graph completion; preserve deterministic answer on failure.
- [ ] Run focused and existing knowledge/ticket/access tests.
- [ ] Commit runtime orchestration.

### Task 3: FastAPI Profile Control and Envelope Metadata

**Files:**
- Modify: `reference_agent/app.py`
- Modify: `reference_agent/deployment.py`
- Test: `tests/test_reference_agent_model_api.py`
- Test: `tests/test_reference_agent_ui_api.py`

**Interfaces:**
- Produces: `GET /api/model-profiles`, `PUT /api/model-profile`, and runtime-backed chat endpoints.

- [ ] Write failing tests for the two exposed profiles, safe current configuration, DeepSeek activation, missing server key diagnostics, invalid profile rejection, and envelope metadata.
- [ ] Run focused tests and confirm endpoint failures.
- [ ] Inject the registry/runtime into the app and implement the allowlisted profile endpoints without an API-key request field.
- [ ] Route both chat endpoints through the same active runtime and preserve response fields.
- [ ] Run API, adapter, scenario, and V1 gate regressions.
- [ ] Commit API integration.

### Task 4: Browser Profile Switching

**Files:**
- Modify: `reference_agent/web/index.html`
- Modify: `reference_agent/web/app.js`
- Modify: `reference_agent/web/styles.css`
- Modify: `tests/ui/test_reference_agent_ui.py`
- Modify: `tests/test_reference_agent_web_assets.py`

**Interfaces:**
- Consumes: model-profile endpoints.
- Produces: accessible Mock/DeepSeek selector, model/base URL fields, and mode/generation status display.

- [ ] Write failing static and Playwright tests for loading profiles, switching profile, no API-key control, and visible model/generation status.
- [ ] Run static tests and UI tests to confirm failures.
- [ ] Implement the compact profile controls and safe update flow.
- [ ] Run focused UI tests at desktop and mobile viewports.
- [ ] Commit UI switching.

### Task 5: Deployment, Documentation, and Acceptance

**Files:**
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Modify: `docs/AI应用全链路质量平台开发流程.md`
- Modify: relevant deployment tests and CI configuration if required.

**Interfaces:**
- Produces: documented offline/real commands and auditable milestone evidence.

- [ ] Add failing deployment configuration tests for the `REFERENCE_AGENT_MODEL_*` contract and absence of real secrets.
- [ ] Update Compose and documentation with DeepSeek official configuration and provider extension guidance.
- [ ] Run focused runtime/API/UI tests, `python -m pytest -q`, V1 API gate, compileall, compose validation, and `git diff --check`.
- [ ] Inspect the complete branch diff for protocol, security, and regression risks.
- [ ] Record exact commands/results in the status table and commit the evidence.
- [ ] Push the branch, open a PR, wait for Actions, perform review, merge to `master`, publish a release, and update deployment/issue tracking before declaring 10.5 complete.
 - [ ] Run the local production-like Docker Compose drill, including image build, health check, API/UI smoke, model configuration injection, SQLite persistence, and backup/restore evidence.
 - [ ] Push the branch, open a PR, wait for Actions, perform review, merge to `master`, publish a release, and update local deployment evidence before declaring 10.5 complete. Independent cloud deployment is future work, not a release blocker for this milestone.
