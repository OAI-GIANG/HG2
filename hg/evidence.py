"""Evidence envelopes and deterministic claim verification primitives.

Evidence structures are declarations about observations. SHA-256 detects byte changes only;
without trusted capture, authenticated actor identity and provenance verification, evidence
is not promoted to TRUSTED and claims remain UNVERIFIED.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from itertools import islice
from typing import Any, Callable, Iterable

from .task_contract import canonical_json

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_OBSERVED = frozenset({"PASS", "FAIL", "INCONCLUSIVE", "NOT_RUN", "BLOCKED"})
_TRUST = frozenset({"UNVERIFIED", "VERIFIED", "REJECTED"})
MAX_EVIDENCE_ENVELOPE_BYTES = 256_000


class EvidenceError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _text(v: Any, name: str, max_len: int = 2048) -> str:
    if not isinstance(v, str) or not v.strip() or len(v) > max_len:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", name)
    return v


def _digest(v: Any, name: str) -> str:
    if not isinstance(v, str) or not _SHA256_RE.fullmatch(v):
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", name + " must be lowercase SHA-256")
    return v


def _timestamp(v: Any, name: str) -> datetime:
    text = _text(v, name, 64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", name + " invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", name + " timezone required")
    return parsed


def evidence_digest(envelope: dict[str, Any]) -> str:
    unsigned = dict(envelope)
    unsigned.pop("envelope_digest", None)
    try:
        encoded = canonical_json(unsigned).encode("utf-8", errors="strict")
    except (UnicodeEncodeError, ValueError, RecursionError) as exc:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "envelope cannot be serialized safely") from exc
    if len(encoded) > MAX_EVIDENCE_ENVELOPE_BYTES:
        raise EvidenceError("EVIDENCE_RESOURCE_LIMIT", "envelope exceeds byte limit")
    return hashlib.sha256(encoded).hexdigest()


def validate_evidence_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    if type(envelope) is not dict:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "envelope must be object")
    required = {
        "schema_version", "evidence_id", "task_id", "test_id", "source_uri",
        "source_revision", "source_digest", "runtime_id", "build_id", "environment",
        "execution_id", "oracle_id", "oracle_version", "observed_status", "started_at",
        "finished_at", "exit_code", "raw_artifact_uri", "raw_artifact_digest",
        "parent_evidence_ids", "actor_ref", "correlation_id", "causation_id",
        "payload_digest", "trust_state", "envelope_digest",
    }
    if set(envelope) != required:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "missing or unknown fields")
    if envelope["schema_version"] != "hg.evidence-envelope.v1":
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "unsupported schema version")
    for key in ("evidence_id", "task_id", "test_id", "execution_id", "oracle_id", "correlation_id"):
        value = _text(envelope[key], key, 128)
        if not _ID_RE.fullmatch(value):
            raise EvidenceError("EVIDENCE_SCHEMA_INVALID", key + " invalid identifier")
    for key in ("source_uri", "source_revision", "runtime_id", "build_id", "oracle_version", "raw_artifact_uri", "actor_ref", "causation_id"):
        _text(envelope[key], key)
    for key in ("source_digest", "raw_artifact_digest", "payload_digest"):
        _digest(envelope[key], key)
    if type(envelope["environment"]) is not dict:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "environment must be object")
    if not isinstance(envelope["observed_status"], str) or envelope["observed_status"] not in _OBSERVED:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "unknown observed_status")
    if type(envelope["exit_code"]) is not int or envelope["exit_code"] < -255 or envelope["exit_code"] > 255:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "exit_code must be bounded integer")
    started = _timestamp(envelope["started_at"], "started_at")
    finished = _timestamp(envelope["finished_at"], "finished_at")
    if finished < started:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "finished_at precedes started_at")
    if type(envelope["parent_evidence_ids"]) is not list or len(envelope["parent_evidence_ids"]) > 4096:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "parent_evidence_ids must be bounded array")
    parents = [_text(x, "parent_evidence_id", 128) for x in envelope["parent_evidence_ids"]]
    if len(parents) != len(set(parents)):
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "duplicate parent evidence IDs")
    if not isinstance(envelope["trust_state"], str) or envelope["trust_state"] not in _TRUST:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "unknown trust_state")
    if envelope["trust_state"] == "VERIFIED":
        raise EvidenceError("EVIDENCE_TRUST_PROMOTION_FORBIDDEN", "schema validation cannot authenticate evidence")
    _digest(envelope["envelope_digest"], "envelope_digest")
    if envelope["envelope_digest"] != evidence_digest(envelope):
        raise EvidenceError("EVIDENCE_INTEGRITY_FAILED", "envelope digest mismatch")
    result = dict(envelope)
    result["parent_evidence_ids"] = parents
    return result


def verify_claim(
    *,
    claim_id: str,
    criterion_id: str,
    evidence_ids: Iterable[str],
    evidence_store: Any,
    expected_source_revision: str,
    expected_oracle_id: str,
    expected_oracle_version: str,
    attestation_verifier: Callable[[dict[str, Any]], tuple[bool, str]] | None = None,
) -> dict[str, Any]:
    """Verify references and consistency only; never authenticates remote provenance."""
    _text(claim_id, "claim_id", 128)
    _text(criterion_id, "criterion_id", 128)
    ids = list(islice(iter(evidence_ids), 4097))
    if len(ids) > 4096:
        return {"claim_id": claim_id, "criterion_id": criterion_id, "status": "UNVERIFIED",
                "reason": "EVIDENCE_RESOURCE_LIMIT", "evidence_ids": []}
    if not ids:
        return {"claim_id": claim_id, "criterion_id": criterion_id, "status": "UNVERIFIED",
                "reason": "EVIDENCE_MISSING", "evidence_ids": []}
    results = []
    for eid in ids:
        try:
            envelope = evidence_store.get(eid)
        except EvidenceError as exc:
            reason = "EVIDENCE_MISSING" if exc.code == "EVIDENCE_NOT_FOUND" else exc.code
            results.append({"evidence_id": eid, "ok": False, "reason": reason})
            continue
        if envelope is None:
            results.append({"evidence_id": eid, "ok": False, "reason": "EVIDENCE_MISSING"})
            continue
        try:
            checked = validate_evidence_envelope(envelope)
        except EvidenceError as exc:
            results.append({"evidence_id": eid, "ok": False, "reason": exc.code})
            continue
        reason = None
        if checked["source_revision"] != expected_source_revision:
            reason = "EVIDENCE_SOURCE_REVISION_MISMATCH"
        elif checked["oracle_id"] != expected_oracle_id or checked["oracle_version"] != expected_oracle_version:
            reason = "EVIDENCE_ORACLE_MISMATCH"
        elif checked["observed_status"] != "PASS":
            reason = "EVIDENCE_OBSERVED_STATUS_NOT_PASS"
        elif checked["trust_state"] == "REJECTED":
            reason = "EVIDENCE_TRUST_REJECTED"
        elif attestation_verifier is None:
            reason = "EVIDENCE_PROVENANCE_UNVERIFIED"
        else:
            try:
                decision = attestation_verifier(dict(checked))
                if type(decision) is not tuple or len(decision) != 2 or type(decision[0]) is not bool or not isinstance(decision[1], str) or not decision[1].strip():
                    reason = "ATTESTATION_VERIFIER_INVALID_RESPONSE"
                elif not decision[0]:
                    reason = "ATTESTATION_NOT_TRUSTED"
                else:
                    reason = None
                    results.append({"evidence_id": eid, "ok": True, "reason": "ATTESTATION_VERIFIED",
                                    "attestation_decision_ref": decision[1]})
                    continue
            except Exception:
                reason = "ATTESTATION_VERIFIER_ERROR"
        results.append({"evidence_id": eid, "ok": reason is None, "reason": reason or "CONSISTENT"})
    adapter_reported_pass = bool(results) and all(r["ok"] for r in results)
    decision_refs = [r["attestation_decision_ref"] for r in results if r.get("attestation_decision_ref")]
    # This function has no configured trust root or host-bound verifier identity. A callback
    # returning True is only an adapter report and must never promote evidence to VERIFIED.
    return {"claim_id": claim_id, "criterion_id": criterion_id,
            "status": "UNVERIFIED",
            "reason": "ATTESTATION_ADAPTER_NOT_BOUND_TO_TRUST_ROOT" if adapter_reported_pass else "EVIDENCE_NOT_VERIFIED",
            "evidence_results": results, "authenticated_provenance": False,
            "attestation_adapter_reported_pass": adapter_reported_pass,
            "attestation_decision_refs": decision_refs}
class SQLiteEvidenceStore:
    """File-backed evidence envelope store with immutable IDs and hash-linked events.

    Stored envelopes remain UNVERIFIED until a separately trusted attestation verifier
    validates their source/oracle/runtime provenance. The store does not store raw artifact
    bytes; only envelope metadata and declared content digests.
    """

    def __init__(self, db_path: str, *, max_records: int = 100_000, busy_timeout_ms: int = 10_000) -> None:
        import os
        import sqlite3
        from contextlib import contextmanager

        self.db_path = os.fspath(db_path)
        if not self.db_path or self.db_path == ":memory:":
            raise EvidenceError("EVIDENCE_STORAGE_INVALID", "durable file-backed database required")
        if type(max_records) is not int or not 1 <= max_records <= 1_000_000:
            raise EvidenceError("EVIDENCE_RESOURCE_LIMIT", "invalid max_records")
        if type(busy_timeout_ms) is not int or not 100 <= busy_timeout_ms <= 120_000:
            raise EvidenceError("EVIDENCE_RESOURCE_LIMIT", "invalid busy_timeout_ms")
        self.max_records = max_records
        self.busy_timeout_ms = busy_timeout_ms
        self._sqlite3 = sqlite3
        self._contextmanager = contextmanager
        with self._connection() as db:
            try:
                journal = db.execute("PRAGMA journal_mode=WAL").fetchone()[0]
                if str(journal).lower() != "wal":
                    raise EvidenceError("EVIDENCE_STORAGE_UNAVAILABLE", "SQLite WAL mode unavailable")
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, 1):
                    raise EvidenceError("EVIDENCE_SCHEMA_UNSUPPORTED", str(version))
                db.executescript("""
                    CREATE TABLE IF NOT EXISTS hg_evidence (
                        evidence_id TEXT PRIMARY KEY,
                        envelope_digest TEXT NOT NULL,
                        envelope_json TEXT NOT NULL,
                        trust_state TEXT NOT NULL,
                        task_id TEXT NOT NULL,
                        source_revision TEXT NOT NULL,
                        oracle_id TEXT NOT NULL,
                        oracle_version TEXT NOT NULL,
                        stored_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS hg_evidence_task
                        ON hg_evidence(task_id, evidence_id);
                    CREATE TABLE IF NOT EXISTS hg_evidence_event (
                        seq INTEGER PRIMARY KEY,
                        evidence_id TEXT NOT NULL REFERENCES hg_evidence(evidence_id),
                        event_type TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        detail_json TEXT NOT NULL,
                        previous_digest TEXT NOT NULL,
                        event_digest TEXT NOT NULL
                    );
                    PRAGMA user_version=1;
                """)
            except EvidenceError:
                raise
            except sqlite3.Error as exc:
                raise EvidenceError("EVIDENCE_STORAGE_UNAVAILABLE", str(exc)) from exc

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
                    raise EvidenceError("EVIDENCE_STORAGE_UNAVAILABLE", str(exc)) from exc
                except Exception:
                    db.rollback()
                    raise
        return manager

    def _append_event(self, db, evidence_id: str, event_type: str, detail: dict[str, Any]) -> None:
        seq = db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM hg_evidence_event").fetchone()[0]
        last = db.execute("SELECT event_digest FROM hg_evidence_event ORDER BY seq DESC LIMIT 1").fetchone()
        previous = last[0] if last else "0" * 64
        occurred_at = datetime.now().astimezone().isoformat(timespec="microseconds")
        detail_json = canonical_json(detail)
        body = {"seq": seq, "evidence_id": evidence_id, "event_type": event_type,
                "occurred_at": occurred_at, "detail_json": detail_json,
                "previous_digest": previous}
        digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
        db.execute(
            "INSERT INTO hg_evidence_event(seq,evidence_id,event_type,occurred_at,detail_json,previous_digest,event_digest) "
            "VALUES(?,?,?,?,?,?,?)",
            (seq, evidence_id, event_type, occurred_at, detail_json, previous, digest),
        )

    def put(self, envelope: dict[str, Any]) -> dict[str, Any]:
        checked = validate_evidence_envelope(envelope)
        if checked["trust_state"] not in {"UNVERIFIED", "REJECTED"}:
            raise EvidenceError("EVIDENCE_TRUST_PROMOTION_FORBIDDEN")
        evidence_id = checked["evidence_id"]
        digest = checked["envelope_digest"]
        envelope_json = canonical_json(checked)
        stored_at = datetime.now().astimezone().isoformat(timespec="microseconds")
        with self._atomic() as db:
            old = db.execute("SELECT envelope_digest,envelope_json FROM hg_evidence WHERE evidence_id=?",
                             (evidence_id,)).fetchone()
            if old:
                if old[0] != digest or old[1] != envelope_json:
                    raise EvidenceError("EVIDENCE_ID_CONFLICT", evidence_id)
                return {"stored": True, "idempotent": True, "evidence_id": evidence_id,
                        "envelope_digest": digest, "trust_state": checked["trust_state"]}
            count = db.execute("SELECT COUNT(*) FROM hg_evidence").fetchone()[0]
            if count >= self.max_records:
                raise EvidenceError("EVIDENCE_RESOURCE_LIMIT", "record limit reached")
            db.execute(
                "INSERT INTO hg_evidence(evidence_id,envelope_digest,envelope_json,trust_state,task_id,source_revision,"
                "oracle_id,oracle_version,stored_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (evidence_id, digest, envelope_json, checked["trust_state"], checked["task_id"],
                 checked["source_revision"], checked["oracle_id"], checked["oracle_version"], stored_at),
            )
            self._append_event(db, evidence_id, "EVIDENCE_STORED",
                               {"envelope_digest": digest, "trust_state": checked["trust_state"],
                                "source_revision": checked["source_revision"],
                                "oracle_id": checked["oracle_id"], "oracle_version": checked["oracle_version"]})
            return {"stored": True, "idempotent": False, "evidence_id": evidence_id,
                    "envelope_digest": digest, "trust_state": checked["trust_state"]}

    def get(self, evidence_id: str) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute("SELECT envelope_json,envelope_digest FROM hg_evidence WHERE evidence_id=?",
                             (evidence_id,)).fetchone()
        if row is None:
            raise EvidenceError("EVIDENCE_NOT_FOUND", evidence_id)
        try:
            envelope = json.loads(row[0])
            checked = validate_evidence_envelope(envelope)
        except (ValueError, EvidenceError) as exc:
            code = exc.code if isinstance(exc, EvidenceError) else "EVIDENCE_INVALID_STORED_JSON"
            raise EvidenceError("EVIDENCE_STORED_RECORD_INVALID", f"{evidence_id}:{code}") from exc
        if checked["envelope_digest"] != row[1]:
            raise EvidenceError("EVIDENCE_STORED_RECORD_INVALID", "stored digest column mismatch")
        return checked

    def list_by_task(self, task_id: str, *, limit: int = 1000) -> list[dict[str, Any]]:
        if not isinstance(task_id, str) or not task_id.strip():
            raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "task_id")
        if type(limit) is not int or not 1 <= limit <= 10_000:
            raise EvidenceError("EVIDENCE_RESOURCE_LIMIT", "invalid limit")
        with self._connection() as db:
            rows = db.execute("SELECT evidence_id FROM hg_evidence WHERE task_id=? ORDER BY evidence_id LIMIT ?",
                              (task_id, limit)).fetchall()
        return [self.get(row[0]) for row in rows]

    def events(self) -> list[dict[str, Any]]:
        with self._connection() as db:
            rows = db.execute(
                "SELECT seq,evidence_id,event_type,occurred_at,detail_json,previous_digest,event_digest "
                "FROM hg_evidence_event ORDER BY seq"
            ).fetchall()
        events = []
        for row in rows:
            try:
                detail = json.loads(row[4])
                parse_error = False
            except (ValueError, TypeError):
                detail = None
                parse_error = True
            events.append({"seq": row[0], "evidence_id": row[1], "event_type": row[2],
                           "occurred_at": row[3], "detail": detail, "detail_parse_error": parse_error,
                           "previous_digest": row[5], "event_digest": row[6]})
        return events

    def verify_store_integrity(self) -> dict[str, Any]:
        """Verify both the event chain and its linkage to stored evidence projections."""
        chain = self.verify_event_chain()
        if not chain["ok"]:
            return chain
        events = self.events()
        first_events: dict[str, dict[str, Any]] = {}
        for event in events:
            if event["event_type"] == "EVIDENCE_STORED":
                if event["evidence_id"] in first_events:
                    return {"ok": False, "reason": "EVIDENCE_DUPLICATE_STORE_EVENT",
                            "evidence_id": event["evidence_id"]}
                first_events[event["evidence_id"]] = event
        with self._connection() as db:
            rows = db.execute(
                "SELECT evidence_id,envelope_digest,trust_state,task_id,source_revision,oracle_id,oracle_version "
                "FROM hg_evidence ORDER BY evidence_id"
            ).fetchall()
        row_ids = {row[0] for row in rows}
        if row_ids != set(first_events):
            return {"ok": False, "reason": "EVIDENCE_EVENT_PROJECTION_MISSING",
                    "stored_records": len(row_ids), "store_events": len(first_events)}
        for row in rows:
            evidence_id = row[0]
            try:
                envelope = self.get(evidence_id)
            except EvidenceError as exc:
                return {"ok": False, "reason": "EVIDENCE_STORED_RECORD_INVALID",
                        "evidence_id": evidence_id, "detail": exc.code}
            event = first_events[evidence_id]
            detail = event.get("detail")
            expected = {"envelope_digest": row[1], "trust_state": row[2], "source_revision": row[4],
                        "oracle_id": row[5], "oracle_version": row[6]}
            row_matches = (envelope["task_id"] == row[3] and envelope["source_revision"] == row[4] and
                           envelope["oracle_id"] == row[5] and envelope["oracle_version"] == row[6] and
                           envelope["trust_state"] == row[2] and envelope["envelope_digest"] == row[1])
            if type(detail) is not dict or any(detail.get(key) != value for key, value in expected.items()) or not row_matches:
                return {"ok": False, "reason": "EVIDENCE_EVENT_PROJECTION_MISMATCH", "evidence_id": evidence_id}
        return {"ok": True, "records_checked": len(rows), "verified_events": chain["verified_events"],
                "head_digest": chain["head_digest"]}

    def verify_event_chain(self) -> dict[str, Any]:
        events = self.events()
        previous = "0" * 64
        for index, event in enumerate(events, 1):
            if event.get("detail_parse_error") or type(event.get("detail")) is not dict:
                return {"ok": False, "reason": "EVIDENCE_EVENT_DETAIL_INVALID",
                        "failed_seq": event["seq"], "verified_events": index - 1}
            if event["seq"] != index or event["previous_digest"] != previous:
                return {"ok": False, "reason": "EVIDENCE_EVENT_CHAIN_LINK_MISMATCH",
                        "failed_seq": event["seq"], "verified_events": index - 1}
            body = {"seq": event["seq"], "evidence_id": event["evidence_id"],
                    "event_type": event["event_type"], "occurred_at": event["occurred_at"],
                    "detail_json": canonical_json(event["detail"]),
                    "previous_digest": event["previous_digest"]}
            digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
            if digest != event["event_digest"]:
                return {"ok": False, "reason": "EVIDENCE_EVENT_CHAIN_DIGEST_MISMATCH",
                        "failed_seq": event["seq"], "verified_events": index - 1}
            previous = event["event_digest"]
        return {"ok": True, "verified_events": len(events), "head_digest": previous}
