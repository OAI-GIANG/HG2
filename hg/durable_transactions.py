"""Durable, fail-closed transaction ledger backed by SQLite.

This component persists coordination state and a hash-linked event log. It does not
perform task steps. COMMITTED requires an injected trusted evidence verifier and commit
authorizer; absent adapters, the operation is blocked. Operational durability depends on
the filesystem/storage guarantees of the host and must be validated on the target device.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from itertools import islice
from typing import Any, Callable, Iterable, Iterator

from .task_contract import canonical_json

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_STEPS = 2_000
MAX_EVIDENCE_IDS = 4_096
_STATES = frozenset({"NEW", "PREPARED", "RUNNING", "EVIDENCE_PENDING", "COMMITTED",
                     "ABORTED", "BLOCKED", "IN_DOUBT"})
_TRANSITIONS = {
    "NEW": frozenset({"PREPARED", "BLOCKED"}),
    "PREPARED": frozenset({"RUNNING", "ABORTED", "BLOCKED"}),
    "RUNNING": frozenset({"EVIDENCE_PENDING", "ABORTED", "IN_DOUBT"}),
    "EVIDENCE_PENDING": frozenset({"COMMITTED", "ABORTED", "BLOCKED", "IN_DOUBT"}),
}


class DurableTransactionError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _text(value: Any, name: str, max_len: int = 512) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        raise DurableTransactionError("TRANSACTION_SCHEMA_INVALID", name)
    return value


def _digest(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise DurableTransactionError("TRANSACTION_SCHEMA_INVALID", name + " must be lowercase SHA-256")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class DurableTransactionStore:
    """Single-database coordinator with SQLite serializable write boundaries."""

    def __init__(
        self,
        db_path: str | os.PathLike[str],
        *,
        max_transactions: int = 100_000,
        busy_timeout_ms: int = 10_000,
        prepare_authorizer: Callable[[dict[str, Any]], tuple[bool, str]] | None = None,
        evidence_verifier: Callable[[list[str]], tuple[bool, str]] | None = None,
        commit_authorizer: Callable[[dict[str, Any]], tuple[bool, str]] | None = None,
    ) -> None:
        self.db_path = os.fspath(db_path)
        if not self.db_path or self.db_path == ":memory:":
            raise DurableTransactionError("TRANSACTION_STORAGE_INVALID", "durable file-backed database required")
        if type(max_transactions) is not int or not 1 <= max_transactions <= 1_000_000:
            raise DurableTransactionError("TRANSACTION_RESOURCE_LIMIT", "invalid max_transactions")
        if type(busy_timeout_ms) is not int or not 100 <= busy_timeout_ms <= 120_000:
            raise DurableTransactionError("TRANSACTION_RESOURCE_LIMIT", "invalid busy_timeout_ms")
        self.max_transactions = max_transactions
        self.busy_timeout_ms = busy_timeout_ms
        self._prepare_authorizer = prepare_authorizer
        self._evidence_verifier = evidence_verifier
        self._commit_authorizer = commit_authorizer
        try:
            with self._connect() as db:
                journal = db.execute("PRAGMA journal_mode=WAL").fetchone()[0]
                if str(journal).lower() != "wal":
                    raise DurableTransactionError("TRANSACTION_STORAGE_UNAVAILABLE", "SQLite WAL mode unavailable")
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, 1):
                    raise DurableTransactionError("TRANSACTION_SCHEMA_UNSUPPORTED", str(version))
                db.executescript("""
                    CREATE TABLE IF NOT EXISTS hg_txn (
                        idempotency_key TEXT PRIMARY KEY,
                        transaction_id TEXT NOT NULL UNIQUE,
                        contract_digest TEXT NOT NULL,
                        plan_digest TEXT NOT NULL,
                        state TEXT NOT NULL,
                        step_ids_json TEXT NOT NULL,
                        completed_steps_json TEXT NOT NULL,
                        evidence_ids_json TEXT NOT NULL,
                        reason TEXT,
                        version INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS hg_txn_event (
                        seq INTEGER PRIMARY KEY,
                        idempotency_key TEXT NOT NULL REFERENCES hg_txn(idempotency_key),
                        event_type TEXT NOT NULL,
                        state TEXT NOT NULL,
                        detail_json TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        previous_digest TEXT NOT NULL,
                        event_digest TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS hg_txn_event_key_seq
                        ON hg_txn_event(idempotency_key, seq);
                    PRAGMA user_version=1;
                """)
        except DurableTransactionError:
            raise
        except sqlite3.Error as exc:
            raise DurableTransactionError("TRANSACTION_STORAGE_UNAVAILABLE", str(exc)) from exc

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.db_path, timeout=self.busy_timeout_ms / 1000,
                             isolation_level=None, check_same_thread=True)
        try:
            db.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            yield db
        finally:
            db.close()

    @contextmanager
    def _atomic(self) -> Iterator[sqlite3.Connection]:
        with self._connect() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                yield db
                db.commit()
            except sqlite3.Error as exc:
                db.rollback()
                raise DurableTransactionError("TRANSACTION_STORAGE_UNAVAILABLE", str(exc)) from exc
            except Exception:
                db.rollback()
                raise

    @staticmethod
    def _decode_row(row: tuple[Any, ...]) -> dict[str, Any]:
        try:
            step_ids = json.loads(row[5])
            completed_steps = json.loads(row[6])
            evidence_ids = json.loads(row[7])
        except (ValueError, TypeError) as exc:
            raise DurableTransactionError("TRANSACTION_STORED_RECORD_INVALID", "invalid stored JSON projection") from exc
        if (type(step_ids) is not list or type(completed_steps) is not list or type(evidence_ids) is not list or
                any(not isinstance(item, str) or not item.strip() for items in (step_ids, completed_steps, evidence_ids) for item in items) or
                len(step_ids) > MAX_STEPS or len(completed_steps) > MAX_STEPS or len(evidence_ids) > MAX_EVIDENCE_IDS or
                len(step_ids) != len(set(step_ids)) or len(completed_steps) != len(set(completed_steps)) or
                len(evidence_ids) != len(set(evidence_ids)) or not set(completed_steps).issubset(set(step_ids))):
            raise DurableTransactionError("TRANSACTION_STORED_RECORD_INVALID", "stored projection violates schema")
        if row[4] not in _STATES or type(row[9]) is not int or row[9] < 1:
            raise DurableTransactionError("TRANSACTION_STORED_RECORD_INVALID", "invalid state or version")
        if (not isinstance(row[0], str) or not row[0] or not isinstance(row[1], str) or not row[1] or
                not isinstance(row[2], str) or not _SHA256.fullmatch(row[2]) or
                not isinstance(row[3], str) or not _SHA256.fullmatch(row[3]) or
                (row[8] is not None and not isinstance(row[8], str)) or
                not isinstance(row[10], str) or not isinstance(row[11], str)):
            raise DurableTransactionError("TRANSACTION_STORED_RECORD_INVALID", "invalid stored scalar fields")
        return {
            "idempotency_key": row[0], "transaction_id": row[1],
            "contract_digest": row[2], "plan_digest": row[3], "state": row[4],
            "step_ids": step_ids, "completed_steps": completed_steps,
            "evidence_ids": evidence_ids, "reason": row[8],
            "version": row[9], "created_at": row[10], "updated_at": row[11],
        }

    def _append_event(
        self, db: sqlite3.Connection, key: str, event_type: str, state: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        seq = db.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM hg_txn_event").fetchone()[0]
        previous = db.execute("SELECT event_digest FROM hg_txn_event ORDER BY seq DESC LIMIT 1").fetchone()
        previous_digest = previous[0] if previous else "0" * 64
        occurred_at = _now()
        detail_json = canonical_json(detail or {})
        body = {
            "seq": seq, "idempotency_key": key, "event_type": event_type,
            "state": state, "detail_json": detail_json, "occurred_at": occurred_at,
            "previous_digest": previous_digest,
        }
        digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
        db.execute(
            "INSERT INTO hg_txn_event(seq,idempotency_key,event_type,state,detail_json,occurred_at,previous_digest,event_digest) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (seq, key, event_type, state, detail_json, occurred_at, previous_digest, digest),
        )

    def _transition(self, db: sqlite3.Connection, row: tuple[Any, ...], target: str,
                    event_type: str, *, reason: str | None = None,
                    detail: dict[str, Any] | None = None) -> dict[str, Any]:
        record = self._decode_row(row)
        source = record["state"]
        if target not in _TRANSITIONS.get(source, frozenset()):
            raise DurableTransactionError("TRANSACTION_INVALID_TRANSITION", f"{source}->{target}")
        now = _now()
        version = record["version"] + 1
        cursor = db.execute(
            "UPDATE hg_txn SET state=?, reason=?, version=?, updated_at=? "
            "WHERE idempotency_key=? AND state=? AND version=?",
            (target, reason, version, now, record["idempotency_key"], source, record["version"]),
        )
        if cursor.rowcount != 1:
            raise DurableTransactionError("TRANSACTION_CAS_CONFLICT", record["idempotency_key"])
        self._append_event(db, record["idempotency_key"], event_type, target, detail or {})
        updated = db.execute("SELECT * FROM hg_txn WHERE idempotency_key=?",
                             (record["idempotency_key"],)).fetchone()
        return self._decode_row(updated)

    def begin(
        self,
        *,
        transaction_id: str,
        idempotency_key: str,
        contract_digest: str,
        plan_digest: str,
        step_ids: Iterable[str],
        declaration_only: bool = True,
    ) -> dict[str, Any]:
        transaction_id = _text(transaction_id, "transaction_id", 128)
        idempotency_key = _text(idempotency_key, "idempotency_key", 256)
        contract_digest = _digest(contract_digest, "contract_digest")
        plan_digest = _digest(plan_digest, "plan_digest")
        try:
            step_list = list(islice(iter(step_ids), MAX_STEPS + 1))
        except TypeError as exc:
            raise DurableTransactionError("TRANSACTION_SCHEMA_INVALID", "step_ids must be iterable") from exc
        if not step_list or len(step_list) > MAX_STEPS:
            raise DurableTransactionError("TRANSACTION_RESOURCE_LIMIT", "step count outside permitted range")
        if any(not isinstance(x, str) or not x.strip() or len(x) > 128 for x in step_list):
            raise DurableTransactionError("TRANSACTION_SCHEMA_INVALID", "step IDs must be nonempty strings")
        if len(step_list) != len(set(step_list)):
            raise DurableTransactionError("TRANSACTION_DUPLICATE_STEP")
        if type(declaration_only) is not bool:
            raise DurableTransactionError("TRANSACTION_SCHEMA_INVALID", "declaration_only must be boolean")
        steps_json = canonical_json(step_list)
        auth_ok = False
        auth_ref = "PREPARE_AUTHORIZER_UNAVAILABLE"
        if self._prepare_authorizer is not None:
            try:
                decision = self._prepare_authorizer({
                    "transaction_id": transaction_id, "idempotency_key": idempotency_key,
                    "contract_digest": contract_digest, "plan_digest": plan_digest,
                    "step_ids": list(step_list), "declaration_only": declaration_only,
                })
                if type(decision) is tuple and len(decision) == 2 and type(decision[0]) is bool and isinstance(decision[1], str) and decision[1].strip():
                    auth_ok, auth_ref = decision
                else:
                    auth_ref = "PREPARE_AUTHORIZER_INVALID_RESPONSE"
            except Exception:
                auth_ref = "PREPARE_AUTHORIZER_ERROR"
        now = _now()
        with self._atomic() as db:
            row = db.execute("SELECT * FROM hg_txn WHERE idempotency_key=?",
                             (idempotency_key,)).fetchone()
            if row:
                record = self._decode_row(row)
                incoming = (contract_digest, plan_digest, step_list)
                existing = (record["contract_digest"], record["plan_digest"], record["step_ids"])
                if incoming != existing:
                    raise DurableTransactionError("IDEMPOTENCY_KEY_CONFLICT", idempotency_key)
                return record
            duplicate_transaction = db.execute("SELECT idempotency_key FROM hg_txn WHERE transaction_id=?",
                                               (transaction_id,)).fetchone()
            if duplicate_transaction:
                raise DurableTransactionError("TRANSACTION_ID_CONFLICT", transaction_id)
            count = db.execute("SELECT COUNT(*) FROM hg_txn").fetchone()[0]
            if count >= self.max_transactions:
                raise DurableTransactionError("TRANSACTION_RESOURCE_LIMIT", "transaction limit reached")
            reason = None
            state = "PREPARED"
            if not declaration_only:
                state, reason = "BLOCKED", "EXECUTION_ADAPTER_UNVERIFIED"
            elif self._prepare_authorizer is None:
                state, reason = "BLOCKED", "PREPARE_AUTHORIZER_UNAVAILABLE"
            elif not auth_ok:
                state, reason = "BLOCKED", "PREPARE_NOT_AUTHORIZED"
            db.execute(
                "INSERT INTO hg_txn(idempotency_key,transaction_id,contract_digest,plan_digest,state,"
                "step_ids_json,completed_steps_json,evidence_ids_json,reason,version,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (idempotency_key, transaction_id, contract_digest, plan_digest, state,
                 steps_json, "[]", "[]", reason, 1, now, now),
            )
            self._append_event(db, idempotency_key, state, state,
                               {"reason": reason, "transaction_id": transaction_id,
                                "contract_digest": contract_digest, "plan_digest": plan_digest,
                                "step_count": len(step_list),
                                "step_ids_digest": hashlib.sha256(canonical_json(step_list).encode("utf-8")).hexdigest(),
                                "declaration_only": declaration_only, "prepare_decision_ref": auth_ref,
                                "prepare_authorized": auth_ok})
            row = db.execute("SELECT * FROM hg_txn WHERE idempotency_key=?",
                             (idempotency_key,)).fetchone()
            return self._decode_row(row)

    def get(self, idempotency_key: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM hg_txn WHERE idempotency_key=?",
                             (idempotency_key,)).fetchone()
        if row is None:
            raise DurableTransactionError("TRANSACTION_NOT_FOUND", idempotency_key)
        return self._decode_row(row)

    def start(self, idempotency_key: str) -> dict[str, Any]:
        with self._atomic() as db:
            row = db.execute("SELECT * FROM hg_txn WHERE idempotency_key=?",
                             (idempotency_key,)).fetchone()
            if row is None:
                raise DurableTransactionError("TRANSACTION_NOT_FOUND", idempotency_key)
            record = self._decode_row(row)
            if not record["reason"] and record["state"] == "PREPARED":
                pass
            elif record["state"] == "BLOCKED":
                raise DurableTransactionError("TRANSACTION_BLOCKED", record["reason"] or "blocked")
            return self._transition(db, row, "RUNNING", "RUNNING")

    def record_step(self, idempotency_key: str, step_id: str, *, succeeded: bool) -> dict[str, Any]:
        if type(succeeded) is not bool:
            raise DurableTransactionError("TRANSACTION_SCHEMA_INVALID", "succeeded must be boolean")
        with self._atomic() as db:
            row = db.execute("SELECT * FROM hg_txn WHERE idempotency_key=?",
                             (idempotency_key,)).fetchone()
            if row is None:
                raise DurableTransactionError("TRANSACTION_NOT_FOUND", idempotency_key)
            record = self._decode_row(row)
            if record["state"] != "RUNNING":
                raise DurableTransactionError("TRANSACTION_INVALID_STATE", record["state"])
            if step_id not in record["step_ids"]:
                raise DurableTransactionError("TRANSACTION_STEP_UNKNOWN", str(step_id))
            if step_id in record["completed_steps"]:
                return record
            if not succeeded:
                return self._transition(db, row, "ABORTED", "STEP_FAILED", reason="STEP_FAILED",
                                         detail={"failed_step": step_id, "side_effect_performed": False})
            completed = record["completed_steps"] + [step_id]
            cursor = db.execute(
                "UPDATE hg_txn SET completed_steps_json=?, version=version+1, updated_at=? "
                "WHERE idempotency_key=? AND state='RUNNING' AND version=?",
                (canonical_json(completed), _now(), idempotency_key, record["version"]),
            )
            if cursor.rowcount != 1:
                raise DurableTransactionError("TRANSACTION_CAS_CONFLICT", idempotency_key)
            self._append_event(db, idempotency_key, "STEP_OBSERVED", "RUNNING",
                               {"step_id": step_id, "side_effect_performed": False})
            updated = db.execute("SELECT * FROM hg_txn WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            return self._decode_row(updated)

    def evidence_pending(self, idempotency_key: str, evidence_ids: Iterable[str]) -> dict[str, Any]:
        try:
            ids = list(islice(iter(evidence_ids), MAX_EVIDENCE_IDS + 1))
        except TypeError as exc:
            raise DurableTransactionError("TRANSACTION_EVIDENCE_INVALID", "evidence_ids must be iterable") from exc
        if not ids or len(ids) > MAX_EVIDENCE_IDS or any(not isinstance(x, str) or not x.strip() for x in ids):
            raise DurableTransactionError("TRANSACTION_EVIDENCE_INVALID")
        if len(ids) != len(set(ids)):
            raise DurableTransactionError("TRANSACTION_EVIDENCE_INVALID", "duplicate evidence ID")
        with self._atomic() as db:
            row = db.execute("SELECT * FROM hg_txn WHERE idempotency_key=?",
                             (idempotency_key,)).fetchone()
            if row is None:
                raise DurableTransactionError("TRANSACTION_NOT_FOUND", idempotency_key)
            record = self._decode_row(row)
            if record["state"] != "RUNNING":
                raise DurableTransactionError("TRANSACTION_INVALID_STATE", record["state"])
            if set(record["completed_steps"]) != set(record["step_ids"]):
                return self._transition(db, row, "IN_DOUBT", "IN_DOUBT",
                                         reason="NOT_ALL_STEPS_OBSERVED",
                                         detail={"reason": "NOT_ALL_STEPS_OBSERVED"})
            now = _now()
            cursor = db.execute(
                "UPDATE hg_txn SET state='EVIDENCE_PENDING', evidence_ids_json=?, version=version+1, updated_at=? "
                "WHERE idempotency_key=? AND state='RUNNING' AND version=?",
                (canonical_json(sorted(ids)), now, idempotency_key, record["version"]),
            )
            if cursor.rowcount != 1:
                raise DurableTransactionError("TRANSACTION_CAS_CONFLICT", idempotency_key)
            self._append_event(db, idempotency_key, "EVIDENCE_PENDING", "EVIDENCE_PENDING",
                               {"evidence_ids": sorted(ids)})
            updated = db.execute("SELECT * FROM hg_txn WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            return self._decode_row(updated)

    def commit(self, idempotency_key: str) -> dict[str, Any]:
        snapshot = self.get(idempotency_key)
        if snapshot["state"] != "EVIDENCE_PENDING":
            raise DurableTransactionError("TRANSACTION_INVALID_STATE", snapshot["state"])

        evidence_ok, evidence_ref = False, "EVIDENCE_VERIFIER_UNAVAILABLE"
        evidence_failure = "EVIDENCE_VERIFIER_UNAVAILABLE"
        auth_ok, auth_ref = False, "COMMIT_AUTHORIZER_UNAVAILABLE"
        auth_failure = "COMMIT_AUTHORIZER_UNAVAILABLE"
        if self._evidence_verifier is not None:
            try:
                decision = self._evidence_verifier(snapshot["evidence_ids"])
                if type(decision) is tuple and len(decision) == 2 and type(decision[0]) is bool and isinstance(decision[1], str) and decision[1].strip():
                    evidence_ok, evidence_ref = decision
                    evidence_failure = None if evidence_ok else "EVIDENCE_NOT_VERIFIED"
                else:
                    evidence_ref = "EVIDENCE_VERIFIER_INVALID_RESPONSE"
                    evidence_failure = evidence_ref
            except Exception:
                evidence_ref = "EVIDENCE_VERIFIER_ERROR"
                evidence_failure = evidence_ref
        if evidence_ok:
            if self._commit_authorizer is not None:
                try:
                    decision = self._commit_authorizer(snapshot)
                    if type(decision) is tuple and len(decision) == 2 and type(decision[0]) is bool and isinstance(decision[1], str) and decision[1].strip():
                        auth_ok, auth_ref = decision
                        auth_failure = None if auth_ok else "COMMIT_NOT_AUTHORIZED"
                    else:
                        auth_ref = "COMMIT_AUTHORIZER_INVALID_RESPONSE"
                        auth_failure = auth_ref
                except Exception:
                    auth_ref = "COMMIT_AUTHORIZER_ERROR"
                    auth_failure = auth_ref

        with self._atomic() as db:
            row = db.execute("SELECT * FROM hg_txn WHERE idempotency_key=?",
                             (idempotency_key,)).fetchone()
            if row is None:
                raise DurableTransactionError("TRANSACTION_NOT_FOUND", idempotency_key)
            current = self._decode_row(row)
            if current["version"] != snapshot["version"] or current["state"] != snapshot["state"]:
                raise DurableTransactionError("TRANSACTION_CAS_CONFLICT", idempotency_key)
            if not evidence_ok:
                return self._transition(db, row, "BLOCKED", "BLOCKED",
                                        reason=evidence_failure or "EVIDENCE_NOT_VERIFIED",
                                        detail={"evidence_decision_ref": evidence_ref})
            if not auth_ok:
                return self._transition(db, row, "BLOCKED", "BLOCKED",
                                        reason=auth_failure or "COMMIT_NOT_AUTHORIZED",
                                        detail={"authority_decision_ref": auth_ref})
            return self._transition(db, row, "COMMITTED", "COMMITTED",
                                    detail={"evidence_decision_ref": evidence_ref,
                                            "authority_decision_ref": auth_ref,
                                            "side_effect_performed": False})

    def recover_incomplete(self) -> list[dict[str, Any]]:
        results = []
        with self._atomic() as db:
            keys = [r[0] for r in db.execute(
                "SELECT idempotency_key FROM hg_txn WHERE state IN ('RUNNING','EVIDENCE_PENDING') ORDER BY idempotency_key"
            )]
            for key in keys:
                row = db.execute("SELECT * FROM hg_txn WHERE idempotency_key=?", (key,)).fetchone()
                results.append(self._transition(
                    db, row, "IN_DOUBT", "RECOVERY_IN_DOUBT", reason="PROCESS_RESTART_RECOVERY_REQUIRED",
                    detail={"reason": "PROCESS_RESTART_RECOVERY_REQUIRED"},
                ))
        return results

    def events(self, idempotency_key: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as db:
            if idempotency_key is None:
                rows = db.execute(
                    "SELECT seq,idempotency_key,event_type,state,detail_json,occurred_at,previous_digest,event_digest "
                    "FROM hg_txn_event ORDER BY seq"
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT seq,idempotency_key,event_type,state,detail_json,occurred_at,previous_digest,event_digest "
                    "FROM hg_txn_event WHERE idempotency_key=? ORDER BY seq", (idempotency_key,)
                ).fetchall()
        events = []
        for row in rows:
            try:
                detail = json.loads(row[4])
                parse_error = False
            except (ValueError, TypeError):
                detail = None
                parse_error = True
            events.append({
                "seq": row[0], "idempotency_key": row[1], "event_type": row[2], "state": row[3],
                "detail": detail, "detail_parse_error": parse_error, "occurred_at": row[5],
                "previous_digest": row[6], "event_digest": row[7],
            })
        return events

    def verify_state_integrity(self) -> dict[str, Any]:
        """Cross-check stored transaction projections against the validated event chain."""
        chain = self.verify_event_chain()
        if not chain["ok"]:
            return chain
        events = self.events()
        first: dict[str, dict[str, Any]] = {}
        latest: dict[str, dict[str, Any]] = {}
        counts: dict[str, int] = {}
        for event in events:
            key = event["idempotency_key"]
            first.setdefault(key, event)
            latest[key] = event
            counts[key] = counts.get(key, 0) + 1
        with self._connect() as db:
            rows = db.execute("SELECT * FROM hg_txn ORDER BY idempotency_key").fetchall()
        if {row[0] for row in rows} != set(latest):
            return {"ok": False, "reason": "TRANSACTION_EVENT_PROJECTION_MISSING", "verified_events": chain["verified_events"]}
        for row in rows:
            try:
                record = self._decode_row(row)
            except DurableTransactionError as exc:
                return {"ok": False, "reason": exc.code, "idempotency_key": row[0]}
            key = record["idempotency_key"]
            event = latest.get(key)
            initial = first.get(key)
            initial_detail = initial.get("detail") if initial else None
            expected_steps_digest = hashlib.sha256(canonical_json(record["step_ids"]).encode("utf-8")).hexdigest()
            initial_matches = (type(initial_detail) is dict and
                               initial_detail.get("transaction_id") == record["transaction_id"] and
                               initial_detail.get("contract_digest") == record["contract_digest"] and
                               initial_detail.get("plan_digest") == record["plan_digest"] and
                               initial_detail.get("step_ids_digest") == expected_steps_digest)
            if (event is None or initial is None or record["state"] != event["state"] or
                    record["version"] != counts.get(key) or not initial_matches):
                return {"ok": False, "reason": "TRANSACTION_EVENT_PROJECTION_MISMATCH",
                        "idempotency_key": key, "verified_events": chain["verified_events"]}
        return {"ok": True, "transactions_checked": len(rows), "verified_events": chain["verified_events"],
                "head_digest": chain["head_digest"]}

    def verify_event_chain(self) -> dict[str, Any]:
        events = self.events()
        previous = "0" * 64
        for index, event in enumerate(events, start=1):
            if event.get("detail_parse_error") or type(event.get("detail")) is not dict:
                return {"ok": False, "reason": "EVENT_DETAIL_INVALID",
                        "failed_seq": event["seq"], "verified_events": index - 1}
            if event["seq"] != index or event["previous_digest"] != previous:
                return {"ok": False, "reason": "EVENT_CHAIN_SEQUENCE_OR_LINK_MISMATCH",
                        "failed_seq": event["seq"], "verified_events": index - 1}
            body = {
                "seq": event["seq"], "idempotency_key": event["idempotency_key"],
                "event_type": event["event_type"], "state": event["state"],
                "detail_json": canonical_json(event["detail"]), "occurred_at": event["occurred_at"],
                "previous_digest": event["previous_digest"],
            }
            digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
            if digest != event["event_digest"]:
                return {"ok": False, "reason": "EVENT_CHAIN_DIGEST_MISMATCH",
                        "failed_seq": event["seq"], "verified_events": index - 1}
            previous = event["event_digest"]
        return {"ok": True, "verified_events": len(events), "head_digest": previous}
