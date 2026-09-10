"""Generic OIDC authentication primitives for the quality platform."""

from .models import AuthenticatedPrincipal, RoleMapper
from .oidc import OidcVerificationError, OidcVerifier
from .session import AuthSession, AuthorizationAttempt, SessionStore

__all__ = [
    "AuthenticatedPrincipal",
    "AuthSession",
    "AuthorizationAttempt",
    "OidcVerificationError",
    "OidcVerifier",
    "RoleMapper",
    "SessionStore",
]
