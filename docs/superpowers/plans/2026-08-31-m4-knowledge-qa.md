# Milestone 4 IT Knowledge QA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Connect the deterministic KnowledgeBase Mock to the reference Agent and expose citation-backed IT knowledge answers with safe refusal and failure handling.

**Architecture:** Extend the LangGraph state with a knowledge-query node that searches `KnowledgeBase`, formats deterministic answers from matched records, and returns source identifiers through `ResponseEnvelope.sources`. The chat API owns service dependencies in `app.state`; no assertions or test-only logic enter the Agent.

**Tech Stack:** FastAPI, LangGraph, existing `KnowledgeBase`, `ResponseEnvelope`, pytest.

**Spec:** `docs/AI应用全链路质量平台开发流程.md`, sections 5-7.

## Global Constraints

- Keep the Agent and test platform separated.
- Keep behavior offline and deterministic; do not call external LLMs.
- Preserve existing `/api/health`, `/api/chat`, and envelope fields.
- Use TDD for every behavior and keep FastGPT out of scope.

### Task 1: Knowledge Answering Graph Behavior

**Files:**
- Modify: `reference_agent/graph.py`
- Test: `tests/test_reference_agent_knowledge.py`

**Interfaces:**
- `build_graph(knowledge_base: KnowledgeBase | None = None)` returns a compiled graph.
- State includes `message`, `answer`, `sources`, and optional `error`.
- Matched answer format: `根据《<title>》：<content>`; no match: `抱歉，知识库中没有找到相关信息，我无法可靠回答。`

- [ ] Write failing tests for matched answer/sources, refusal, and KnowledgeBase `ServiceError` mapping.
- [ ] Run `pytest tests/test_reference_agent_knowledge.py -q` and confirm failure.
- [ ] Implement the smallest graph node using the existing KnowledgeBase.
- [ ] Run focused tests and confirm pass.
- [ ] Commit `feat: add knowledge answering graph`.

### Task 2: Chat API Integration

**Files:**
- Modify: `reference_agent/app.py`
- Modify: `reference_agent/graph.py`
- Test: `tests/test_reference_agent_knowledge.py`

**Interfaces:**
- `create_app(database: str = "reference_agent.db", knowledge_base: KnowledgeBase | None = None)`.
- `/api/chat` returns `sources` and `metadata.knowledge_status` (`answered`, `refused`, or `unavailable`).
- KnowledgeBase failures return HTTP 200 with a safe answer and `knowledge_status="unavailable"`; transport errors are not leaked.

- [ ] Add failing API tests for hit, refusal, and 504/5xx response.
- [ ] Run focused tests and confirm failure.
- [ ] Wire one KnowledgeBase instance into app state and envelope creation.
- [ ] Run focused tests and confirm pass.
- [ ] Commit `feat: expose knowledge qa through chat api`.

### Task 3: Regression and Documentation

**Files:**
- Modify: `docs/AI应用全链路质量平台开发流程.md`
- Test: `tests/test_reference_agent_knowledge.py`, full suite

- [ ] Run focused and full pytest suites.
- [ ] Update milestone 4 status with exact evidence; leave milestones 5-17 unstarted.
- [ ] Run `git diff --check` and inspect for external calls/secrets.
- [ ] Commit `docs: record milestone 4 knowledge qa evidence`.

