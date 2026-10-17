"""Fail-closed policy predicates, capability grants, and approval state transitions."""
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
_APPROVAL_FIELDS = {
    "approval_id", "principal_id", "action", "resource_id", "request_digest",
    "status", "version", "created_at", "expires_at", "decided_by", "decided_at",
    "decision_reason",
}


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
        if not isinstance(self.grant_id, str) or not self.grant_id.strip():
            return False
        if not isinstance(self.principal_id, str) or not self.principal_id.strip():
            return False
        if not isinstance(self.capability, str) or not self.capability.strip():
            return False
        if isinstance(self.issued_at, bool) or not isinstance(self.issued_at, (int, float)) or not math.isfinite(self.issued_at) or now < self.issued_at:
            return False
        if self.expires_at is not None and (
            isinstance(self.expires_at, bool) or not isinstance(self.expires_at, (int, float))
            or not math.isfinite(self.expires_at) or now >= self.expires_at
        ):
            return False
        if self.revoked_at is not None and (
            isinstance(self.revoked_at, bool) or not isinstance(self.revoked_at, (int, float))
            or not math.isfinite(self.revoked_at) or now >= self.revoked_at
        ):
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


def validate_approval_request(request: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(request, Mapping) or set(request) != _APPROVAL_FIELDS:
        raise PolicyError("APPROVAL_SCHEMA_INVALID")
    result = dict(request)
    for field in ("approval_id", "principal_id", "resource_id"):
        if not isinstance(result[field], str) or not result[field].strip():
            raise PolicyError("APPROVAL_SCHEMA_INVALID")
    if not isinstance(result["action"], str) or result["action"] not in ALLOWED or result["action"] in FORBIDDEN:
        raise PolicyError("ACTION_NOT_APPROVABLE")
    if not isinstance(result["request_digest"], str) or not _DIGEST_RE.fullmatch(result["request_digest"]):
        raise PolicyError("REQUEST_DIGEST_INVALID")
    if not isinstance(result["status"], str) or result["status"] not in _APPROVAL_STATES:
        raise PolicyError("APPROVAL_STATUS_INVALID")
    version = result["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise PolicyError("APPROVAL_VERSION_INVALID")
    created_at = result["created_at"]
    expires_at = result["expires_at"]
    for value in (created_at, expires_at):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise PolicyError("APPROVAL_SCHEMA_INVALID")
    if expires_at <= created_at:
        raise PolicyError("APPROVAL_SCHEMA_INVALID")
    decided_at = result["decided_at"]
    if decided_at is not None and (
        isinstance(decided_at, bool) or not isinstance(decided_at, (int, float)) or not math.isfinite(decided_at)
    ):
        raise PolicyError("APPROVAL_SCHEMA_INVALID")
    decided_by = result["decided_by"]
    if decided_by is not None and (not isinstance(decided_by, str) or not decided_by.strip()):
        raise PolicyError("APPROVAL_SCHEMA_INVALID")
    reason = result["decision_reason"]
    if not isinstance(reason, str) or len(reason) > 512:
        raise PolicyError("APPROVAL_SCHEMA_INVALID")
    if result["status"] == "PENDING" and (decided_by is not None or decided_at is not None or reason):
        raise PolicyError("APPROVAL_PENDING_HAS_DECISION")
    if result["status"] in ("APPROVED", "DENIED") and (decided_by is None or decided_at is None):
        raise PolicyError("APPROVAL_DECISION_INCOMPLETE")
    if result["status"] == "EXPIRED" and decided_at is None:
        raise PolicyError("APPROVAL_EXPIRY_INCOMPLETE")
    return result


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
        "version": 1,
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
    """Pure state-machine transition; callers must persist the result atomically."""
    current = validate_approval_request(request)
    if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now):
        raise PolicyError("INVALID_POLICY_TIME")
    if current["status"] != "PENDING":
        if (
            current["status"] == decision
            and current["decided_by"] == approver_id
            and current["decision_reason"] == reason
        ):
            return current
        raise PolicyError("APPROVAL_ALREADY_DECIDED")
    if float(now) >= current["expires_at"]:
        current.update(
            status="EXPIRED", version=current["version"] + 1,
            decided_by=None, decided_at=float(now), decision_reason="EXPIRED",
        )
        return validate_approval_request(current)
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
        version=current["version"] + 1,
        decided_by=approver_id,
        decided_at=float(now),
        decision_reason=reason,
    )
    return validate_approval_request(current)


