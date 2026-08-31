# Milestone 3 Mock Services Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build deterministic, offline Mock user, asset, ticket, approval, and knowledge-base services for the reference IT service desk Agent.

**Architecture:** Each service is a small in-memory class with explicit records, typed result/error behavior, and injectable latency/failure configuration. Ticket and approval writes accept idempotency keys and preserve state for later business assertions. Services are independent of the Agent and are composed only by future milestones.

**Tech Stack:** Python 3.9+, dataclasses, `time.sleep`, pytest.

**Spec:** `docs/AI应用全链路质量平台开发流程.md`, sections 5, 6, and milestone 3 in section 7.

## Global Constraints

- Keep the test platform and reference Agent separated; services must not contain test assertions.
- Keep execution offline and deterministic; no network, API keys, or production data.
- Use TDD: each behavior gets a failing test before implementation.
- FastGPT remains out of scope.
- Preserve existing public APIs and all existing tests.

### Task 1: Shared Mock Controls and User/Asset Services

**Files:**
- Create: `reference_agent/services/__init__.py`
- Create: `reference_agent/services/common.py`
- Create: `reference_agent/services/users.py`
- Create: `reference_agent/services/assets.py`
- Test: `tests/test_mock_services.py`

**Interfaces:**
- `FailureConfig(status_code: int | None = None, message: str = "", delay_seconds: float = 0.0)`
- `ServiceError.status_code`, `.message`
- `UserService.get_user(user_id: str) -> dict | None`
- `AssetService.get_asset(asset_id: str) -> dict | None`
- Every service constructor accepts `records: dict | None = None, failure: FailureConfig | None = None`.

- [ ] **Step 1: Write failing tests** for known user/asset lookup, empty lookup, configured 503, and measurable delay.
- [ ] **Step 2: Run** `pytest tests/test_mock_services.py -q`; expected failure because modules do not exist.
- [ ] **Step 3: Implement** shared failure/delay handling and the two lookup services with safe copies of records.
- [ ] **Step 4: Run** `pytest tests/test_mock_services.py -q`; expected all Task 1 tests pass.
- [ ] **Step 5: Commit** `git add reference_agent/services tests/test_mock_services.py && git commit -m "feat: add mock user and asset services"`.

### Task 2: Ticket Service

**Files:**
- Create: `reference_agent/services/tickets.py`
- Modify: `reference_agent/services/__init__.py`
- Test: `tests/test_mock_services.py`

**Interfaces:**
- `TicketService.create_ticket(user_id: str, asset_id: str, category: str, priority: str, idempotency_key: str | None = None) -> dict`
- `TicketService.get_ticket(ticket_id: str) -> dict | None`
- `TicketService.list_tickets(user_id: str | None = None) -> list[dict]`
- New tickets contain `ticket_id`, `user_id`, `asset_id`, `category`, `priority`, and `status="created"`.

- [ ] **Step 1: Add failing tests** for creation, retrieval, configured 5xx, and repeated idempotency key returning the same ticket.
- [ ] **Step 2: Run** `pytest tests/test_mock_services.py -q`; expected new failures.
- [ ] **Step 3: Implement** deterministic ticket IDs, state storage, safe copies, and idempotency index.
- [ ] **Step 4: Run** `pytest tests/test_mock_services.py -q`; expected all ticket tests pass.
- [ ] **Step 5: Commit** `git add reference_agent/services tests/test_mock_services.py && git commit -m "feat: add idempotent mock ticket service"`.

### Task 3: Approval Service

**Files:**
- Create: `reference_agent/services/approvals.py`
- Modify: `reference_agent/services/__init__.py`
- Test: `tests/test_mock_services.py`

**Interfaces:**
- `ApprovalService.create_approval(user_id: str, software: str, justification: str = "", idempotency_key: str | None = None) -> dict`
- `ApprovalService.get_approval(approval_id: str) -> dict | None`
- New approvals contain `approval_id`, `user_id`, `software`, `justification`, and `status="pending"`.

- [ ] **Step 1: Add failing tests** for pending approval, retrieval, configured 403/5xx, and idempotent repeat.
- [ ] **Step 2: Run** `pytest tests/test_mock_services.py -q`; expected new failures.
- [ ] **Step 3: Implement** deterministic approval IDs, state storage, failure handling, and idempotency index.
- [ ] **Step 4: Run** `pytest tests/test_mock_services.py -q`; expected all approval tests pass.
- [ ] **Step 5: Commit** `git add reference_agent/services tests/test_mock_services.py && git commit -m "feat: add idempotent mock approval service"`.

### Task 4: Knowledge Base Service and Public Exports

**Files:**
- Create: `reference_agent/services/knowledge_base.py`
- Modify: `reference_agent/services/__init__.py`
- Test: `tests/test_mock_services.py`

**Interfaces:**
- `KnowledgeBase.search(query: str, limit: int = 5) -> list[dict]`
- Each result contains `document_id`, `title`, `content`, and `score`.
- Empty/blank queries return `[]`; configured failures raise `ServiceError`.

- [ ] **Step 1: Add failing tests** for ranked search, limit, empty result, and configured timeout/5xx.
- [ ] **Step 2: Run** `pytest tests/test_mock_services.py -q`; expected new failures.
- [ ] **Step 3: Implement** deterministic token-overlap ranking with stable tie ordering and safe copies.
- [ ] **Step 4: Run** `pytest tests/test_mock_services.py -q`; expected all service tests pass.
- [ ] **Step 5: Commit** `git add reference_agent/services tests/test_mock_services.py && git commit -m "feat: add mock knowledge base service"`.

### Task 5: Regression, Documentation Evidence, and Acceptance

**Files:**
- Modify: `docs/AI应用全链路质量平台开发流程.md`
- Test: `tests/test_mock_services.py`, full suite

- [ ] **Step 1: Run focused suite** `pytest tests/test_mock_services.py -q` and record result.
- [ ] **Step 2: Run full suite** `pytest -q` and confirm no new failures.
- [ ] **Step 3: Update** milestone 3 status with files, commands, result, and remaining work; do not mark later milestones complete.
- [ ] **Step 4: Run** `git diff --check` and inspect the complete diff for secrets, external calls, and API regressions.
- [ ] **Step 5: Commit** `git add docs/AI应用全链路质量平台开发流程.md && git commit -m "docs: record milestone 3 mock service evidence"`.

