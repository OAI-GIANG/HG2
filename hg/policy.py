"""Fail-closed policy predicates and pure approval state transitions."""
from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

ALLOWED = frozenset({
    "health.read", "session.create", "edge.register", "edge.heartbeat", "edge.status"
})
NEEDS_AUTH = frozenset({"session.create", "edge.register", "edge.heartbeat", "edge.status"})
FORBIDDEN = frozenset({
    "file.read", "file.write", "shell.exec", "network.fetch", "deploy",
    "identity.change", "state.import", "provider.invoke",
})
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_APPROVAL_STATES = frozenset({"PENDING", "APPROVED", "DENIED", "EXPIRED"})


class PolicyError(ValueError):
    """Raised when a policy or approval transition is invalid."""


@dataclass(frozen=True)
class Decision:
    allowed: bool
    action: str
    reason: str
    principal_id: str = ""
    grant_id: str | None = None


@dataclass(frozen=True)
class CapabilityGrant:
    grant_id: str
    principal_id: str
    capability: str
    issued_at: float
    expires_at: float | None = None
    revoked_at: float | None = None
    resource_scope: str | None = None

    def active_at(self, now: float) -> bool:
        if not self.grant_id or not self.principal_id or not self.capability:
            return False
        if not math.isfinite(self.issued_at) or now < self.issued_at:
            return False
        if self.expires_at is not None and (not math.isfinite(self.expires_at) or now >= self.expires_at):
            return False
        if self.revoked_at is not None and (not math.isfinite(self.revoked_at) or now >= self.revoked_at):
            return False
        return True


def authorize(action: Any, *, authenticated: bool = False) -> Decision:
    """Compatibility policy for existing callers; deny by default."""
    if not isinstance(action, str) or not action:
        return Decision(False, "", "INVALID_ACTION")
    if action in FORBIDDEN:
        return Decision(False, action, "EXPLICITLY_FORBIDDEN")
    if action not in ALLOWED:
        return Decision(False, action, "NOT_ALLOWLISTED")
    if action in NEEDS_AUTH and not authenticated:
        return Decision(False, action, "AUTHENTICATION_REQUIRED")
    return Decision(True, action, "ALLOWLISTED")


def authorize_with_grants(
    principal_id: str,
    action: str,
    grants: Iterable[CapabilityGrant],
    *,
    now: float,
    resource: str | None = None,
) -> Decision:
    """Authorize using explicit, unexpired grants; never elevate from malformed input."""
    if not isinstance(principal_id, str) or not principal_id.strip():
        return Decision(False, action if isinstance(action, str) else "", "PRINCIPAL_REQUIRED")
    base = authorize(action, authenticated=True)
    if not base.allowed:
        return Decision(False, base.action, base.reason, principal_id)
    if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now):
        return Decision(False, base.action, "INVALID_POLICY_TIME", principal_id)
    try:
        candidates = list(grants)
    except TypeError:
        return Decision(False, base.action, "INVALID_GRANT_SET", principal_id)
    for grant in candidates:
        if not isinstance(grant, CapabilityGrant):
            continue
        if grant.principal_id != principal_id or grant.capability != action or not grant.active_at(float(now)):
            continue
        if grant.resource_scope is not None and grant.resource_scope != resource:
            continue
        return Decision(True, action, "EXPLICIT_GRANT", principal_id, grant.grant_id)
    return Decision(False, action, "GRANT_REQUIRED", principal_id)


def create_approval_request(
    *,
    principal_id: str,
    action: str,
    resource_id: str,
    request_digest: str,
    now: float,
    ttl_seconds: float = 300.0,
) -> dict[str, Any]:
    if not isinstance(principal_id, str) or not principal_id.strip():
        raise PolicyError("PRINCIPAL_REQUIRED")
    if not isinstance(action, str) or action not in ALLOWED or action in FORBIDDEN:
        raise PolicyError("ACTION_NOT_APPROVABLE")
    if not isinstance(resource_id, str) or not resource_id.strip():
        raise PolicyError("RESOURCE_REQUIRED")
    if not isinstance(request_digest, str) or not _DIGEST_RE.fullmatch(request_digest):
        raise PolicyError("REQUEST_DIGEST_INVALID")
    if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now):
        raise PolicyError("INVALID_POLICY_TIME")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float)) or not math.isfinite(ttl_seconds):
        raise PolicyError("INVALID_APPROVAL_TTL")
    if ttl_seconds <= 0 or ttl_seconds > 86400:
        raise PolicyError("INVALID_APPROVAL_TTL")
    return {
        "approval_id": uuid.uuid4().hex,
        "principal_id": principal_id,
        "action": action,
        "resource_id": resource_id,
        "request_digest": request_digest,
        "status": "PENDING",
        "created_at": float(now),
        "expires_at": float(now) + float(ttl_seconds),
        "decided_by": None,
        "decided_at": None,
        "decision_reason": "",
    }


def decide_approval(
    request: Mapping[str, Any],
    *,
    decision: str,
    approver_id: str,
    now: float,
    reason: str = "",
) -> dict[str, Any]:
    """Pure state-machine transition; callers must persist the returned state atomically."""
    if not isinstance(request, Mapping):
        raise PolicyError("APPROVAL_REQUEST_INVALID")
    required = {
        "approval_id", "principal_id", "action", "resource_id", "request_digest",
        "status", "created_at", "expires_at", "decided_by", "decided_at", "decision_reason",
    }
    if set(request) != required:
        raise PolicyError("APPROVAL_SCHEMA_INVALID")
    current = dict(request)
    if current["status"] not in _APPROVAL_STATES:
        raise PolicyError("APPROVAL_STATUS_INVALID")
    if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now):
        raise PolicyError("INVALID_POLICY_TIME")
    if current["status"] != "PENDING":
        if current["status"] == decision and current["decided_by"] == approver_id:
            return current
        raise PolicyError("APPROVAL_ALREADY_DECIDED")
    if float(now) >= current["expires_at"]:
        current.update(status="EXPIRED", decided_by=None, decided_at=float(now), decision_reason="EXPIRED")
        return current
    if decision not in ("APPROVED", "DENIED"):
        raise PolicyError("APPROVAL_DECISION_INVALID")
    if not isinstance(approver_id, str) or not approver_id.strip():
        raise PolicyError("APPROVER_REQUIRED")
    if approver_id == current["principal_id"]:
        raise PolicyError("SELF_APPROVAL_FORBIDDEN")
    if not isinstance(reason, str) or len(reason) > 512:
        raise PolicyError("APPROVAL_REASON_INVALID")
    current.update(
        status=decision,
        decided_by=approver_id,
        decided_at=float(now),
        decision_reason=reason,
    )
    return current
