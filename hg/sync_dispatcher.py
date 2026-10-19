"""Transport-agnostic dispatcher for the phone-owned transactional outbox."""
from __future__ import annotations

from typing import Any, Mapping, Protocol

from .sqlite_state import SQLiteStateError, SQLiteStateStore
from .auth import AuthenticatedPrincipal
from .policy import authorize_service_mutation, issue_mutation_permit


class SyncTransport(Protocol):
    def send_event(self, event: Mapping[str, Any]) -> Mapping[str, Any]:
        """Send one committed event and return an authenticated relay acknowledgement."""


class SyncDispatcher:
    """Deliver committed outbox events through an injected transport; never owns state."""

    def __init__(self, store: SQLiteStateStore, transport: SyncTransport, *, principal: AuthenticatedPrincipal | None = None):
        self.store = store
        self.transport = transport
        self.principal = principal

    def _authorize(self) -> str | None:
        for action in ("sync.outbox.attempt", "sync.outbox.acknowledge"):
            decision = authorize_service_mutation(action, self.principal)
            if not decision.allowed:
                return decision.reason
        return None

    @staticmethod
    def _valid_ack(ack: Any, item: Mapping[str, Any]) -> bool:
        if not isinstance(ack, Mapping):
            return False
        if set(ack) != {"status", "event_id", "event_digest", "remote_cursor"}:
            return False
        cursor = ack["remote_cursor"]
        return (
            ack["status"] == "ACK"
            and ack["event_id"] == item["event_id"]
            and ack["event_digest"] == item["event_digest"]
            and isinstance(cursor, int)
            and not isinstance(cursor, bool)
            and cursor >= 1
        )

    def dispatch_once(self, *, limit: int = 25) -> dict[str, Any]:
        denial = self._authorize()
        if denial is not None:
            return {"status": "BLOCKED_AUTHORIZATION", "sent": 0, "pending": 0, "reason": denial}
        actor_id = self.principal.principal_id
        try:
            pending = self.store.pending_outbox(limit=limit)
        except SQLiteStateError as exc:
            return {"status": "BLOCKED_INVALID_BATCH", "sent": 0, "pending": 0, "reason": str(exc)}
        if not pending:
            return {"status": "NO_PENDING", "sent": 0, "pending": 0, "reason": "OUTBOX_EMPTY"}

        sent = 0
        for item in pending:
            try:
                attempt_action = "sync.outbox.attempt"
                attempt_context = {"principal": actor_id, "scope": attempt_action}
                attempt_correlation = "outbox-attempt:" + item["event_id"]
                attempt_permit = issue_mutation_permit(
                    attempt_action, self.principal, event_type=attempt_action, actor_id=actor_id,
                    payload={"event_id": item["event_id"]}, correlation_id=attempt_correlation,
                    authority_context=attempt_context,
                )
                self.store.record_outbox_attempt(
                    item["event_id"], actor_id=actor_id, authority_context=attempt_context,
                    correlation_id=attempt_correlation, mutation_permit=attempt_permit,
                )
                ack = self.transport.send_event(item["event"])
            except Exception as exc:
                return {
                    "status": "PARTIAL" if sent else "RETRY_PENDING",
                    "sent": sent,
                    "pending": len(self.store.pending_outbox()),
                    "reason": "TRANSPORT_ERROR_" + type(exc).__name__,
                }
            if not self._valid_ack(ack, item):
                return {
                    "status": "PARTIAL" if sent else "BLOCKED_ACK_INVALID",
                    "sent": sent,
                    "pending": len(self.store.pending_outbox()),
                    "reason": "ACK_SCHEMA_OR_BINDING_INVALID",
                }
            try:
                ack_action = "sync.outbox.acknowledge"
                ack_context = {"principal": actor_id, "scope": ack_action}
                ack_correlation = "outbox-ack:" + item["event_id"] + ":" + str(ack["remote_cursor"])
                ack_permit = issue_mutation_permit(
                    ack_action, self.principal, event_type=ack_action, actor_id=actor_id,
                    payload={"event_id": item["event_id"], "remote_cursor": ack["remote_cursor"]},
                    correlation_id=ack_correlation, authority_context=ack_context,
                )
                self.store.acknowledge_outbox(
                    item["event_id"], ack["remote_cursor"], actor_id=actor_id,
                    authority_context=ack_context, correlation_id=ack_correlation,
                    mutation_permit=ack_permit,
                )
            except SQLiteStateError as exc:
                return {
                    "status": "PARTIAL" if sent else "BLOCKED_CURSOR",
                    "sent": sent,
                    "pending": len(self.store.pending_outbox()),
                    "reason": str(exc),
                }
            sent += 1

        remaining = len(self.store.pending_outbox())
        return {
            "status": "SYNCED" if remaining == 0 else "PARTIAL",
            "sent": sent,
            "pending": remaining,
            "reason": "ACKNOWLEDGED" if remaining == 0 else "BATCH_LIMIT_REACHED",
        }
