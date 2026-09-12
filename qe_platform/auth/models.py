"""Small, safe authentication value objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


VALID_ROLES = frozenset({"viewer", "reviewer", "releaser", "admin"})


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """A verified subject and its internal platform roles.

    Claims deliberately do not survive the verifier boundary: callers only need
    the stable subject and approved roles, and keeping the IdP response out of
    application state prevents it reaching logs or response payloads.
    """

    subject: str
    roles: frozenset[str]

    def has_role(self, required: str) -> bool:
        if required not in VALID_ROLES:
            raise ValueError("unknown role")
        return "admin" in self.roles or required in self.roles


class RoleMapper:
    """Maps a single OIDC roles/groups claim to the four internal roles."""

    def __init__(self, claim_name: str = "roles", mapping: Mapping[str, str] | None = None) -> None:
        if not isinstance(claim_name, str) or not claim_name.strip():
            raise ValueError("role claim name must be nonempty")
        self.claim_name = claim_name.strip()
        source = mapping or {}
        self.mapping = {
            key: value
            for key, value in source.items()
            if isinstance(key, str) and isinstance(value, str) and value in VALID_ROLES
        }

    def roles_from_claims(self, claims: Mapping[str, Any]) -> frozenset[str]:
        value = claims.get(self.claim_name)
        if not isinstance(value, (list, tuple, set, frozenset)):
            return frozenset()
        values: Iterable[object] = value
        return frozenset(
            internal
            for external in values
            if isinstance(external, str)
            for internal in (self.mapping.get(external),)
            if internal in VALID_ROLES
        )

    # Kept as a readable alias for the design document's initial naming.
    def map_claims(self, claims: Mapping[str, Any]) -> frozenset[str]:
        return self.roles_from_claims(claims)