def authorize_with_approvals(
    principal_id: str,
    action: str,
    approvals: Iterable[Mapping[str, Any]],
    *,
    now: float,
    resource: str,
) -> Decision:
    """Allow only an unexpired approved request for the exact principal/action/resource."""
    base = authorize(action, authenticated=True)
    if not base.allowed:
        return Decision(False, base.action, base.reason, principal_id if isinstance(principal_id, str) else "")
    if not isinstance(principal_id, str) or not principal_id.strip():
        return Decision(False, action, "PRINCIPAL_REQUIRED")
    if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now):
        return Decision(False, action, "INVALID_POLICY_TIME", principal_id)
    try:
        candidates = list(approvals)
    except TypeError:
        return Decision(False, action, "INVALID_APPROVAL_SET", principal_id)
    for candidate in candidates:
        try:
            approval = validate_approval_request(candidate)
        except PolicyError:
            continue
        if (
            approval["status"] == "APPROVED"
            and approval["principal_id"] == principal_id
            and approval["action"] == action
            and approval["resource_id"] == resource
            and float(now) < approval["expires_at"]
        ):
            return Decision(True, action, "APPROVED_REQUEST", principal_id, approval["approval_id"])
    return Decision(False, action, "APPROVAL_REQUIRED", principal_id)


class ApprovalService:
    """Persist approval requests and decisions through the transactional HG2 state store."""

    def __init__(self, store, *, clock):
        self.store = store
        self.clock = clock

    def request(
        self,
        *,
        principal_id: str,
        action: str,
        resource_id: str,
        request_digest: str,
        idempotency_key: str,
        ttl_seconds: float = 300.0,
        sync_required: bool = False,
    ) -> dict[str, Any]:
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise PolicyError("APPROVAL_IDEMPOTENCY_KEY_REQUIRED")
        existing = self.store.get_event_by_idempotency(idempotency_key)
        if existing is not None:
            payload = existing.get("payload")
            if (
                existing.get("event_type") == "policy.approval.created"
                and existing.get("actor_id") == principal_id
                and isinstance(payload, dict)
                and payload.get("principal_id") == principal_id
                and payload.get("action") == action
                and payload.get("resource_id") == resource_id
                and payload.get("request_digest") == request_digest
            ):
                current = self.store.get_approval(payload.get("approval_id"))
                if current is not None:
                    return current
            raise PolicyError("APPROVAL_IDEMPOTENCY_CONFLICT")
        request = create_approval_request(
            principal_id=principal_id,
            action=action,
            resource_id=resource_id,
            request_digest=request_digest,
            now=self.clock(),
            ttl_seconds=ttl_seconds,
        )
        self.store.emit(
            "policy.approval.created",
            request,
            actor_id=principal_id,
            authority_context={"principal": principal_id, "role": "requester"},
            idempotency_key=idempotency_key,
            sync_required=sync_required,
        )
        return request

    def decide(
        self,
        approval_id: str,
        *,
        decision: str,
        approver_id: str,
        expected_version: int,
        reason: str = "",
        idempotency_key: str | None = None,
        sync_required: bool = False,
    ) -> dict[str, Any]:
        if not isinstance(approval_id, str) or not approval_id.strip():
            raise PolicyError("APPROVAL_ID_REQUIRED")
        if not isinstance(approver_id, str) or not approver_id.strip():
            raise PolicyError("APPROVER_REQUIRED")
        if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 1:
            raise PolicyError("APPROVAL_VERSION_INVALID")
        transition_key = idempotency_key or "approval:" + approval_id + ":version:" + str(expected_version + 1)
        existing = self.store.get_event_by_idempotency(transition_key)
        if existing is not None:
            payload = existing.get("payload")
            transition = payload.get("transition") if isinstance(payload, dict) else None
            if (
                existing.get("event_type") == "policy.approval.decided"
                and existing.get("actor_id") == approver_id
                and isinstance(payload, dict)
                and isinstance(payload.get("approval"), dict)
                and isinstance(transition, dict)
                and payload["approval"].get("approval_id") == approval_id
                and transition.get("decision") == decision
            ):
                current = self.store.get_approval(approval_id)
                if current == payload["approval"]:
                    return current
            current = self.store.get_approval(approval_id)
            if current is not None and current["version"] != expected_version:
                raise PolicyError("APPROVAL_VERSION_CONFLICT")
            raise PolicyError("APPROVAL_IDEMPOTENCY_CONFLICT")

        current = self.store.get_approval(approval_id)
        if current is None:
            raise PolicyError("APPROVAL_NOT_FOUND")
        if current["version"] != expected_version:
            raise PolicyError("APPROVAL_VERSION_CONFLICT")
        now_value = self.clock()
        updated = decide_approval(
            current,
            decision=decision,
            approver_id=approver_id,
            now=now_value,
            reason=reason,
        )
        payload = {
            "approval": updated,
            "transition": {
                "decision": decision,
                "approver_id": approver_id,
                "reason": reason,
            },
        }
        self.store.emit(
            "policy.approval.decided",
            payload,
            actor_id=approver_id,
            authority_context={"principal": approver_id, "role": "approver"},
            idempotency_key=transition_key,
            sync_required=sync_required,
        )
        return updated
