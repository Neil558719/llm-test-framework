"""故障工单 Mock 服务。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol

from .common import FailureConfig, MockServiceBase


class TicketRepository(Protocol):
    def create_ticket(self, user_id: str, asset_id: str, category: str, priority: str, idempotency_key: str | None) -> dict[str, Any]: ...
    def get_ticket(self, ticket_id: str) -> dict[str, Any] | None: ...
    def list_tickets(self, user_id: str | None = None) -> list[dict[str, Any]]: ...


class TicketService(MockServiceBase):
    def __init__(self, failure: FailureConfig | None = None, *, repository: TicketRepository | None = None) -> None:
        super().__init__(failure)
        self._repository = repository
        self._tickets: dict[str, dict[str, Any]] = {}
        self._idempotency: dict[str, str] = {}
        self._next_id = 1

    def create_ticket(
        self,
        user_id: str,
        asset_id: str,
        category: str,
        priority: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        self._before_call()
        if self._repository is not None:
            return self._repository.create_ticket(user_id, asset_id, category, priority, idempotency_key)
        if idempotency_key and idempotency_key in self._idempotency:
            return deepcopy(self._tickets[self._idempotency[idempotency_key]])

        ticket_id = f"T-{self._next_id:04d}"
        self._next_id += 1
        ticket = {
            "ticket_id": ticket_id,
            "user_id": user_id,
            "asset_id": asset_id,
            "category": category,
            "priority": priority,
            "status": "created",
        }
        self._tickets[ticket_id] = ticket
        if idempotency_key:
            self._idempotency[idempotency_key] = ticket_id
        return deepcopy(ticket)

    def get_ticket(self, ticket_id: str) -> dict[str, Any] | None:
        self._before_call()
        if self._repository is not None:
            return self._repository.get_ticket(ticket_id)
        ticket = self._tickets.get(ticket_id)
        return deepcopy(ticket) if ticket is not None else None

    def list_tickets(self, user_id: str | None = None) -> list[dict[str, Any]]:
        self._before_call()
        if self._repository is not None:
            return self._repository.list_tickets(user_id)
        tickets = self._tickets.values()
        if user_id is not None:
            tickets = (ticket for ticket in tickets if ticket["user_id"] == user_id)
        return deepcopy(list(tickets))
