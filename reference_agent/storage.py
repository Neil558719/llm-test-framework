"""参考 Agent 的最小 SQLite 存储层。"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict


class SQLiteStore:
    """保存会话元数据，支持文件数据库和单连接内存数据库。"""

    def __init__(self, database: str = "reference_agent.db") -> None:
        self._connection = sqlite3.connect(database, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS sessions ("
            "session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL)"
        )
        self._connection.commit()

    def upsert_session(self, session_id: str, user_id: str) -> None:
        self._connection.execute(
            "INSERT INTO sessions(session_id, user_id) VALUES (?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET user_id=excluded.user_id",
            (session_id, user_id),
        )
        self._connection.commit()

    def get_session(self, session_id: str) -> Dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT session_id, user_id FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

    def close(self) -> None:
        self._connection.close()
