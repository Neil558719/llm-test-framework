# Milestone 5 Ticket Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a deterministic IT incident ticket flow to the reference Agent with user/asset validation, tool-call telemetry, idempotency, and safe recovery.

**Architecture:** Extend the LangGraph response node to classify ticket intents before knowledge search. Ticket handling validates the user and asset owner, creates a ticket with a session-derived idempotency key, and records each deterministic service call as a `ToolCall`. Knowledge questions retain their current path.

**Tech Stack:** FastAPI, LangGraph, existing Mock services and `ResponseEnvelope`, pytest.

**Spec:** `docs/AI应用全链路质量平台开发流程.md`, sections 5-7.

## Global Constraints

- Agent and test platform remain separate.
- Behavior is offline and deterministic; no external LLM calls.
- Preserve existing health/chat and knowledge QA behavior.
- Use TDD for every behavior; FastGPT remains out of scope.

### Task 1: Ticket Intent and Graph Flow

**Files:**
- Modify: `reference_agent/graph.py`
- Test: `tests/test_reference_agent_ticket.py`

**Interfaces:**
- `build_graph(knowledge_base=None, user_service=None, asset_service=None, ticket_service=None)`.
- State adds `user_id`, `session_id`, `tool_calls`, and `ticket_status`.
- Ticket intent recognizes messages containing `故障`, `报修`, `无法连接`, or `创建工单`.

- [ ] Write failing graph tests for happy path, missing user/asset, ownership mismatch, and tool order.
- [ ] Run focused tests and confirm failure against current knowledge-only graph.
- [ ] Implement validation and ticket creation nodes with `ToolCall` records.
- [ ] Run focused tests and confirm pass.
- [ ] Commit `feat: add deterministic ticket graph flow`.

### Task 2: Chat API and Idempotency

**Files:**
- Modify: `reference_agent/app.py`
- Modify: `reference_agent/graph.py`
- Test: `tests/test_reference_agent_ticket.py`

**Interfaces:**
- `create_app(database="reference_agent.db", knowledge_base=None, user_service=None, asset_service=None, ticket_service=None)`.
- `/api/chat` passes request user/session context and returns `tool_calls`, `ticket_status`, and `metadata.ticket_status`.
- Repeating the same session request reuses the same ticket via idempotency key.

- [ ] Add failing API tests for created ticket, repeated request, and TicketService 5xx.
- [ ] Run focused tests and confirm failure.
- [ ] Wire service dependencies and stable session-derived idempotency key into graph invocation.
- [ ] Run focused tests and confirm pass.
- [ ] Commit `feat: expose ticket flow through chat api`.

### Task 3: Regression and Acceptance Evidence

**Files:**
- Modify: `docs/AI应用全链路质量平台开发流程.md`
- Test: `tests/test_reference_agent_ticket.py`, full suite

- [ ] Run focused ticket tests and full pytest suite.
- [ ] Update milestone 5 status with exact evidence; leave milestones 6-17 unstarted.
- [ ] Run `git diff --check` and inspect for secrets, external calls, and regressions.
- [ ] Commit `docs: record milestone 5 ticket flow evidence`.

