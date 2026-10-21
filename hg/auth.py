"""Constant-time bearer authentication for trusted HG application entry points."""
from __future__ import annotations
import hmac
import os
from dataclasses import dataclass

CONFIGURABLE_SCOPES = frozenset({
    "provider.invoke", "session.create", "edge.register", "edge.heartbeat",
    "workflow.task.create", "workflow.task.read", "workflow.task.transition",
    "policy.approval.request", "policy.approval.vote",
    "brain.request", "audit.append", "sync.outbox.attempt", "sync.outbox.acknowledge",
    "state.migration.import", "state.backup", "state.restore",
})
DEFAULT_SCOPES = frozenset({"provider.invoke"})
_MAX_TOKEN_CHARS = 4096
_PRINCIPAL_SEAL = object()


@dataclass(frozen=True, repr=False)
class AuthenticatedPrincipal:
    """Opaque authenticated caller context bound to a configured subject."""
    scopes: frozenset[str]
    _seal: object
    principal_id: str | None = None

    def allows(self, action: str) -> bool:
        return self._seal is _PRINCIPAL_SEAL and action in self.scopes

    def __repr__(self) -> str:
        return f"AuthenticatedPrincipal(scopes={sorted(self.scopes)!r})"


class BearerAuthenticator:
    """Validate an Authorization: Bearer header; never expose configured token."""

    def __init__(self, token: str = "", scopes=DEFAULT_SCOPES, *, principal_id: str | None = None):
        valid_token = (
            isinstance(token, str) and 0 < len(token) <= _MAX_TOKEN_CHARS
            and not any(ch.isspace() for ch in token)
        )
        self._token = token if valid_token else ""
        self.principal_id = (
            principal_id if isinstance(principal_id, str) and principal_id.strip() and len(principal_id) <= 256
            else None
        )
        try:
            requested = frozenset(scopes)
        except TypeError:
            requested = frozenset()
        # Any unknown capability invalidates the entire scope configuration.
        self.scopes = requested if requested <= CONFIGURABLE_SCOPES else frozenset()

    @classmethod
    def from_env(cls) -> "BearerAuthenticator":
        token = os.environ.get("HG_AUTH_TOKEN", "")
        principal_id = os.environ.get("HG_AUTH_PRINCIPAL_ID")
        raw_scopes = os.environ.get("HG_AUTH_SCOPES", "provider.invoke")
        requested = frozenset(part.strip() for part in raw_scopes.split(",") if part.strip())
        if not requested <= CONFIGURABLE_SCOPES:
            requested = frozenset()
        return cls(token, requested, principal_id=principal_id)

    def __repr__(self) -> str:
        return f"BearerAuthenticator(configured={bool(self._token)}, scopes={sorted(self.scopes)!r})"

    def authenticate(self, authorization_header: str | None) -> AuthenticatedPrincipal | None:
        if not self._token or not self.scopes:
            return None
        if not isinstance(authorization_header, str) or len(authorization_header) > _MAX_TOKEN_CHARS + 16:
            return None
        scheme, separator, supplied = authorization_header.partition(" ")
        if not separator or scheme.lower() != "bearer" or not supplied or any(ch.isspace() for ch in supplied):
            return None
        if not hmac.compare_digest(supplied.encode("utf-8"), self._token.encode("utf-8")):
            return None
        return AuthenticatedPrincipal(self.scopes, _PRINCIPAL_SEAL, self.principal_id)
