"""Provenance-aware memory classification; no automatic fact promotion.

This module records trust metadata supplied by a caller but does not authenticate that
metadata. Only an external verified-trust adapter could promote a memory item.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from itertools import islice
from typing import Any, Callable, Iterable

from .task_contract import canonical_json

_TRUST_LEVELS = ("UNVERIFIED", "CORROBORATED", "VERIFIED", "REVOKED")
_SENSITIVITY = frozenset({"PUBLIC", "INTERNAL", "CONFIDENTIAL", "SECRET"})
_MEMORY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class MemoryError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _text(value: Any, field: str, max_len: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        raise MemoryError("MEMORY_SCHEMA_INVALID", field)
    return value


def create_memory_record(
    *,
    memory_id: str,
    statement: str,
    source_ref: str | None,
    source_digest: str | None,
    authority_ref: str | None,
    observed_at: str | None,
    expires_at: str | None,
    memory_key: str | None = None,
    sensitivity: str = "INTERNAL",
    parent_memory_ids: Iterable[str] = (),
    supplied_trust_level: str = "UNVERIFIED",
) -> dict[str, Any]:
    """Create untrusted memory metadata. Caller labels cannot promote trust."""
    _text(memory_id, "memory_id", 128)
    if not _MEMORY_ID_RE.fullmatch(memory_id):
        raise MemoryError("MEMORY_SCHEMA_INVALID", "memory_id syntax")
    _text(statement, "statement")
    if not isinstance(sensitivity, str) or sensitivity not in _SENSITIVITY:
        raise MemoryError("MEMORY_SCHEMA_INVALID", "sensitivity")
    if not isinstance(supplied_trust_level, str) or supplied_trust_level not in _TRUST_LEVELS:
        raise MemoryError("MEMORY_SCHEMA_INVALID", "supplied_trust_level")
    problems = []
    if source_ref is not None and (not isinstance(source_ref, str) or not source_ref.strip() or len(source_ref) > 1024):
        raise MemoryError("MEMORY_SCHEMA_INVALID", "source_ref")
    if not source_ref:
        problems.append("SOURCE_MISSING")
    if source_digest is not None and not isinstance(source_digest, str):
        raise MemoryError("MEMORY_SCHEMA_INVALID", "source_digest must be string or null")
    if not source_digest or len(source_digest) != 64 or any(c not in "0123456789abcdef" for c in source_digest):
        problems.append("SOURCE_DIGEST_MISSING_OR_INVALID")
    if authority_ref is not None and (not isinstance(authority_ref, str) or not authority_ref.strip() or len(authority_ref) > 1024):
        raise MemoryError("MEMORY_SCHEMA_INVALID", "authority_ref")
    if not authority_ref:
        problems.append("AUTHORITY_MISSING")
    if observed_at is not None and (not isinstance(observed_at, str) or not observed_at.strip()):
        raise MemoryError("MEMORY_SCHEMA_INVALID", "observed_at")
    if expires_at is not None and (not isinstance(expires_at, str) or not expires_at.strip()):
        raise MemoryError("MEMORY_SCHEMA_INVALID", "expires_at")
    if not observed_at:
        problems.append("OBSERVATION_TIME_MISSING")
    if not expires_at:
        problems.append("EXPIRY_POLICY_MISSING")
    try:
        parent_iter = iter(parent_memory_ids)
        parents_raw = list(islice(parent_iter, 4097))
    except TypeError as exc:
        raise MemoryError("MEMORY_SCHEMA_INVALID", "parent_memory_ids must be iterable") from exc
    if len(parents_raw) > 4096:
        raise MemoryError("MEMORY_RESOURCE_LIMIT", "too many parent_memory_ids")
    if any(not isinstance(item, str) or not _MEMORY_ID_RE.fullmatch(item) for item in parents_raw):
        raise MemoryError("MEMORY_SCHEMA_INVALID", "parent_memory_ids")
    parents = sorted(set(parents_raw))
    if observed_at:
        try:
            observed_dt = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise MemoryError("MEMORY_SCHEMA_INVALID", "observed_at") from exc
        if observed_dt.tzinfo is None or observed_dt.utcoffset() is None:
            raise MemoryError("MEMORY_SCHEMA_INVALID", "observed_at timezone required")
    else:
        observed_dt = None
    if expires_at:
        try:
            expiry_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise MemoryError("MEMORY_SCHEMA_INVALID", "expires_at") from exc
        if expiry_dt.tzinfo is None or expiry_dt.utcoffset() is None:
            raise MemoryError("MEMORY_SCHEMA_INVALID", "expires_at timezone required")
        if observed_dt is not None and expiry_dt <= observed_dt:
            raise MemoryError("MEMORY_SCHEMA_INVALID", "expiry must follow observation")
    if memory_key is not None:
        _text(memory_key, "memory_key", 256)
    value_digest = hashlib.sha256(statement.encode("utf-8")).hexdigest()
    record = {
        "schema_version": "hg.provenance-memory.v1",
        "memory_id": memory_id,
        "memory_key": memory_key,
        "statement": statement,
        "value_digest": value_digest,
        "source_ref": source_ref,
        "source_digest": source_digest,
        "authority_ref": authority_ref,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "sensitivity": sensitivity,
        "parent_memory_ids": parents,
        "trust_level": "UNVERIFIED" if supplied_trust_level != "REVOKED" else "REVOKED",
        "source_trust_claim": supplied_trust_level,
        "blockers": sorted(set(problems)),
    }
    record["record_digest"] = hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()
    return record


def assess_memory(
    record: dict[str, Any], *, known_authority_refs: set[str] | None = None,
    provenance_verifier: Callable[[dict[str, Any]], tuple[bool, str]] | None = None,
) -> dict[str, Any]:
    if type(record) is not dict or record.get("schema_version") != "hg.provenance-memory.v1":
        return {"trusted": False, "status": "UNVERIFIED", "reasons": ["MEMORY_SCHEMA_INVALID"]}
    reasons = list(record.get("blockers", []))
    supplied_digest = record.get("record_digest")
    unsigned = dict(record)
    unsigned.pop("record_digest", None)
    actual_digest = hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()
    if not isinstance(supplied_digest, str) or supplied_digest != actual_digest:
        reasons.append("MEMORY_RECORD_DIGEST_MISMATCH")
    if known_authority_refs is None or record.get("authority_ref") not in known_authority_refs:
        reasons.append("AUTHORITY_NOT_VERIFIED")
    if record.get("trust_level") == "REVOKED":
        return {"trusted": False, "status": "REVOKED", "reasons": sorted(set(reasons or ["MEMORY_REVOKED"]))}
    if provenance_verifier is None:
        reasons.append("PROVENANCE_VERIFIER_UNAVAILABLE")
    elif not reasons:
        try:
            decision = provenance_verifier(dict(record))
            if type(decision) is not tuple or len(decision) != 2 or type(decision[0]) is not bool or not isinstance(decision[1], str) or not decision[1].strip():
                reasons.append("PROVENANCE_VERIFIER_INVALID_RESPONSE")
            elif not decision[0]:
                reasons.append("SOURCE_PROVENANCE_NOT_VERIFIED")
            else:
                reasons.append("PROVENANCE_ADAPTER_NOT_BOUND_TO_TRUST_ROOT")
                return {"trusted": False, "status": "UNVERIFIED", "reasons": sorted(set(reasons)),
                        "provenance_adapter_reported_pass": True,
                        "provenance_decision_ref": decision[1]}
        except Exception:
            reasons.append("PROVENANCE_VERIFIER_ERROR")
    return {"trusted": False, "status": "UNVERIFIED", "reasons": sorted(set(reasons))}


def detect_memory_conflicts(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect exact-key conflicts only; never choose a winner implicitly."""
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        if type(record) is not dict:
            continue
        source = record.get("source_ref")
        key = record.get("memory_key")
        value_digest = record.get("value_digest")
        if not isinstance(source, str) or not isinstance(key, str) or not isinstance(value_digest, str):
            continue
        by_key.setdefault((source, key), []).append(record)
    conflicts = []
    for (source, key), group in sorted(by_key.items()):
        digests = sorted({r["value_digest"] for r in group})
        if len(digests) > 1:
            conflicts.append({"source_ref": source, "memory_key": key,
                              "value_digests": digests, "status": "CONFLICT_UNRESOLVED"})
    return conflicts
