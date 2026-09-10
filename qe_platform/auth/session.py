"""Persisted opaque browser sessions and one-time OIDC authorization attempts."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

from .models import VALID_ROLES


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@dataclass(frozen=True)
class AuthSession:
    session_id: str
    subject: str
    roles: frozenset[str]
    expires_at: datetime
    csrf_hash: str


@dataclass(frozen=True)
class AuthorizationAttempt:
    state: str
    nonce: str
    code_verifier: str
    redirect_target: str
    expires_at: datetime


class SessionStore:
    """Separate SQLite storage containing only opaque, minimally needed state."""

    def __init__(self, database: str | Path, clock: Callable[[], datetime] | None = None) -> None:
        self.database = str(database)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS auth_sessions (
                    session_id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    roles_json TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    csrf_hash TEXT NOT NULL,
                    revoked_at TEXT
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS oidc_authorization_attempts (
                    state TEXT PRIMARY KEY,
                    nonce TEXT NOT NULL,
                    code_verifier TEXT NOT NULL,
                    redirect_target TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )"""
            )

    def create(
        self,
        subject: str,
        roles: Iterable[str],
        *,
        expires_at: datetime | None = None,
        session_id: str | None = None,
        csrf_token: str | None = None,
    ) -> AuthSession:
        if not isinstance(subject, str) or not subject:
            raise ValueError("subject must be nonempty")
        clean_roles = frozenset(role for role in roles if role in VALID_ROLES)
        now = _utc(self._clock())
        expiry = _utc(expires_at or (now + timedelta(hours=8)))
        if expiry <= now:
            raise ValueError("session expiry must be in the future")
        identifier = session_id or secrets.token_urlsafe(32)
        raw_csrf = csrf_token or secrets.token_urlsafe(32)
        digest = hashlib.sha256(raw_csrf.encode("utf-8")).hexdigest()
        record = AuthSession(identifier, subject, clean_roles, expiry, digest)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO auth_sessions (session_id, subject, roles_json, expires_at, csrf_hash, revoked_at) VALUES (?, ?, ?, ?, ?, NULL)",
                (record.session_id, record.subject, json.dumps(sorted(record.roles)), record.expires_at.isoformat(), record.csrf_hash),
            )
        return record

    def get(self, session_id: str) -> AuthSession | None:
        if not isinstance(session_id, str) or not session_id:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT session_id, subject, roles_json, expires_at, csrf_hash FROM auth_sessions WHERE session_id = ? AND revoked_at IS NULL",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            expiry = datetime.fromisoformat(row["expires_at"])
            roles = frozenset(role for role in json.loads(row["roles_json"]) if role in VALID_ROLES)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if _utc(expiry) <= _utc(self._clock()):
            return None
        return AuthSession(row["session_id"], row["subject"], roles, _utc(expiry), row["csrf_hash"])

    def revoke(self, session_id: str) -> None:
        with self._connect() as connection:
            connection.execute("UPDATE auth_sessions SET revoked_at = ? WHERE session_id = ?", (_utc(self._clock()).isoformat(), session_id))

    def delete_expired(self) -> int:
        now = _utc(self._clock()).isoformat()
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM auth_sessions WHERE expires_at <= ? OR revoked_at IS NOT NULL", (now,))
            connection.execute("DELETE FROM oidc_authorization_attempts WHERE expires_at <= ?", (now,))
        return cursor.rowcount

    @staticmethod
    def verify_csrf(session: AuthSession, token: str | None) -> bool:
        if not isinstance(token, str) or not token:
            return False
        return hmac.compare_digest(hashlib.sha256(token.encode("utf-8")).hexdigest(), session.csrf_hash)

    def create_authorization_attempt(self, redirect_target: str, *, lifetime: timedelta = timedelta(minutes=10)) -> AuthorizationAttempt:
        now = _utc(self._clock())
        attempt = AuthorizationAttempt(
            state=secrets.token_urlsafe(32),
            nonce=secrets.token_urlsafe(32),
            code_verifier=secrets.token_urlsafe(64),
            redirect_target=redirect_target,
            expires_at=now + lifetime,
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO oidc_authorization_attempts (state, nonce, code_verifier, redirect_target, expires_at) VALUES (?, ?, ?, ?, ?)",
                (attempt.state, attempt.nonce, attempt.code_verifier, attempt.redirect_target, attempt.expires_at.isoformat()),
            )
        return attempt

    def consume_authorization_attempt(self, state: str) -> AuthorizationAttempt | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state, nonce, code_verifier, redirect_target, expires_at FROM oidc_authorization_attempts WHERE state = ?", (state,)
            ).fetchone()
            connection.execute("DELETE FROM oidc_authorization_attempts WHERE state = ?", (state,))
        if row is None:
            return None
        try:
            attempt = AuthorizationAttempt(
                row["state"], row["nonce"], row["code_verifier"], row["redirect_target"], _utc(datetime.fromisoformat(row["expires_at"]))
            )
        except (TypeError, ValueError):
            return None
        return attempt if attempt.expires_at > _utc(self._clock()) else None
