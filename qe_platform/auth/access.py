"""Trusted server-side grants; request claims never define application access."""
from collections.abc import Iterable, Mapping
import os

from fastapi import HTTPException

from .models import AuthenticatedPrincipal
from qe_platform.application_scope import application_set, load_grants, valid_identifier


class ApplicationAccessPolicy:
    def __init__(self, mapping: Mapping[str, Iterable[str]]) -> None:
        if not isinstance(mapping, Mapping) or not all(valid_identifier(subject) for subject in mapping):
            raise ValueError("application access must map subject identifiers to grants")
        self._mapping = {subject: application_set(apps) for subject, apps in mapping.items()}

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None):
        values = os.environ if environ is None else environ
        return cls(load_grants(values.get("QE_APPLICATION_ACCESS", "{}")))

    def allowed_applications(self, principal: AuthenticatedPrincipal) -> frozenset[str]:
        return self._mapping.get(principal.subject, frozenset())

    def require_application(self, principal: AuthenticatedPrincipal, application: str) -> None:
        if not valid_identifier(application) or application not in self.allowed_applications(principal):
            raise HTTPException(status_code=403, detail="forbidden")