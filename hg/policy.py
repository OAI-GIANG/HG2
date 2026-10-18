"""Fail-closed policy predicates, capability grants, and approval state transitions."""
from __future__ import annotations

import math
import re
import uuid
import threading
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .auth import AuthenticatedPrincipal, CONFIGURABLE_SCOPES
from .contracts import ContractError, canonical_digest

ALLOWED = frozenset({
    "health.read", "edge.register", "edge.heartbeat", "edge.status",
    "workflow.task.create", "workflow.task.transition",
    "policy.approval.request", "policy.approval.vote",
    "brain.request",
}) | CONFIGURABLE_SCOPES
NEEDS_AUTH = frozenset({
    "edge.register", "edge.heartbeat", "edge.status",
}) | CONFIGURABLE_SCOPES
PRINCIPAL_ONLY_ACTIONS = frozenset({"provider.invoke"})
APPROVABLE_ACTIONS = ALLOWED - PRINCIPAL_ONLY_ACTIONS
# Internal state-changing service actions are deliberately explicit and fail closed.
SERVICE_MUTATION_ACTIONS = frozenset({
    "session.create", "workflow.task.create", "workflow.task.transition",
    "policy.approval.request", "policy.approval.vote", "brain.request", "audit.append",
    "sync.outbox.attempt", "sync.outbox.acknowledge", "state.migration.import",
    "state.backup", "state.restore",
})
MUTATION_EVENT_ACTIONS = MappingProxyType({
    "session.created": "session.create",
    "workflow.task.created": "workflow.task.create",
    "workflow.task.transitioned": "workflow.task.transition",
    "policy.approval.created": "policy.approval.request",
    "policy.approval.decided": "policy.approval.vote",
    "sync.outbox.attempt": "sync.outbox.attempt",
    "sync.outbox.acknowledge": "sync.outbox.acknowledge",
    "state.migration.import": "state.migration.import",
    "state.backup": "state.backup",
    "state.restore": "state.restore",
    "brain.request.accepted": "brain.request",
    "brain.request.completed": "brain.request",
    "provider.call.started": "brain.request",
    "provider.call.completed": "brain.request",
    "tool.call.started": "brain.request",
    "tool.call.completed": "brain.request",
    "tool.loop_blocked": "brain.request",
    "tool.iteration_limit": "brain.request",
})
FORBIDDEN = frozenset({
    "file.read", "file.write", "shell.exec", "network.fetch", "deploy",
    "identity.change", "state.import",
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


@dataclass(frozen=True, repr=False)
class MutationPermit:
    """Single-use in-process receipt bound to one exact durable state operation."""
    nonce: str
    action: str
    event_type: str
    principal_id: str
    actor_id: str
    payload_digest: str
    correlation_id: str
    causation_id: str | None
    idempotency_key: str | None
    event_id: str | None
    authority_digest: str
    evidence_refs_digest: str
    sync_required: bool
    expires_at_monotonic: float
    _seal: object


_MUTATION_PERMIT_SEAL = object()
_MUTATION_PERMIT_LOCK = threading.Lock()
_ISSUED_MUTATION_PERMITS: dict[str, MutationPermit] = {}
_MUTATION_PERMIT_TTL_SECONDS = 30.0
_MUTATION_PERMIT_MAX_PENDING = 10_000


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


def _authorize_base_action(action: Any, *, authenticated: bool = False) -> Decision:
    """Validate an action's base allowlist without granting a mutation permit."""
    if not isinstance(action, str) or not action:
        return Decision(False, "", "INVALID_ACTION")
    if action in FORBIDDEN:
        return Decision(False, action, "EXPLICITLY_FORBIDDEN")
    if action in PRINCIPAL_ONLY_ACTIONS:
        return Decision(False, action, "SEALED_PRINCIPAL_REQUIRED")
    if action not in ALLOWED:
        return Decision(False, action, "NOT_ALLOWLISTED")
    if action in NEEDS_AUTH and not authenticated:
        return Decision(False, action, "AUTHENTICATION_REQUIRED")
    return Decision(True, action, "ALLOWLISTED")


def authorize(action: Any, *, authenticated: bool = False) -> Decision:
    """Compatibility policy for direct callers; mutating actions never pass via a boolean."""
    if isinstance(action, str) and action in SERVICE_MUTATION_ACTIONS:
        return Decision(False, action, "SEALED_PRINCIPAL_REQUIRED")
    return _authorize_base_action(action, authenticated=authenticated)


def authorize_principal(action: Any, principal: Any) -> Decision:
    """Authorize a sealed principal without trusting a caller-supplied boolean.

    The compatibility `authorize(..., authenticated=True)` API is retained for
    existing internal relay paths, but authenticated application actions should
    use this principal-bound decision function.
    """
    if not isinstance(action, str) or not action:
        return Decision(False, "", "INVALID_ACTION")
    if action in FORBIDDEN:
        return Decision(False, action, "EXPLICITLY_FORBIDDEN")
    if action not in ALLOWED:
        return Decision(False, action, "NOT_ALLOWLISTED")
    if action not in NEEDS_AUTH:
        return Decision(True, action, "ALLOWLISTED")
    if not isinstance(principal, AuthenticatedPrincipal):
        return Decision(False, action, "AUTHENTICATION_REQUIRED")
    if not principal.allows(action):
        return Decision(False, action, "ACTION_NOT_AUTHORIZED")
    if action in SERVICE_MUTATION_ACTIONS and (
        not isinstance(principal.principal_id, str) or not principal.principal_id.strip()
    ):
        return Decision(False, action, "PRINCIPAL_ID_REQUIRED")
    return Decision(True, action, "AUTHENTICATED_SCOPE", principal.principal_id or "")


def authorize_service_mutation(action: Any, principal: Any) -> Decision:
    """Authorize a versioned internal state mutation using a sealed principal.

    There is intentionally no actor-id or authenticated-boolean fallback.
    The caller must carry the exact configured scope for this service action.
    """
    if not isinstance(action, str) or action not in SERVICE_MUTATION_ACTIONS:
        return Decision(False, action if isinstance(action, str) else "", "NOT_ALLOWLISTED")
    if not isinstance(principal, AuthenticatedPrincipal):
        return Decision(False, action, "AUTHENTICATION_REQUIRED")
    if not principal.allows(action):
        return Decision(False, action, "ACTION_NOT_AUTHORIZED")
    if not isinstance(principal.principal_id, str) or not principal.principal_id.strip():
        return Decision(False, action, "PRINCIPAL_ID_REQUIRED")
    return Decision(True, action, "AUTHENTICATED_SCOPE", principal.principal_id)


def issue_mutation_permit(
    action: Any,
    principal: Any,
    *,
    event_type: str,
    actor_id: str,
    payload: dict[str, Any],
    correlation_id: str | None = None,
    causation_id: str | None = None,
    idempotency_key: str | None = None,
    event_id: str | None = None,
    authority_context: dict[str, Any] | None = None,
    evidence_refs: list[str] | None = None,
    sync_required: bool = False,
) -> MutationPermit:
    """Issue a single-use receipt for an exact store mutation after central authorization."""
    decision = authorize_service_mutation(action, principal)
    if not decision.allowed:
        raise PolicyError(decision.reason)
    if not isinstance(actor_id, str) or actor_id != principal.principal_id:
        raise PolicyError("MUTATION_ACTOR_PRINCIPAL_MISMATCH")
    if not isinstance(event_type, str) or not event_type:
        raise PolicyError("MUTATION_EVENT_TYPE_INVALID")
    required_action = MUTATION_EVENT_ACTIONS.get(event_type, "audit.append")
    if required_action != action:
        raise PolicyError("MUTATION_EVENT_ACTION_MISMATCH")
    if not isinstance(payload, dict):
        raise PolicyError("MUTATION_PAYLOAD_INVALID")
    if not isinstance(correlation_id, str) or not correlation_id.strip():
        raise PolicyError("MUTATION_CORRELATION_REQUIRED")
    if idempotency_key is not None and (not isinstance(idempotency_key, str) or not idempotency_key.strip()):
        raise PolicyError("MUTATION_IDEMPOTENCY_INVALID")
    if causation_id is not None and (not isinstance(causation_id, str) or not causation_id.strip()):
        raise PolicyError("MUTATION_CAUSATION_INVALID")
    if event_id is not None and (not isinstance(event_id, str) or not event_id.strip()):
        raise PolicyError("MUTATION_EVENT_ID_INVALID")
    if evidence_refs is not None and (
        not isinstance(evidence_refs, list)
        or any(not isinstance(ref, str) or not ref.strip() for ref in evidence_refs)
    ):
        raise PolicyError("MUTATION_EVIDENCE_REFS_INVALID")
    if not isinstance(sync_required, bool):
        raise PolicyError("MUTATION_SYNC_REQUIRED_INVALID")
    expected_context = {"principal": principal.principal_id, "scope": action}
    if authority_context != expected_context:
        raise PolicyError("MUTATION_AUTHORITY_CONTEXT_MISMATCH")
    if action == "session.create" and payload.get("principal_id") != principal.principal_id:
        raise PolicyError("SESSION_PAYLOAD_PRINCIPAL_MISMATCH")
    if action == "workflow.task.create":
        if payload.get("correlation_id") != correlation_id or payload.get("idempotency_key") != idempotency_key:
            raise PolicyError("WORKFLOW_CREATE_CORRELATION_OR_IDEMPOTENCY_MISMATCH")
    if action == "workflow.task.transition":
        task = payload.get("task") if isinstance(payload, dict) else None
        if not isinstance(task, dict) or task.get("correlation_id") != correlation_id:
            raise PolicyError("WORKFLOW_TRANSITION_CORRELATION_MISMATCH")
    if action == "policy.approval.request" and payload.get("principal_id") != principal.principal_id:
        raise PolicyError("APPROVAL_REQUESTER_PRINCIPAL_MISMATCH")
    if action == "policy.approval.vote":
        approval = payload.get("approval") if isinstance(payload, dict) else None
        transition = payload.get("transition") if isinstance(payload, dict) else None
        if not isinstance(approval, dict) or not isinstance(transition, dict):
            raise PolicyError("APPROVAL_VOTER_PRINCIPAL_MISMATCH")
        if (
            transition.get("approver_id") != principal.principal_id
            or approval.get("principal_id") == principal.principal_id
            or (
                approval.get("status") in {"APPROVED", "DENIED"}
                and approval.get("decided_by") != principal.principal_id
            )
            or (
                approval.get("status") == "EXPIRED"
                and approval.get("decided_by") is not None
            )
        ):
            raise PolicyError("APPROVAL_VOTER_PRINCIPAL_MISMATCH")
    try:
        payload_digest = canonical_digest(payload)
        authority_digest = canonical_digest(authority_context)
        evidence_refs_digest = canonical_digest(evidence_refs)
    except ContractError as exc:
        raise PolicyError("MUTATION_ENVELOPE_INVALID") from exc
    nonce = uuid.uuid4().hex
    expires_at = time.monotonic() + _MUTATION_PERMIT_TTL_SECONDS
    permit = MutationPermit(
        nonce, action, event_type, actor_id, actor_id, payload_digest,
        correlation_id, causation_id, idempotency_key, event_id, authority_digest,
        evidence_refs_digest, sync_required, expires_at, _MUTATION_PERMIT_SEAL,
    )
    with _MUTATION_PERMIT_LOCK:
        now = time.monotonic()
        for stale_nonce, stale in list(_ISSUED_MUTATION_PERMITS.items()):
            if stale.expires_at_monotonic <= now:
                del _ISSUED_MUTATION_PERMITS[stale_nonce]
        if len(_ISSUED_MUTATION_PERMITS) >= _MUTATION_PERMIT_MAX_PENDING:
            raise PolicyError("MUTATION_PERMIT_REGISTRY_FULL")
        _ISSUED_MUTATION_PERMITS[nonce] = permit
    return permit


def consume_mutation_permit(
    permit: Any,
    *,
    event_type: str,
    actor_id: str | None,
    payload: dict[str, Any],
    correlation_id: str | None = None,
    causation_id: str | None = None,
    idempotency_key: str | None = None,
    event_id: str | None = None,
    authority_context: dict[str, Any] | None = None,
    evidence_refs: list[str] | None = None,
    sync_required: bool = False,
) -> bool:
    """Validate and consume the exact issued receipt; mismatches never authorize."""
    if not isinstance(event_type, str) or not event_type:
        return False
    if not isinstance(permit, MutationPermit) or permit._seal is not _MUTATION_PERMIT_SEAL:
        return False
    if not isinstance(sync_required, bool):
        return False
    if evidence_refs is not None and (
        not isinstance(evidence_refs, list)
        or any(not isinstance(ref, str) or not ref.strip() for ref in evidence_refs)
    ):
        return False
    if causation_id is not None and (not isinstance(causation_id, str) or not causation_id.strip()):
        return False
    try:
        payload_digest = canonical_digest(payload)
        authority_digest = canonical_digest(authority_context)
        evidence_refs_digest = canonical_digest(evidence_refs)
    except (ContractError, TypeError, ValueError):
        return False
    with _MUTATION_PERMIT_LOCK:
        registered = _ISSUED_MUTATION_PERMITS.get(permit.nonce)
        if registered is not permit:
            return False
        # Every presented receipt is one-shot: a mismatch also burns it, preventing retry
        # of the same receipt after an attempted substitution. Services must mint a fresh
        # permit for a fresh, fully validated operation.
        del _ISSUED_MUTATION_PERMITS[permit.nonce]
        if permit.expires_at_monotonic <= time.monotonic():
            return False
        return (
            permit.action == MUTATION_EVENT_ACTIONS.get(event_type, "audit.append")
            and permit.event_type == event_type
            and permit.actor_id == actor_id
            and permit.principal_id == actor_id
            and permit.payload_digest == payload_digest
            and permit.correlation_id == correlation_id
            and permit.causation_id == causation_id
            and permit.idempotency_key == idempotency_key
            and permit.event_id == event_id
            and permit.authority_digest == authority_digest
            and permit.evidence_refs_digest == evidence_refs_digest
            and permit.sync_required == sync_required
        )


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
    base = _authorize_base_action(action, authenticated=True)
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
    if not isinstance(result["action"], str) or result["action"] not in APPROVABLE_ACTIONS or result["action"] in FORBIDDEN:
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
    if not isinstance(action, str) or action not in APPROVABLE_ACTIONS or action in FORBIDDEN:
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
    request_digest: str,
) -> Decision:
    """Allow only an unexpired approval for the exact principal/action/resource/request digest."""
    base = _authorize_base_action(action, authenticated=True)
    if not base.allowed:
        return Decision(False, base.action, base.reason, principal_id if isinstance(principal_id, str) else "")
    if not isinstance(principal_id, str) or not principal_id.strip():
        return Decision(False, action, "PRINCIPAL_REQUIRED")
    if not isinstance(request_digest, str) or not _DIGEST_RE.fullmatch(request_digest):
        return Decision(False, action, "REQUEST_DIGEST_INVALID", principal_id)
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
            and approval["request_digest"] == request_digest
            and approval["decided_by"] != approval["principal_id"]
            and float(now) < approval["expires_at"]
        ):
            return Decision(True, action, "APPROVED_REQUEST", principal_id, approval["approval_id"])
    return Decision(False, action, "APPROVAL_REQUIRED", principal_id)


