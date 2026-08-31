"""里程碑 3 Mock 下游服务契约。"""

import time

import pytest

from reference_agent.services.assets import AssetService
from reference_agent.services.common import FailureConfig, ServiceError
from reference_agent.services.tickets import TicketService
from reference_agent.services.users import UserService


def test_user_and_asset_services_return_known_records_and_empty_for_unknown():
    users = UserService(records={"U1001": {"user_id": "U1001", "name": "张三"}})
    assets = AssetService(records={"PC-1001": {"asset_id": "PC-1001", "owner_id": "U1001"}})

    assert users.get_user("U1001")["name"] == "张三"
    assert users.get_user("missing") is None
    assert assets.get_asset("PC-1001")["owner_id"] == "U1001"
    assert assets.get_asset("missing") is None


def test_lookup_services_raise_configured_failure():
    failure = FailureConfig(status_code=503, message="user service unavailable")
    service = UserService(failure=failure)

    with pytest.raises(ServiceError) as exc_info:
        service.get_user("U1001")

    assert exc_info.value.status_code == 503
    assert str(exc_info.value) == "user service unavailable"


def test_lookup_services_apply_configured_delay():
    service = AssetService(
        records={"PC-1001": {"asset_id": "PC-1001"}},
        failure=FailureConfig(delay_seconds=0.02),
    )

    started = time.perf_counter()
    assert service.get_asset("PC-1001") is not None

    assert time.perf_counter() - started >= 0.02


def test_ticket_service_creates_and_retrieves_ticket():
    service = TicketService()

    ticket = service.create_ticket("U1001", "PC-1001", "vpn", "high")

    assert ticket["ticket_id"].startswith("T-")
    assert ticket["status"] == "created"
    assert service.get_ticket(ticket["ticket_id"]) == ticket


def test_ticket_service_reuses_idempotency_key():
    service = TicketService()

    first = service.create_ticket("U1001", "PC-1001", "vpn", "high", "request-1")
    second = service.create_ticket("U1001", "PC-1001", "vpn", "high", "request-1")

    assert second == first
    assert len(service.list_tickets()) == 1


def test_ticket_service_raises_configured_failure():
    service = TicketService(failure=FailureConfig(status_code=500, message="db down"))

    with pytest.raises(ServiceError) as exc_info:
        service.create_ticket("U1001", "PC-1001", "vpn", "high")

    assert exc_info.value.status_code == 500
