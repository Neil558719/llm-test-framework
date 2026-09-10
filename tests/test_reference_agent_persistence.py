from concurrent.futures import ThreadPoolExecutor
import sqlite3

from fastapi.testclient import TestClient

from reference_agent.app import create_app
from reference_agent.deployment import create_deployment_app
from reference_agent.services import ApprovalService, AssetService, TicketService, UserService
from reference_agent.storage import SQLiteStore


def test_ticket_and_approval_state_survive_store_reopen_with_idempotency(tmp_path):
    database = tmp_path / "reference-agent.db"
    store = SQLiteStore(database)
    tickets = TicketService(repository=store)
    approvals = ApprovalService(repository=store)

    ticket = tickets.create_ticket("U1001", "PC-1001", "vpn", "high", "ticket-request")
    approval = approvals.create_approval("U1001", "VPN", "remote work", "approval-request")
    store.close()

    reopened = SQLiteStore(database)
    try:
        tickets = TicketService(repository=reopened)
        approvals = ApprovalService(repository=reopened)
        assert tickets.get_ticket(ticket["ticket_id"]) == ticket
        assert approvals.get_approval(approval["approval_id"]) == approval
        assert tickets.create_ticket("U1001", "PC-1001", "other", "normal", "ticket-request") == ticket
        assert approvals.create_approval("U1001", "Slack", "other", "approval-request") == approval
    finally:
        reopened.close()


def test_persistent_ticket_writes_allocate_unique_ids_during_concurrency(tmp_path):
    store = SQLiteStore(tmp_path / "reference-agent.db")
    tickets = TicketService(repository=store)

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            created = list(pool.map(
                lambda index: tickets.create_ticket("U1001", f"PC-{index}", "vpn", "normal"),
                range(40),
            ))
        assert len({item["ticket_id"] for item in created}) == 40
        assert len(tickets.list_tickets()) == 40
    finally:
        store.close()


def test_access_draft_survives_app_reopen_until_request_is_complete(tmp_path):
    database = tmp_path / "reference-agent.db"
    users = UserService({"U1001": {"user_id": "U1001", "name": "User"}})
    assets = AssetService({"PC-1001": {"asset_id": "PC-1001", "owner_id": "U1001", "status": "active"}})
    app = create_app(database, user_service=users, asset_service=assets)

    with TestClient(app) as client:
        response = client.post("/api/chat", json={
            "message": "申请安装 VPN", "user_id": "U1001", "session_id": "persistent-draft",
        })
        assert response.json()["metadata"]["approval_status"] == "needs_information"
    app.state.store.close()
    connection = sqlite3.connect(database)
    try:
        draft = connection.execute(
            "SELECT message FROM access_drafts WHERE session_id = 'persistent-draft'"
        ).fetchone()[0]
        assert draft == "申请权限 VPN"
    finally:
        connection.close()

    reopened = create_app(database, user_service=users, asset_service=assets)
    try:
        with TestClient(reopened) as client:
            response = client.post("/api/chat", json={
                "message": "理由是远程办公", "user_id": "U1001", "session_id": "persistent-draft",
            })
        body = response.json()
        assert body["metadata"]["approval_status"] == "pending"
        assert body["tool_calls"][-1]["result"]["approval_id"] == "A-0001"
    finally:
        reopened.state.store.close()


def test_store_backup_copies_a_consistent_database(tmp_path):
    source = tmp_path / "reference-agent.db"
    backup = tmp_path / "backup.db"
    store = SQLiteStore(source)
    try:
        store.upsert_session("session-1", "U1001")
        store.backup(backup)
    finally:
        store.close()

    restored = SQLiteStore(backup)
    try:
        assert restored.get_session("session-1") == {"session_id": "session-1", "user_id": "U1001"}
    finally:
        restored.close()


def test_deployment_factory_uses_durable_ticket_services(tmp_path, monkeypatch):
    database = tmp_path / "deployment.db"
    monkeypatch.setenv("REFERENCE_AGENT_DATABASE", str(database))
    app = create_deployment_app()
    try:
        with TestClient(app) as client:
            response = client.post("/api/chat", json={
                "message": "VPN 无法连接，设备 PC-1001，请创建工单",
                "user_id": "U1001",
                "session_id": "deployment-ticket",
            })
        assert response.json()["metadata"]["ticket_status"] == "created"
    finally:
        app.state.store.close()

    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 1
    finally:
        connection.close()
