"""Transactional execution protocol model — no user code or side effects are executed.

This is a deterministic in-memory state machine for contract testing, not a durable,
multi-process transaction engine. It deliberately fails closed for external effects.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from .task_contract import canonical_json

TERMINAL = frozenset({"COMMITTED", "ABORTED", "BLOCKED", "IN_DOUBT"})
TRANSITIONS = {
    "NEW": frozenset({"PREPARED", "BLOCKED"}),
    "PREPARED": frozenset({"RUNNING", "ABORTED", "BLOCKED"}),
    "RUNNING": frozenset({"EVIDENCE_PENDING", "ABORTED", "IN_DOUBT"}),
    "EVIDENCE_PENDING": frozenset({"COMMITTED", "ABORTED", "BLOCKED", "IN_DOUBT"}),
}


class TransactionError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass
class TransactionRecord:
    transaction_id: str
    idempotency_key: str
    contract_digest: str
    plan_digest: str
    state: str = "NEW"
    step_ids: tuple[str, ...] = ()
    completed_steps: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    reason: str | None = None


class TransactionCoordinatorModel:
    """In-process test double. It must not be represented as crash-safe or multi-process."""

    def __init__(self, *, max_transactions: int = 10_000) -> None:
        self.max_transactions = max_transactions
        self._by_key: dict[str, TransactionRecord] = {}
        self._events: list[dict[str, Any]] = []

    def _event(self, transaction: TransactionRecord, event_type: str, detail: dict[str, Any] | None = None) -> None:
        body = {"sequence": len(self._events) + 1, "transaction_id": transaction.transaction_id,
                "idempotency_key": transaction.idempotency_key, "event_type": event_type,
                "state": transaction.state, "detail": detail or {}}
        body["event_digest"] = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
        self._events.append(body)

    def begin(self, *, transaction_id: str, idempotency_key: str,
              contract_digest: str, plan_digest: str, step_ids: list[str],
              all_steps_declared_pure: bool = False) -> TransactionRecord:
        for name, value in (("transaction_id", transaction_id), ("idempotency_key", idempotency_key),
                            ("contract_digest", contract_digest), ("plan_digest", plan_digest)):
            if not isinstance(value, str) or not value.strip():
                raise TransactionError("TRANSACTION_SCHEMA_INVALID", name)
        if not step_ids or any(not isinstance(x, str) or not x.strip() for x in step_ids):
            raise TransactionError("TRANSACTION_SCHEMA_INVALID", "step_ids must be nonempty strings")
        if len(step_ids) != len(set(step_ids)):
            raise TransactionError("TRANSACTION_DUPLICATE_STEP")
        existing = self._by_key.get(idempotency_key)
        if existing:
            identity = (existing.contract_digest, existing.plan_digest, existing.step_ids)
            incoming = (contract_digest, plan_digest, tuple(step_ids))
            if identity != incoming:
                raise TransactionError("IDEMPOTENCY_KEY_CONFLICT")
            return existing
        if len(self._by_key) >= self.max_transactions:
            raise TransactionError("TRANSACTION_RESOURCE_LIMIT")
        record = TransactionRecord(transaction_id, idempotency_key, contract_digest, plan_digest,
                                   step_ids=tuple(step_ids))
        if not all_steps_declared_pure:
            record.state = "BLOCKED"
            record.reason = "EXECUTION_ADAPTER_UNVERIFIED"
            self._by_key[idempotency_key] = record
            self._event(record, "BLOCKED", {"reason": record.reason})
            return record
        record.state = "PREPARED"
        self._by_key[idempotency_key] = record
        self._event(record, "PREPARED", {"step_count": len(step_ids)})
        return record

    def start(self, idempotency_key: str) -> TransactionRecord:
        record = self._get(idempotency_key)
        self._transition(record, "RUNNING")
        self._event(record, "RUNNING")
        return record

    def record_step(self, idempotency_key: str, step_id: str, *, succeeded: bool) -> TransactionRecord:
        record = self._get(idempotency_key)
        if record.state != "RUNNING":
            raise TransactionError("TRANSACTION_INVALID_STATE", record.state)
        if step_id not in record.step_ids:
            raise TransactionError("TRANSACTION_STEP_UNKNOWN", step_id)
        if step_id in record.completed_steps:
            return record
        if not succeeded:
            self._transition(record, "ABORTED")
            record.reason = "STEP_FAILED"
            self._event(record, "ABORTED", {"failed_step": step_id})
            return record
        record.completed_steps = record.completed_steps + (step_id,)
        self._event(record, "STEP_OBSERVED", {"step_id": step_id, "side_effect_performed": False})
        return record

    def evidence_pending(self, idempotency_key: str, evidence_ids: list[str]) -> TransactionRecord:
        record = self._get(idempotency_key)
        if record.state != "RUNNING":
            raise TransactionError("TRANSACTION_INVALID_STATE", record.state)
        if set(record.completed_steps) != set(record.step_ids):
            self._transition(record, "IN_DOUBT")
            record.reason = "NOT_ALL_STEPS_OBSERVED"
            self._event(record, "IN_DOUBT", {"reason": record.reason})
            return record
        record.evidence_ids = tuple(sorted(set(evidence_ids)))
        self._transition(record, "EVIDENCE_PENDING")
        self._event(record, "EVIDENCE_PENDING", {"evidence_ids": list(record.evidence_ids)})
        return record

    def commit(self, idempotency_key: str, *, evidence_verified: bool,
               commit_authorized: bool) -> TransactionRecord:
        record = self._get(idempotency_key)
        if record.state != "EVIDENCE_PENDING":
            raise TransactionError("TRANSACTION_INVALID_STATE", record.state)
        if not evidence_verified or not commit_authorized:
            self._transition(record, "BLOCKED")
            record.reason = "EVIDENCE_OR_COMMIT_AUTHORIZATION_UNVERIFIED"
            self._event(record, "BLOCKED", {"reason": record.reason})
            return record
        self._transition(record, "COMMITTED")
        self._event(record, "COMMITTED", {"side_effect_performed": False})
        return record

    def recover(self, idempotency_key: str) -> TransactionRecord:
        record = self._get(idempotency_key)
        if record.state in {"RUNNING", "EVIDENCE_PENDING"}:
            self._transition(record, "IN_DOUBT")
            record.reason = "DURABLE_RECOVERY_NOT_IMPLEMENTED"
            self._event(record, "IN_DOUBT", {"reason": record.reason})
        return record

    def events(self) -> list[dict[str, Any]]:
        return [dict(e) for e in self._events]

    def _get(self, key: str) -> TransactionRecord:
        if key not in self._by_key:
            raise TransactionError("TRANSACTION_NOT_FOUND", key)
        return self._by_key[key]

    @staticmethod
    def _transition(record: TransactionRecord, target: str) -> None:
        if target not in TRANSITIONS.get(record.state, frozenset()):
            raise TransactionError("TRANSACTION_INVALID_TRANSITION", f"{record.state}->{target}")
        record.state = target
