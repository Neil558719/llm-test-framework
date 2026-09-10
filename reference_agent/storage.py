"""Durable SQLite persistence owned by the Reference Agent boundary."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterator

from qe_platform.storage import Migration, MigrationRunner, configure_sqlite


class SQLiteStore:
    """Persist session and business state while keeping service response shapes stable."""

    def __init__(self, database: str | Path = "reference_agent.db") -> None:
        self.database = str(database)
        self._lock = RLock()
        self._connection = sqlite3.connect(self.database, check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            configure_sqlite(self._connection)
            self.migrate()

    def migrate(self) -> int:
        return MigrationRunner(self._connection, "reference_agent", _MIGRATIONS).apply()

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                yield
                self._connection.commit()
            except BaseException:
                self._connection.rollback()
                raise

    def upsert_session(self, session_id: str, user_id: str) -> None:
        with self._transaction():
            self._connection.execute(
                "INSERT INTO sessions(session_id, user_id) VALUES (?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET user_id=excluded.user_id",
                (session_id, user_id),
            )

    def get_session(self, session_id: str) -> Dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT session_id, user_id FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def create_ticket(
        self, user_id: str, asset_id: str, category: str, priority: str, idempotency_key: str | None
    ) -> dict[str, Any]:
        with self._transaction():
            existing = self._idempotent_row("tickets", "ticket_id", idempotency_key)
            if existing is not None:
                return existing
            ticket_id = self._next_id("tickets", "ticket_id", "T")
            self._connection.execute(
                "INSERT INTO tickets(ticket_id, user_id, asset_id, category, priority, status, idempotency_key) "
                "VALUES (?, ?, ?, ?, ?, 'created', ?)",
                (ticket_id, user_id, asset_id, category, priority, idempotency_key),
            )
            return self._ticket(ticket_id)

    def get_ticket(self, ticket_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT ticket_id, user_id, asset_id, category, priority, status FROM tickets WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_tickets(self, user_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT ticket_id, user_id, asset_id, category, priority, status FROM tickets"
        parameters: tuple[str, ...] = ()
        if user_id is not None:
            sql += " WHERE user_id = ?"
            parameters = (user_id,)
        sql += " ORDER BY ticket_id"
        with self._lock:
            rows = self._connection.execute(sql, parameters).fetchall()
        return [dict(row) for row in rows]

    def create_approval(
        self, user_id: str, software: str, justification: str, idempotency_key: str | None
    ) -> dict[str, Any]:
        with self._transaction():
            existing = self._idempotent_row("approvals", "approval_id", idempotency_key)
            if existing is not None:
                return existing
            approval_id = self._next_id("approvals", "approval_id", "A")
            self._connection.execute(
                "INSERT INTO approvals(approval_id, user_id, software, justification, status, idempotency_key) "
                "VALUES (?, ?, ?, ?, 'pending', ?)",
                (approval_id, user_id, software, justification, idempotency_key),
            )
            return self._approval(approval_id)

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT approval_id, user_id, software, justification, status FROM approvals WHERE approval_id = ?", (approval_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_access_draft(self, session_id: str) -> str:
        with self._lock:
            row = self._connection.execute(
                "SELECT message FROM access_drafts WHERE session_id = ?", (session_id,)
            ).fetchone()
        return "" if row is None else str(row[0])

    def upsert_access_draft(self, session_id: str, message: str) -> None:
        with self._transaction():
            self._connection.execute(
                "INSERT INTO access_drafts(session_id, message) VALUES (?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET message=excluded.message",
                (session_id, message),
            )

    def delete_access_draft(self, session_id: str) -> None:
        with self._transaction():
            self._connection.execute("DELETE FROM access_drafts WHERE session_id = ?", (session_id,))

    def backup(self, target: str | Path) -> None:
        target_path = Path(target)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        destination = sqlite3.connect(str(target_path))
        try:
            with self._lock:
                self._connection.backup(destination)
        finally:
            destination.close()

    def _idempotent_row(self, table: str, identifier: str, key: str | None) -> dict[str, Any] | None:
        if not key:
            return None
        row = self._connection.execute(
            f"SELECT {identifier} FROM {table} WHERE idempotency_key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        return self._ticket(row[0]) if table == "tickets" else self._approval(row[0])

    def _next_id(self, table: str, identifier: str, prefix: str) -> str:
        row = self._connection.execute(
            f"SELECT COALESCE(MAX(CAST(SUBSTR({identifier}, 3) AS INTEGER)), 0) + 1 FROM {table}"
        ).fetchone()
        return f"{prefix}-{int(row[0]):04d}"

    def _ticket(self, ticket_id: str) -> dict[str, Any]:
        value = self.get_ticket(ticket_id)
        assert value is not None
        return value

    def _approval(self, approval_id: str) -> dict[str, Any]:
        value = self.get_approval(approval_id)
        assert value is not None
        return value

    def close(self) -> None:
        with self._lock:
            self._connection.close()


def _create_reference_agent_tables(connection: sqlite3.Connection) -> None:
    connection.execute("CREATE TABLE IF NOT EXISTS sessions (session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL)")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS tickets (ticket_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, "
        "asset_id TEXT NOT NULL, category TEXT NOT NULL, priority TEXT NOT NULL, status TEXT NOT NULL, "
        "idempotency_key TEXT UNIQUE)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS approvals (approval_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, "
        "software TEXT NOT NULL, justification TEXT NOT NULL, status TEXT NOT NULL, idempotency_key TEXT UNIQUE)"
    )
    connection.execute("CREATE TABLE IF NOT EXISTS access_drafts (session_id TEXT PRIMARY KEY, message TEXT NOT NULL)")


_MIGRATIONS = (Migration(1, _create_reference_agent_tables),)
