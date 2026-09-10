"""Shared SQLite connection settings for local production data stores."""

from __future__ import annotations

import sqlite3


def configure_sqlite(connection: sqlite3.Connection) -> None:
    """Configure durability and contention defaults before application queries."""
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA busy_timeout=5000")
