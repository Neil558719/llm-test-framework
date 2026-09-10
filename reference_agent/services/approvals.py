"""软件权限审批 Mock 服务。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol

from .common import FailureConfig, MockServiceBase


class ApprovalRepository(Protocol):
    def create_approval(self, user_id: str, software: str, justification: str, idempotency_key: str | None) -> dict[str, Any]: ...
    def get_approval(self, approval_id: str) -> dict[str, Any] | None: ...


class ApprovalService(MockServiceBase):
    def __init__(self, failure: FailureConfig | None = None, *, repository: ApprovalRepository | None = None) -> None:
        super().__init__(failure)
        self._repository = repository
        self._approvals: dict[str, dict[str, Any]] = {}
        self._idempotency: dict[str, str] = {}
        self._next_id = 1

    def create_approval(
        self,
        user_id: str,
        software: str,
        justification: str = "",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        self._before_call()
        if self._repository is not None:
            return self._repository.create_approval(user_id, software, justification, idempotency_key)
        if idempotency_key and idempotency_key in self._idempotency:
            return deepcopy(self._approvals[self._idempotency[idempotency_key]])

        approval_id = f"A-{self._next_id:04d}"
        self._next_id += 1
        approval = {
            "approval_id": approval_id,
            "user_id": user_id,
            "software": software,
            "justification": justification,
            "status": "pending",
        }
        self._approvals[approval_id] = approval
        if idempotency_key:
            self._idempotency[idempotency_key] = approval_id
        return deepcopy(approval)

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        self._before_call()
        if self._repository is not None:
            return self._repository.get_approval(approval_id)
        approval = self._approvals.get(approval_id)
        return deepcopy(approval) if approval is not None else None
