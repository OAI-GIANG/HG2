"""Read-only contract for a runtime's canonical event-state boundary.

This protocol intentionally describes observation, not mutation. StateStore and
SQLiteStateStore have different write authorization and recovery semantics; this
module does not make them drop-in interchangeable and does not perform migration.
DurableTransactionStore is a separate transaction ledger, not a runtime event store.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


CONTRACT_VERSION = "HG_RUNTIME_STATE_BOUNDARY_V1"


@runtime_checkable
class RuntimeStateBoundary(Protocol):
    """Minimum read-only surface required to inspect one canonical state owner."""

    runtime_id: str

    def replay(self) -> list[dict[str, Any]]: ...

    def verify(self) -> dict[str, Any]: ...

    def audit_export(self) -> dict[str, Any]: ...


def inspect_runtime_state_boundary(store: RuntimeStateBoundary) -> dict[str, Any]:
    """Fail closed unless a backend proves a stable identity and valid event chain."""
    runtime_id = getattr(store, "runtime_id", None)
    if not isinstance(runtime_id, str) or not runtime_id.strip():
        raise ValueError("RUNTIME_STATE_IDENTITY_MISSING")
    verify = store.verify()
    if not isinstance(verify, dict) or verify.get("ok") is not True:
        raise ValueError("RUNTIME_STATE_INTEGRITY_NOT_VERIFIED")
    events = store.replay()
    if not isinstance(events, list) or any(not isinstance(item, dict) for item in events):
        raise ValueError("RUNTIME_STATE_REPLAY_INVALID")
    exported = store.audit_export()
    if not isinstance(exported, dict) or exported.get("runtime_id") != runtime_id:
        raise ValueError("RUNTIME_STATE_EXPORT_IDENTITY_MISMATCH")
    if exported.get("events") != len(events):
        raise ValueError("RUNTIME_STATE_EXPORT_COUNT_MISMATCH")
    if verify.get("events") != len(events):
        raise ValueError("RUNTIME_STATE_VERIFY_COUNT_MISMATCH")
    return {
        "schema_version": CONTRACT_VERSION,
        "ok": True,
        "runtime_id": runtime_id,
        "events": len(events),
        "verification": verify,
        "read_only": True,
        "migration_performed": False,
    }