class SQLiteProvenanceMemoryStore:
    """Durable append-preserving memory store; trust remains external to storage.

    PUBLIC/INTERNAL records can be stored. CONFIDENTIAL/SECRET records are rejected
    until an independently trusted encryption-at-rest adapter is specified.
    """

    def __init__(self, db_path: str, *, max_records: int = 100_000, busy_timeout_ms: int = 10_000) -> None:
        import os
        import sqlite3
        from contextlib import contextmanager

        self.db_path = os.fspath(db_path)
        if not self.db_path or self.db_path == ":memory:":
            raise MemoryError("MEMORY_STORAGE_INVALID", "durable file-backed database required")
        if type(max_records) is not int or not 1 <= max_records <= 1_000_000:
            raise MemoryError("MEMORY_RESOURCE_LIMIT", "invalid max_records")
        if type(busy_timeout_ms) is not int or not 100 <= busy_timeout_ms <= 120_000:
            raise MemoryError("MEMORY_RESOURCE_LIMIT", "invalid busy_timeout_ms")
        self.max_records = max_records
        self.busy_timeout_ms = busy_timeout_ms
        self._sqlite3 = sqlite3
        self._contextmanager = contextmanager

        with self._connection() as db:
            try:
                journal = db.execute("PRAGMA journal_mode=WAL").fetchone()[0]
                if str(journal).lower() != "wal":
                    raise MemoryError("MEMORY_STORAGE_UNAVAILABLE", "SQLite WAL mode unavailable")
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, 1):
                    raise MemoryError("MEMORY_SCHEMA_UNSUPPORTED", str(version))
                db.executescript("""
                    CREATE TABLE IF NOT EXISTS hg_memory (
                        memory_id TEXT PRIMARY KEY,
                        memory_key TEXT NOT NULL,
                        source_ref TEXT,
                        value_digest TEXT NOT NULL,
                        sensitivity TEXT NOT NULL,
                        record_digest TEXT NOT NULL,
                        record_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS hg_memory_source_key
                        ON hg_memory(source_ref, memory_key);
                    CREATE TABLE IF NOT EXISTS hg_memory_event (
                        seq INTEGER PRIMARY KEY,
                        memory_id TEXT NOT NULL REFERENCES hg_memory(memory_id),
                        event_type TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        detail_json TEXT NOT NULL,
                        previous_digest TEXT NOT NULL,
                        event_digest TEXT NOT NULL
                    );
                    PRAGMA user_version=1;
                """)
            except MemoryError:
                raise
            except sqlite3.Error as exc:
                raise MemoryError("MEMORY_STORAGE_UNAVAILABLE", str(exc)) from exc

    @property
    def _connection(self):
        @self._contextmanager
        def manager():
            db = self._sqlite3.connect(self.db_path, timeout=self.busy_timeout_ms / 1000,
                                       isolation_level=None, check_same_thread=True)
            try:
                db.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
                db.execute("PRAGMA foreign_keys=ON")
                db.execute("PRAGMA synchronous=FULL")
                yield db
            finally:
                db.close()
        return manager

    @property
    def _atomic(self):
        @self._contextmanager
        def manager():
            with self._connection() as db:
                try:
                    db.execute("BEGIN IMMEDIATE")
                    yield db
                    db.commit()
                except self._sqlite3.Error as exc:
                    db.rollback()
                    raise MemoryError("MEMORY_STORAGE_UNAVAILABLE", str(exc)) from exc
                except Exception:
                    db.rollback()
                    raise
        return manager

    @staticmethod
    def _record_digest(record: dict[str, Any]) -> str:
        unsigned = dict(record)
        unsigned.pop("record_digest", None)
        return hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()

    def _append_event(self, db, memory_id: str, event_type: str, detail: dict[str, Any]) -> None:
        seq = db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM hg_memory_event").fetchone()[0]
        previous = db.execute("SELECT event_digest FROM hg_memory_event ORDER BY seq DESC LIMIT 1").fetchone()
        previous_digest = previous[0] if previous else "0" * 64
        occurred_at = datetime.now().astimezone().isoformat(timespec="microseconds")
        detail_json = canonical_json(detail)
        body = {"seq": seq, "memory_id": memory_id, "event_type": event_type,
                "occurred_at": occurred_at, "detail_json": detail_json,
                "previous_digest": previous_digest}
        digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
        db.execute(
            "INSERT INTO hg_memory_event(seq,memory_id,event_type,occurred_at,detail_json,previous_digest,event_digest) "
            "VALUES(?,?,?,?,?,?,?)",
            (seq, memory_id, event_type, occurred_at, detail_json, previous_digest, digest),
        )

    def put(self, record: dict[str, Any]) -> dict[str, Any]:
        if type(record) is not dict or record.get("schema_version") != "hg.provenance-memory.v1":
            raise MemoryError("MEMORY_SCHEMA_INVALID", "expected provenance memory v1")
        memory_id = _text(record.get("memory_id"), "memory_id", 128)
        memory_key = _text(record.get("memory_key"), "memory_key", 256)
        sensitivity = record.get("sensitivity")
        if not isinstance(sensitivity, str) or sensitivity not in {"PUBLIC", "INTERNAL"}:
            raise MemoryError("MEMORY_SENSITIVITY_BLOCKED", "encrypted storage adapter required for CONFIDENTIAL/SECRET")
        expected_digest = self._record_digest(record)
        if record.get("record_digest") != expected_digest:
            raise MemoryError("MEMORY_RECORD_DIGEST_MISMATCH")
        value_digest = record.get("value_digest")
        if not isinstance(value_digest, str) or len(value_digest) != 64 or any(c not in "0123456789abcdef" for c in value_digest):
            raise MemoryError("MEMORY_SCHEMA_INVALID", "value_digest")
        source_ref = record.get("source_ref")
        if source_ref is not None and (not isinstance(source_ref, str) or len(source_ref) > 1024):
            raise MemoryError("MEMORY_SCHEMA_INVALID", "source_ref")
        record_json = canonical_json(record)
        created_at = datetime.now().astimezone().isoformat(timespec="microseconds")

        with self._atomic() as db:
            existing = db.execute("SELECT record_digest,record_json FROM hg_memory WHERE memory_id=?",
                                   (memory_id,)).fetchone()
            if existing:
                if existing[0] != expected_digest or existing[1] != record_json:
                    raise MemoryError("MEMORY_ID_CONFLICT", memory_id)
                return {"stored": True, "idempotent": True, "memory_id": memory_id,
                        "record_digest": expected_digest, "conflict": False}
            count = db.execute("SELECT COUNT(*) FROM hg_memory").fetchone()[0]
            if count >= self.max_records:
                raise MemoryError("MEMORY_RESOURCE_LIMIT", "record limit reached")
            peers = db.execute(
                "SELECT memory_id,value_digest FROM hg_memory WHERE source_ref IS ? AND memory_key=? ORDER BY memory_id",
                (source_ref, memory_key),
            ).fetchall()
            conflicts = [row[0] for row in peers if row[1] != value_digest]
            db.execute(
                "INSERT INTO hg_memory(memory_id,memory_key,source_ref,value_digest,sensitivity,record_digest,record_json,created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (memory_id, memory_key, source_ref, value_digest, sensitivity, expected_digest, record_json, created_at),
            )
            self._append_event(db, memory_id, "MEMORY_CONFLICT" if conflicts else "MEMORY_STORED",
                               {"record_digest": expected_digest, "memory_id": memory_id,
                                "memory_key": memory_key, "source_ref": source_ref,
                                "value_digest": value_digest, "sensitivity": sensitivity,
                                "conflicting_memory_ids": conflicts, "trust_level": "UNVERIFIED"})
            return {"stored": True, "idempotent": False, "memory_id": memory_id,
                    "record_digest": expected_digest, "conflict": bool(conflicts),
                    "conflicting_memory_ids": conflicts, "trust_level": "UNVERIFIED"}

    def get(self, memory_id: str) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute("SELECT record_json FROM hg_memory WHERE memory_id=?", (memory_id,)).fetchone()
        if row is None:
            raise MemoryError("MEMORY_NOT_FOUND", memory_id)
        try:
            record = json.loads(row[0])
        except (ValueError, TypeError) as exc:
            raise MemoryError("MEMORY_STORED_RECORD_INVALID", memory_id) from exc
        if type(record) is not dict:
            raise MemoryError("MEMORY_STORED_RECORD_INVALID", memory_id)
        if self._record_digest(record) != record.get("record_digest"):
            raise MemoryError("MEMORY_RECORD_DIGEST_MISMATCH", memory_id)
        return record

    def list_conflicts(self) -> list[dict[str, Any]]:
        with self._connection() as db:
            rows = db.execute(
                "SELECT source_ref,memory_key,memory_id,value_digest FROM hg_memory "
                "ORDER BY source_ref,memory_key,memory_id"
            ).fetchall()
        grouped: dict[tuple[str | None, str], list[tuple[str, str]]] = {}
        for source_ref, memory_key, memory_id, value_digest in rows:
            grouped.setdefault((source_ref, memory_key), []).append((memory_id, value_digest))
        conflicts = []
        for (source_ref, memory_key), items in sorted(grouped.items(), key=lambda item: (item[0][0] or "", item[0][1])):
            digests = {item[1] for item in items}
            if len(digests) > 1:
                conflicts.append({"source_ref": source_ref, "memory_key": memory_key,
                                  "memory_ids": sorted(item[0] for item in items),
                                  "value_digests": sorted(digests), "status": "CONFLICT_UNRESOLVED"})
        return conflicts


    def events(self) -> list[dict[str, Any]]:
        with self._connection() as db:
            rows = db.execute(
                "SELECT seq,memory_id,event_type,occurred_at,detail_json,previous_digest,event_digest "
                "FROM hg_memory_event ORDER BY seq"
            ).fetchall()
        events = []
        for row in rows:
            try:
                detail = json.loads(row[4])
                parse_error = False
            except (ValueError, TypeError):
                detail = None
                parse_error = True
            events.append({"seq": row[0], "memory_id": row[1], "event_type": row[2],
                           "occurred_at": row[3], "detail": detail, "detail_parse_error": parse_error,
                           "previous_digest": row[5], "event_digest": row[6]})
        return events

    def verify_store_integrity(self) -> dict[str, Any]:
        """Cross-check stored memory rows against their initial immutable store events."""
        chain = self.verify_event_chain()
        if not chain["ok"]:
            return chain
        events = self.events()
        first_events: dict[str, dict[str, Any]] = {}
        for event in events:
            if event["event_type"] in {"MEMORY_STORED", "MEMORY_CONFLICT"}:
                if event["memory_id"] in first_events:
                    return {"ok": False, "reason": "MEMORY_DUPLICATE_STORE_EVENT", "memory_id": event["memory_id"]}
                first_events[event["memory_id"]] = event
        with self._connection() as db:
            rows = db.execute(
                "SELECT memory_id,memory_key,source_ref,value_digest,sensitivity,record_digest "
                "FROM hg_memory ORDER BY memory_id"
            ).fetchall()
        row_ids = {row[0] for row in rows}
        if row_ids != set(first_events):
            return {"ok": False, "reason": "MEMORY_EVENT_PROJECTION_MISSING",
                    "stored_records": len(row_ids), "store_events": len(first_events)}
        for row in rows:
            memory_id = row[0]
            try:
                record = self.get(memory_id)
            except MemoryError as exc:
                return {"ok": False, "reason": "MEMORY_STORED_RECORD_INVALID",
                        "memory_id": memory_id, "detail": exc.code}
            event = first_events[memory_id]
            detail = event.get("detail")
            expected = {"record_digest": row[5], "memory_id": row[0], "memory_key": row[1],
                        "source_ref": row[2], "value_digest": row[3], "sensitivity": row[4],
                        "trust_level": "UNVERIFIED"}
            row_matches = (record.get("memory_id") == row[0] and record.get("memory_key") == row[1] and
                           record.get("source_ref") == row[2] and record.get("value_digest") == row[3] and
                           record.get("sensitivity") == row[4] and record.get("record_digest") == row[5])
            if type(detail) is not dict or any(detail.get(key) != value for key, value in expected.items()) or not row_matches:
                return {"ok": False, "reason": "MEMORY_EVENT_PROJECTION_MISMATCH", "memory_id": memory_id}
        return {"ok": True, "records_checked": len(rows), "verified_events": chain["verified_events"],
                "head_digest": chain["head_digest"]}

    def verify_event_chain(self) -> dict[str, Any]:
        events = self.events()
        previous = "0" * 64
        for index, event in enumerate(events, 1):
            if event.get("detail_parse_error") or type(event.get("detail")) is not dict:
                return {"ok": False, "reason": "MEMORY_EVENT_DETAIL_INVALID",
                        "failed_seq": event["seq"], "verified_events": index - 1}
            if event["seq"] != index or event["previous_digest"] != previous:
                return {"ok": False, "reason": "MEMORY_EVENT_CHAIN_LINK_MISMATCH",
                        "failed_seq": event["seq"], "verified_events": index - 1}
            body = {"seq": event["seq"], "memory_id": event["memory_id"],
                    "event_type": event["event_type"], "occurred_at": event["occurred_at"],
                    "detail_json": canonical_json(event["detail"]),
                    "previous_digest": event["previous_digest"]}
            digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
            if digest != event["event_digest"]:
                return {"ok": False, "reason": "MEMORY_EVENT_CHAIN_DIGEST_MISMATCH",
                        "failed_seq": event["seq"], "verified_events": index - 1}
            previous = event["event_digest"]
        return {"ok": True, "verified_events": len(events), "head_digest": previous}
