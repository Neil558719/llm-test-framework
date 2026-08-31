# Milestone 6 Access Request and Handoff Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add deterministic software access requests, missing-information prompts, restricted-software handling, human handoff, and approval idempotency to the reference Agent.

**Architecture:** Extend the existing response node with an access intent branch before knowledge search. The branch extracts software and justification, validates the user, rejects configured restricted software with a handoff state, or creates an approval through `ApprovalService` using a stable session/user/software key. Tool calls remain observable through `ResponseEnvelope`.

**Tech Stack:** FastAPI, LangGraph, existing Mock services and `ResponseEnvelope`, pytest.

**Spec:** `docs/AI应用全链路质量平台开发流程.md`, sections 5-7.

## Global Constraints

- Keep Agent and test platform separated.
- Keep behavior offline and deterministic; no external LLM calls.
- Preserve existing knowledge and ticket flows.
- Use TDD; FastGPT remains out of scope.

### Task 1: Access Graph Flow

**Files:**
- Modify: `reference_agent/graph.py`
- Test: `tests/test_reference_agent_access.py`

**Interfaces:**
- `build_graph(..., approval_service=None)` accepts `ApprovalService` injection.
- State adds `approval_status` and `handoff_reason`.
- Access intent recognizes `申请权限`, `申请安装`, `安装软件`, and `访问权限`.

- [ ] Write failing tests for normal approval, missing software/reason, restricted software, and user failure.
- [ ] Run focused tests and confirm failure.
- [ ] Implement extraction, validation, restricted policy, and approval ToolCalls.
- [ ] Run focused tests and confirm pass.
- [ ] Commit `feat: add access approval graph flow`.

### Task 2: Chat API Integration and Idempotency

**Files:**
- Modify: `reference_agent/app.py`
- Modify: `reference_agent/graph.py`
- Test: `tests/test_reference_agent_access.py`

**Interfaces:**
- `create_app(..., approval_service=None)` injects the ApprovalService.
- `/api/chat` returns `approval_status`, `handoff_reason`, `tool_calls`, and `metadata.approval_status`.
- Repeating the same session/software request reuses the same approval.

- [ ] Add failing API tests for normal request, repeated request, handoff, and approval 5xx.
- [ ] Run focused tests and confirm failure.
- [ ] Wire request context and response metadata without leaking exceptions.
- [ ] Run focused tests and confirm pass.
- [ ] Commit `feat: expose access flow through chat api`.

### Task 3: Regression and Acceptance Evidence

**Files:**
- Modify: `docs/AI应用全链路质量平台开发流程.md`
- Test: `tests/test_reference_agent_access.py`, full suite

- [ ] Run focused and full pytest suites.
- [ ] Update milestone 6 evidence; leave milestones 7-17 unstarted.
- [ ] Run `git diff --check` and inspect for secrets/external calls/regressions.
- [ ] Commit `docs: record milestone 6 access flow evidence`.

