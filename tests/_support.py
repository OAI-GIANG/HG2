"""Shared test-only authority helpers for protected durable domain events."""
from __future__ import annotations

from typing import Any
import uuid

from hg.auth import BearerAuthenticator
from hg.policy import issue_mutation_permit


def principal(subject_id: str, scopes):
    token = "test-token:" + subject_id
    return BearerAuthenticator(token, scopes, principal_id=subject_id).authenticate("Bearer " + token)


def authorized_domain_emit(
    store,
    event_type: str,
    payload: dict[str, Any],
    *,
    subject_id: str,
    action: str,
    correlation_id: str | None = None,
    event_id: str | None = None,
    idempotency_key: str | None = None,
    sync_required: bool = False,
    actor_id: str | None = None,
    authority_context: dict[str, Any] | None = None,
):
    """Perform test setup through the same single-use permit boundary as runtime code."""
    actor = subject_id if actor_id is None else actor_id
    if correlation_id is None:
        if idempotency_key is not None:
            correlation_id = "audit-idem:" + subject_id + ":" + idempotency_key
        elif event_id is not None:
            correlation_id = "audit-event:" + subject_id + ":" + event_id
        else:
            correlation_id = uuid.uuid4().hex
    if event_type == "session.created":
        payload = dict(payload)
        payload.setdefault("principal_id", subject_id)
    auth = principal(subject_id, {action})
    context = authority_context if authority_context is not None else {"principal": subject_id, "scope": action}
    permit = issue_mutation_permit(
        action, auth, event_type=event_type, actor_id=actor, payload=payload,
        correlation_id=correlation_id, idempotency_key=idempotency_key,
        event_id=event_id, authority_context=context,
        sync_required=sync_required,
    )
    args = {
        "correlation_id": correlation_id,
        "event_id": event_id,
        "actor_id": actor,
        "authority_context": context,
        "mutation_permit": permit,
    }
    if idempotency_key is not None:
        args["idempotency_key"] = idempotency_key
    if sync_required:
        args["sync_required"] = True
    return store.emit(event_type, payload, **args)


def authorized_outbox_attempt(store, event_id: str, *, subject_id="sync-test"):
    action = "sync.outbox.attempt"
    context = {"principal": subject_id, "scope": action}
    correlation = "outbox-attempt:" + event_id
    permit = issue_mutation_permit(
        action, principal(subject_id, {action}), event_type=action, actor_id=subject_id,
        payload={"event_id": event_id}, correlation_id=correlation, authority_context=context,
    )
    return store.record_outbox_attempt(
        event_id, correlation_id=correlation, actor_id=subject_id,
        authority_context=context, mutation_permit=permit,
    )


def authorized_outbox_ack(store, event_id: str, remote_cursor: int, *, subject_id="sync-test"):
    action = "sync.outbox.acknowledge"
    context = {"principal": subject_id, "scope": action}
    correlation = "outbox-ack:" + event_id + ":" + str(remote_cursor)
    permit = issue_mutation_permit(
        action, principal(subject_id, {action}), event_type=action, actor_id=subject_id,
        payload={"event_id": event_id, "remote_cursor": remote_cursor},
        correlation_id=correlation, authority_context=context,
    )
    return store.acknowledge_outbox(
        event_id, remote_cursor, correlation_id=correlation, actor_id=subject_id, authority_context=context,
        mutation_permit=permit,
    )


def authorized_audit_emit(
    store,
    event_type: str,
    payload: dict[str, Any],
    *,
    subject_id="audit-fixture",
    correlation_id: str | None = None,
    event_id: str | None = None,
    idempotency_key: str | None = None,
    sync_required: bool = False,
):
    """Append non-domain audit/test events through the explicitly scoped audit permit."""
    if correlation_id is None:
        if idempotency_key is not None:
            correlation_id = "audit-idem:" + subject_id + ":" + idempotency_key
        elif event_id is not None:
            correlation_id = "audit-event:" + subject_id + ":" + event_id
        else:
            correlation_id = uuid.uuid4().hex
    action = "audit.append"
    context = {"principal": subject_id, "scope": action}
    permit = issue_mutation_permit(
        action, principal(subject_id, {action}), event_type=event_type,
        actor_id=subject_id, payload=payload, correlation_id=correlation_id,
        idempotency_key=idempotency_key, event_id=event_id, authority_context=context,
        sync_required=sync_required,
    )
    kwargs = {
        "correlation_id": correlation_id, "event_id": event_id,
        "idempotency_key": idempotency_key, "actor_id": subject_id,
        "authority_context": context, "mutation_permit": permit,
    }
    if sync_required:
        if not callable(getattr(store, "pending_outbox", None)):
            raise ValueError("legacy StateStore has no transactional outbox")
        kwargs["sync_required"] = True
    return store.emit(event_type, payload, **kwargs)
