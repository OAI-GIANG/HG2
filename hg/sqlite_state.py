"""Transactional SQLite state backend for HG2's phone-owned runtime.

This backend is opt-in until legacy-state migration and runtime cutover are separately verified.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from typing import Any

from .contracts import (
    ContractError,
    SCHEMA_VERSION,
    ZERO_DIGEST,
    canonical_json,
    create_event,
    parse_json_no_duplicate_keys,
    validate_event,
)

_PRODUCT_ID = "HG"
_OWNER_ID = "phone"
_REQUIRED_META = ("runtime_id", "state_owner_id", "last_seq", "head_digest")


class SQLiteStateError(RuntimeError):
    """Raised when the transactional state backend cannot safely continue."""


class IdempotencyConflict(SQLiteStateError):
    """An idempotency key was reused for a different operation."""


class SQLiteStateStore:
    """Append-only, hash-chained events and projections in one SQLite transaction."""

    def __init__(self, directory: str, *, clock=time.time, database_name="hg2-state.sqlite3"):
        self.directory = os.path.abspath(str(directory))
        os.makedirs(self.directory, exist_ok=True)
        self.path = os.path.join(self.directory, database_name)
        self._clock = clock
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            self.path, timeout=5.0, isolation_level=None, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._initialize()
        result = self.verify()
        if not result["ok"]:
            self._conn.close()
            raise SQLiteStateError("state integrity failed: " + result["reason"])
        self.runtime_id = self._meta()["runtime_id"]

    def _meta(self) -> dict[str, str]:
        return {row["key"]: row["value"] for row in self._conn.execute("SELECT key, value FROM metadata")}

    def _set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO metadata(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def _initialize(self) -> None:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute(
                    "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                self._conn.execute(
                    "CREATE TABLE IF NOT EXISTS events ("
                    "sequence INTEGER PRIMARY KEY CHECK(sequence > 0), "
                    "event_id TEXT NOT NULL UNIQUE, idempotency_key TEXT UNIQUE, "
                    "event_type TEXT NOT NULL, event_json TEXT NOT NULL, "
                    "previous_digest TEXT NOT NULL, record_digest TEXT NOT NULL)"
                )
                self._conn.execute(
                    "CREATE TABLE IF NOT EXISTS sessions (session_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL)"
                )
                self._conn.execute(
                    "CREATE TABLE IF NOT EXISTS counters (event_type TEXT PRIMARY KEY, count INTEGER NOT NULL CHECK(count >= 0))"
                )
                event_count = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
                meta = self._meta()
                if event_count == 0 and not meta:
                    runtime_id = uuid.uuid4().hex
                    self._set_meta("runtime_id", runtime_id)
                    self._set_meta("state_owner_id", _OWNER_ID)
                    self._set_meta("last_seq", "0")
                    self._set_meta("head_digest", ZERO_DIGEST)
                    genesis = create_event(
                        event_type="hg.genesis",
                        sequence=1,
                        actor_id="system",
                        authority_context={"principal": "system", "reason": "genesis"},
                        runtime_id=runtime_id,
                        state_owner_id=_OWNER_ID,
                        payload={"product_id": _PRODUCT_ID, "schema_version": SCHEMA_VERSION},
                        previous_digest=ZERO_DIGEST,
                        correlation_id="genesis",
                        event_id="genesis-" + runtime_id,
                        recorded_at=self._clock(),
                    )
                    self._insert_event(genesis)
                elif event_count == 0 or any(key not in meta for key in _REQUIRED_META):
                    raise SQLiteStateError("partial state initialization; refusing automatic repair")
                self._conn.execute("COMMIT")
            except Exception:
                if self._conn.in_transaction:
                    self._conn.execute("ROLLBACK")
                raise

    def _insert_event(self, event: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO events(sequence, event_id, idempotency_key, event_type, event_json, previous_digest, record_digest) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
            (
                event["sequence"], event["event_id"], event["idempotency_key"], event["event_type"],
                canonical_json(event), event["previous_digest"], event["record_digest"],
            ),
        )
        self._apply_projection(event)
        self._set_meta("last_seq", str(event["sequence"]))
        self._set_meta("head_digest", event["record_digest"])

    def _apply_projection(self, event: dict[str, Any]) -> None:
        if event["event_type"] == "session.created":
            session_id = event["payload"].get("session_id")
            if isinstance(session_id, str) and session_id:
                self._conn.execute(
                    "INSERT INTO sessions(session_id, payload_json) VALUES(?, ?) "
                    "ON CONFLICT(session_id) DO UPDATE SET payload_json=excluded.payload_json",
                    (session_id, canonical_json(event["payload"])),
                )
        self._conn.execute(
            "INSERT INTO counters(event_type, count) VALUES(?, 1) "
            "ON CONFLICT(event_type) DO UPDATE SET count=count+1",
            (event["event_type"],),
        )

    def _event_by_id(self, event_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT event_json FROM events WHERE event_id=?", (event_id,)).fetchone()
        return None if row is None else parse_json_no_duplicate_keys(row["event_json"])

    def _event_by_idempotency(self, key: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT event_json FROM events WHERE idempotency_key=?", (key,)
        ).fetchone()
        return None if row is None else parse_json_no_duplicate_keys(row["event_json"])

    def emit(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        event_id: str | None = None,
        actor_id: str = "local-user",
        authority_context: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                if event_id is not None:
                    existing = self._event_by_id(event_id)
                    if existing is not None:
                        same_operation = (
                            existing["event_type"] == event_type
                            and canonical_json(existing["payload"]) == canonical_json(payload)
                        )
                        if not same_operation:
                            raise IdempotencyConflict("EVENT_ID_REUSED")
                        self._conn.execute("COMMIT")
                        return existing
                if idempotency_key is not None:
                    existing = self._event_by_idempotency(idempotency_key)
                    if existing is not None:
                        same_operation = (
                            existing["event_type"] == event_type
                            and canonical_json(existing["payload"]) == canonical_json(payload)
                        )
                        if not same_operation:
                            raise IdempotencyConflict("IDEMPOTENCY_KEY_REUSED")
                        self._conn.execute("COMMIT")
                        return existing
                meta = self._meta()
                seq = int(meta["last_seq"]) + 1
                event = create_event(
                    event_type=event_type,
                    sequence=seq,
                    actor_id=actor_id,
                    authority_context=authority_context or {"principal": actor_id},
                    runtime_id=meta["runtime_id"],
                    state_owner_id=meta["state_owner_id"],
                    payload=payload,
                    previous_digest=meta["head_digest"],
                    correlation_id=correlation_id,
                    causation_id=causation_id,
                    idempotency_key=idempotency_key,
                    evidence_refs=evidence_refs,
                    event_id=event_id,
                    recorded_at=self._clock(),
                )
                self._insert_event(event)
                self._conn.execute("COMMIT")
                return event
            except Exception:
                if self._conn.in_transaction:
                    self._conn.execute("ROLLBACK")
                raise

    def replay(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT event_json FROM events ORDER BY sequence").fetchall()
            return [parse_json_no_duplicate_keys(row["event_json"]) for row in rows]

    def verify(self) -> dict[str, Any]:
        with self._lock:
            try:
                integrity = self._conn.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    return {"ok": False, "events": 0, "reason": "sqlite_integrity_failure"}
                meta = self._meta()
                if any(key not in meta for key in _REQUIRED_META):
                    return {"ok": False, "events": 0, "reason": "metadata_missing"}
                if meta["state_owner_id"] != _OWNER_ID:
                    return {"ok": False, "events": 0, "reason": "state_owner_mismatch"}
                previous = ZERO_DIGEST
                expected_seq = 1
                seen_ids = set()
                expected_counters: dict[str, int] = {}
                expected_sessions: dict[str, str] = {}
                rows = self._conn.execute("SELECT * FROM events ORDER BY sequence").fetchall()
                for row in rows:
                    try:
                        event = validate_event(parse_json_no_duplicate_keys(row["event_json"]))
                    except ContractError as exc:
                        return {"ok": False, "events": expected_seq - 1, "reason": "invalid_event_" + str(exc)}
                    if event["sequence"] != expected_seq or row["sequence"] != expected_seq:
                        return {"ok": False, "events": expected_seq - 1, "reason": "sequence_gap"}
                    if event["previous_digest"] != previous or row["previous_digest"] != previous:
                        return {"ok": False, "events": expected_seq - 1, "reason": "chain_break"}
                    if event["record_digest"] != row["record_digest"]:
                        return {"ok": False, "events": expected_seq - 1, "reason": "record_digest_column_mismatch"}
                    if event["event_id"] != row["event_id"] or event["event_type"] != row["event_type"]:
                        return {"ok": False, "events": expected_seq - 1, "reason": "event_column_mismatch"}
                    if event["idempotency_key"] != row["idempotency_key"]:
                        return {"ok": False, "events": expected_seq - 1, "reason": "idempotency_column_mismatch"}
                    if event["runtime_id"] != meta["runtime_id"] or event["state_owner_id"] != _OWNER_ID:
                        return {"ok": False, "events": expected_seq - 1, "reason": "event_owner_mismatch"}
                    if event["event_id"] in seen_ids:
                        return {"ok": False, "events": expected_seq - 1, "reason": "duplicate_event_id"}
                    seen_ids.add(event["event_id"])
                    expected_counters[event["event_type"]] = expected_counters.get(event["event_type"], 0) + 1
                    if event["event_type"] == "session.created":
                        session_id = event["payload"].get("session_id")
                        if isinstance(session_id, str) and session_id:
                            expected_sessions[session_id] = canonical_json(event["payload"])
                    previous = event["record_digest"]
                    expected_seq += 1
                last_seq = expected_seq - 1
                if int(meta["last_seq"]) != last_seq or meta["head_digest"] != previous:
                    return {"ok": False, "events": last_seq, "reason": "checkpoint_mismatch"}
                actual_counters = {
                    row["event_type"]: row["count"]
                    for row in self._conn.execute("SELECT event_type, count FROM counters")
                }
                if actual_counters != expected_counters:
                    return {"ok": False, "events": last_seq, "reason": "counter_projection_mismatch"}
                actual_sessions = {
                    row["session_id"]: row["payload_json"]
                    for row in self._conn.execute("SELECT session_id, payload_json FROM sessions")
                }
                if actual_sessions != expected_sessions:
                    return {"ok": False, "events": last_seq, "reason": "session_projection_mismatch"}
                return {
                    "ok": True, "events": last_seq, "last_seq": last_seq,
                    "head_digest": previous, "reason": "chain_ok",
                }
            except (sqlite3.DatabaseError, ContractError, ValueError, TypeError):
                return {"ok": False, "events": 0, "reason": "state_read_failure"}

    def audit_export(self) -> dict[str, Any]:
        events = self.replay()
        verification = self.verify()
        meta = self._meta()
        sessions = {
            row["session_id"]: parse_json_no_duplicate_keys(row["payload_json"])
            for row in self._conn.execute("SELECT session_id, payload_json FROM sessions")
        }
        counters = {
            row["event_type"]: row["count"]
            for row in self._conn.execute("SELECT event_type, count FROM counters")
        }
        return {
            "schema": SCHEMA_VERSION,
            "product_id": _PRODUCT_ID,
            "runtime_id": meta["runtime_id"],
            "events": len(events),
            "last_seq": int(meta["last_seq"]),
            "head_digest": meta["head_digest"],
            "verify": verification,
            "state": {"sessions": sessions, "counters": counters},
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
