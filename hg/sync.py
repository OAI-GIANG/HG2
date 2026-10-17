"""Transport-agnostic dispatcher for the phone-owned transactional outbox."""
from __future__ import annotations

from typing import Any, Mapping, Protocol

from .sqlite_state import SQLiteStateError, SQLiteStateStore


class SyncTransport(Protocol):
    def send_event(self, event: Mapping[str, Any]) -> Mapping[str, Any]:
        """Send one committed event and return an authenticated relay acknowledgement."""


class SyncDispatcher:
    """Deliver committed outbox events through an injected transport; never owns state."""

    def __init__(self, store: SQLiteStateStore, transport: SyncTransport):
        self.store = store
        self.transport = transport

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
        try:
            pending = self.store.pending_outbox(limit=limit)
        except SQLiteStateError as exc:
            return {"status": "BLOCKED_INVALID_BATCH", "sent": 0, "pending": 0, "reason": str(exc)}
        if not pending:
            return {"status": "NO_PENDING", "sent": 0, "pending": 0, "reason": "OUTBOX_EMPTY"}

        sent = 0
        for item in pending:
            try:
                self.store.record_outbox_attempt(item["event_id"])
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
                self.store.acknowledge_outbox(item["event_id"], ack["remote_cursor"])
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
