"""HG T-018 cross-context event synchronization (spool-based, fail-closed).

Design invariants
- Each context owns its OWN StateStore/log. A local log only ever contains records the local
  writer produced; foreign events are recorded as local "sync.received" envelopes carrying the
  origin provenance, so local seq/prev_hash invariants can never be broken by remote input.
- Exchange happens through an on-disk two-way spool (outbox/inbox/conflicts) with
  write-temp -> fsync -> os.replace (atomic publish, never a partially visible batch).
- Every batch is validated before any local write: schema, required fields, payload hash,
  in-batch chain continuity, duplicate detection (idempotency) and conflict detection.
- Fail-closed: any invalid input is rejected with a specific reason and an audit record; nothing
  is written for rejected input.
"""
from __future__ import annotations

import json
import os
import time
import uuid

from .history import HistoryError, StateStore, canonical, digest

SYNC_SCHEMA = "HG_SYNC_V1"
BATCH_SCHEMA = "HG_SYNC_BATCH_V1"
REQUIRED_EVENT_FIELDS = ("event_id", "event_type", "payload", "payload_hash",
                         "origin_context", "origin_seq", "origin_prev_hash", "origin_hash")


class SyncError(Exception):
    """Raised for rejected batches/events (fail-closed)."""


class SyncContext:
    def __init__(self, context_id: str, state_dir: str, spool_dir: str, clock=time.time) -> None:
        self.context_id = context_id
        self.spool = spool_dir
        self._clock = clock
        for sub in ("inbox", "outbox", "conflicts"):
            os.makedirs(os.path.join(spool_dir, sub), exist_ok=True)
        self.audit_path = os.path.join(spool_dir, "sync-audit.jsonl")
        self.store = StateStore(state_dir)  # fail-closed on corrupt history

    # ---------------------------------------------------------------- audit
    def _audit(self, record: dict) -> None:
        with open(self.audit_path, "a", encoding="utf-8") as fh:
            fh.write(canonical(record) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def audit_records(self) -> list:
        if not os.path.exists(self.audit_path):
            return []
        with open(self.audit_path, "r", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh.read().splitlines() if line.strip()]

    # --------------------------------------------------------------- export
    def local_event(self, event_type: str, payload: dict) -> dict:
        rec = self.store.emit(event_type, payload)
        return {"event_id": rec["event_id"], "event_type": rec["event_type"], "payload": rec["payload"],
                "payload_hash": digest(rec["payload"]), "origin_context": self.context_id,
                "origin_seq": rec["seq"], "origin_prev_hash": rec["prev_hash"], "origin_hash": rec["record_hash"]}

    def export_batch(self, events: list) -> dict:
        batch = {"schema": BATCH_SCHEMA, "context_id": self.context_id, "created_at": self._clock(),
                 "events": events}
        blob = canonical(batch).encode("utf-8")
        name = "%s-%s.json" % (self.context_id[:8], uuid.uuid4().hex[:12])
        target = os.path.join(self.spool, "outbox", name)
        tmp = target + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(blob)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
        self._audit({"op": "export", "file": name, "batch_hash": digest(batch),
                     "events": len(events), "at": self._clock()})
        return {"file": name, "batch_hash": digest(batch), "events": len(events)}

    def publish(self, event_type: str, payload: dict) -> dict:
        return self.export_batch([self.local_event(event_type, payload)])

    # --------------------------------------------------------------- import
    def _received_index(self) -> dict:
        index = {}
        for rec in self.store.replay():
            if rec["event_type"] == "sync.received":
                key = (rec["payload"].get("origin_context"), rec["payload"].get("event_id"))
                index[key] = rec["payload"].get("payload_hash")
        return index

    def import_batch(self, path_or_name: str) -> dict:
        name = os.path.basename(path_or_name)
        path = path_or_name if os.path.exists(path_or_name) else os.path.join(self.spool, "inbox", name)
        if not os.path.exists(path):
            raise SyncError("batch file missing")
        with open(path, "rb") as fh:
            raw = fh.read()
        try:
            batch = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._reject(name, "MALFORMED_OR_TRUNCATED_BATCH", raw)
            raise SyncError("malformed batch") from exc
        if not isinstance(batch, dict) or batch.get("schema") != BATCH_SCHEMA:
            self._reject(name, "UNSUPPORTED_BATCH_SCHEMA", raw)
            raise SyncError("unsupported batch schema")
        events = batch.get("events")
        if not isinstance(events, list) or not events:
            self._reject(name, "EMPTY_BATCH", raw)
            raise SyncError("empty batch")
        index = self._received_index()
        accepted, duplicates = [], []
        prev_origin_hash = None
        for ev in events:
            if not isinstance(ev, dict) or any(f not in ev for f in REQUIRED_EVENT_FIELDS):
                self._reject(name, "MISSING_REQUIRED_FIELD", raw)
                raise SyncError("missing required field")
            if ev["origin_context"] == self.context_id:
                self._reject(name, "SELF_ORIGIN_EVENT", raw)
                raise SyncError("self-origin event")
            if digest(ev["payload"]) != ev["payload_hash"]:
                self._reject(name, "PAYLOAD_HASH_MISMATCH", raw)
                raise SyncError("payload hash mismatch")
            if prev_origin_hash is not None and ev["origin_prev_hash"] != prev_origin_hash:
                self._reject(name, "IN_BATCH_CHAIN_BREAK", raw)
                raise SyncError("in-batch chain break")
            prev_origin_hash = ev["origin_hash"]
            key = (ev["origin_context"], ev["event_id"])
            if key in index:
                if index[key] == ev["payload_hash"]:
                    duplicates.append(ev["event_id"])
                    continue
                self._conflict(name, "DUPLICATE_EVENT_ID_DIFFERENT_PAYLOAD", raw)
                raise SyncError("duplicate event id with different payload")
            self.store.emit("sync.received", {"event_id": ev["event_id"], "event_type": ev["event_type"],
                                              "payload": ev["payload"], "payload_hash": ev["payload_hash"],
                                              "origin_context": ev["origin_context"], "origin_seq": ev["origin_seq"],
                                              "origin_prev_hash": ev["origin_prev_hash"], "origin_hash": ev["origin_hash"]})
            index[key] = ev["payload_hash"]
            accepted.append(ev["event_id"])
        os.replace(path, os.path.join(self.spool, "inbox", ".consumed-" + name))
        self._audit({"op": "import", "file": name, "accepted": accepted, "duplicates": duplicates,
                     "batch_hash": digest(batch), "at": self._clock()})
        return {"accepted": accepted, "duplicates": duplicates}

    # ------------------------------------------------------------ rejection
    def _reject(self, name: str, reason: str, raw: bytes) -> None:
        self._audit({"op": "reject", "file": name, "reason": reason, "batch_sha256": digest(raw.decode("utf-8", "replace")),
                     "at": self._clock()})
        self.store.emit("sync.rejected", {"file": name, "reason": reason})

    def _conflict(self, name: str, reason: str, raw: bytes) -> None:
        dest = os.path.join(self.spool, "conflicts", name)
        try:
            os.replace(self.spool + "/inbox/" + name, dest)
        except OSError:
            with open(dest, "wb") as fh:
                fh.write(raw)
        self._audit({"op": "conflict", "file": name, "reason": reason, "at": self._clock()})
        self.store.emit("sync.conflict", {"file": name, "reason": reason})
