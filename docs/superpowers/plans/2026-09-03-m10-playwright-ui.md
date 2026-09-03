# Milestone 10 Playwright UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a runnable Reference Agent web UI and independent Playwright acceptance tests for the required user workflows.

**Architecture:** FastAPI serves zero-build static assets and adds demo login, session lookup, and SSE chat endpoints while preserving `/api/chat`. Playwright page objects and UI tests live outside the Agent implementation and reuse existing YAML scenario assets.

**Tech Stack:** FastAPI, Starlette static files, vanilla HTML/CSS/JavaScript, pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-03-m10-playwright-ui-design.md`

## Global Constraints

- Preserve existing `AppResponse` and `ResponseEnvelope` fields and `/api/chat` behavior.
- Keep test assertions outside `reference_agent`.
- Do not add FastGPT capability or production credentials.
- UI tests are a separate execution mode and are marked `ui`.

### Task 1: Backend UI Contracts

**Files:**
- Modify: `reference_agent/app.py`
- Create: `tests/test_reference_agent_ui_api.py`

- [ ] Write failing tests for `/`, demo login, session lookup, SSE completion envelope, and stable upstream error event.
- [ ] Run `pytest tests/test_reference_agent_ui_api.py -q` and confirm missing routes fail.
- [ ] Implement the routes with existing graph invocation and `StreamingResponse` SSE events.
- [ ] Run the focused tests and then the existing Reference Agent tests.
- [ ] Commit `feat: add reference agent ui api contracts`.

### Task 2: Static Web UI

**Files:**
- Create: `reference_agent/web/index.html`
- Create: `reference_agent/web/app.js`
- Create: `reference_agent/web/styles.css`
- Modify: `reference_agent/app.py`
- Create: `tests/test_reference_agent_web_assets.py`

- [ ] Write failing tests for served HTML, required controls, and JavaScript endpoint usage.
- [ ] Run the focused tests and confirm assets are absent.
- [ ] Implement accessible login/session/chat/status layout and SSE rendering.
- [ ] Run asset tests and backend regression tests.
- [ ] Commit `feat: add reference agent web ui`.

### Task 3: Playwright Test Layer

**Files:**
- Modify: `pyproject.toml`
- Create: `qe_platform/browser/__init__.py`
- Create: `qe_platform/browser/pages.py`
- Create: `qe_platform/browser/scenarios.py`
- Create: `tests/ui/conftest.py`
- Create: `tests/ui/test_reference_agent_ui.py`

- [ ] Write UI tests marked `ui` for login/session, knowledge streaming, ticket result, error message, and handoff.
- [ ] Run collection without the optional dependency and confirm a clear skip/error policy.
- [ ] Add optional `ui` dependency and page objects with base URL/configurable server fixture.
- [ ] Install Playwright browser and run `pytest -m ui`; keep tests excluded from default suite.
- [ ] Commit `test: add playwright reference agent acceptance layer`.

### Task 4: CI, Documentation, and Status Evidence

**Files:**
- Modify: `.github/workflows/ui.yml`
- Modify: `docs/AI应用全链路质量平台开发流程.md`
- Modify: `README.md`
- Create: `docs/superpowers/plans/2026-09-03-m10-playwright-ui-closeout.md`

- [ ] Add a CI job that installs the UI extra, browser binaries, starts the app, and uploads Playwright artifacts.
- [ ] Document local UI execution and its demo-only authentication boundary.
- [ ] Run UI, API, and full regression commands; record exact results and remaining gaps in the status table.
- [ ] Inspect diff, run `git diff --check`, and commit `docs: record milestone 10 evidence`.