class ApprovalService:
    """Persist approval requests and decisions through the transactional HG2 state store."""

    def __init__(self, store, *, clock, principal=None):
        self.store = store
        self.clock = clock
        self.principal = principal

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
        decision = authorize_service_mutation("policy.approval.request", self.principal)
        if not decision.allowed:
            raise PolicyError(decision.reason)
        if principal_id != getattr(self.principal, "principal_id", None):
            raise PolicyError("APPROVAL_REQUESTER_PRINCIPAL_MISMATCH")
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
        correlation = uuid.uuid4().hex
        context = {"principal": principal_id, "scope": "policy.approval.request"}
        permit = issue_mutation_permit(
            "policy.approval.request", self.principal, event_type="policy.approval.created",
            actor_id=principal_id, payload=request, correlation_id=correlation,
            idempotency_key=idempotency_key, authority_context=context,
            sync_required=sync_required,
        )
        self.store.emit(
            "policy.approval.created", request, correlation_id=correlation, actor_id=principal_id,
            authority_context=context, idempotency_key=idempotency_key, sync_required=sync_required,
            mutation_permit=permit,
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
        authz = authorize_service_mutation("policy.approval.vote", self.principal)
        if not authz.allowed:
            raise PolicyError(authz.reason)
        requested_decision = decision
        if approver_id != getattr(self.principal, "principal_id", None):
            raise PolicyError("APPROVER_PRINCIPAL_MISMATCH")
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
                and transition.get("decision") == requested_decision
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
        correlation = "approval:" + approval_id + ":decision:" + str(expected_version + 1)
        context = {"principal": approver_id, "scope": "policy.approval.vote"}
        permit = issue_mutation_permit(
            "policy.approval.vote", self.principal, event_type="policy.approval.decided",
            actor_id=approver_id, payload=payload, correlation_id=correlation,
            idempotency_key=transition_key, authority_context=context,
            sync_required=sync_required,
        )
        self.store.emit(
            "policy.approval.decided", payload, correlation_id=correlation, actor_id=approver_id,
            authority_context=context, idempotency_key=transition_key, sync_required=sync_required,
            mutation_permit=permit,
        )
        return updated
