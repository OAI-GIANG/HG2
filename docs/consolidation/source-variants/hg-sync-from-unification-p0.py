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
import re
import time
import uuid

from .history import PRODUCT_ID, SCHEMA, StateStore, canonical, digest

SYNC_SCHEMA = "HG_SYNC_V2"
BATCH_SCHEMA = "HG_SYNC_BATCH_V2"
REQUIRED_EVENT_FIELDS = ("event_id", "event_type", "payload", "payload_hash",
                         "origin_context", "origin_seq", "origin_prev_hash", "origin_hash",
                         "origin_record")
REQUIRED_ORIGIN_RECORD_FIELDS = ("seq", "event_id", "event_type", "recorded_at", "correlation_id",
                                 "causation_id", "product_id", "runtime_id", "schema", "payload",
                                 "prev_hash", "record_hash")


def _object_without_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(value):
    raise ValueError("non-standard JSON constant: " + value)


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


class SyncError(Exception):
    """Raised for rejected batches/events (fail-closed)."""


class SyncContext:
    def __init__(self, context_id: str, state_dir: str, spool_dir: str, clock=time.time, *,
                 store: StateStore | None = None) -> None:
        self.context_id = context_id
        self.spool = spool_dir
        self._clock = clock
        for sub in ("inbox", "outbox", "conflicts"):
            os.makedirs(os.path.join(spool_dir, sub), exist_ok=True)
        self.audit_path = os.path.join(spool_dir, "sync-audit.jsonl")
        # Runtime integration must inject the canonical owner's existing store.
        # Constructing another StateStore for the same state_dir can replay and
        # rewrite durable projections concurrently with the canonical owner.
        self.store = store if store is not None else StateStore(state_dir)
        if store is not None and os.path.realpath(store.dir) != os.path.realpath(state_dir):
            raise ValueError("injected StateStore directory mismatch")

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
        origin_record = json.loads(canonical(rec))
        return {"event_id": rec["event_id"], "event_type": rec["event_type"], "payload": origin_record["payload"],
                "payload_hash": digest(origin_record["payload"]), "origin_context": self.context_id,
                "origin_seq": origin_record["seq"], "origin_prev_hash": origin_record["prev_hash"],
                "origin_hash": origin_record["record_hash"], "origin_record": origin_record}

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
                payload = rec["payload"]
                key = (payload.get("origin_context"), payload.get("event_id"))
                index[key] = {field: payload.get(field) for field in
                              ("event_type", "payload_hash", "origin_seq", "origin_prev_hash", "origin_hash")}
        return index

    def import_batch(self, path_or_name: str, *, _authenticated_batch=None, _authenticated_raw=None) -> dict:
        # Imports are restricted to a simple filename already staged in this context's inbox.
        # Never read/move an arbitrary caller-supplied path or follow an inbox symlink.
        if (not isinstance(path_or_name, str) or not path_or_name
                or os.path.basename(path_or_name) != path_or_name
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,123}\.json", path_or_name)):
            raise SyncError("invalid inbox filename")
        name = path_or_name
        inbox = os.path.realpath(os.path.join(self.spool, "inbox"))
        path = os.path.join(inbox, name)
        if os.path.islink(path) or not os.path.isfile(path) or os.path.realpath(path) != path:
            raise SyncError("batch file missing or unsafe")
        if _authenticated_batch is not None:
            # Authenticated path passes the exact parsed object whose authentication tag was
            # verified; do not reopen the inbox file and create a verify/import TOCTOU.
            batch, raw = _authenticated_batch, _authenticated_raw
            if not isinstance(raw, bytes):
                raise SyncError("authenticated raw bytes required")
        else:
            with open(path, "rb") as fh:
                raw = fh.read()
            try:
                batch = json.loads(raw.decode("utf-8"), object_pairs_hook=_object_without_duplicate_keys,
                                   parse_constant=_reject_json_constant)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                self._reject(name, "MALFORMED_OR_TRUNCATED_BATCH", raw)
                raise SyncError("malformed batch") from exc
        if not isinstance(batch, dict) or batch.get("schema") != BATCH_SCHEMA:
            self._reject(name, "UNSUPPORTED_BATCH_SCHEMA", raw)
            raise SyncError("unsupported batch schema")
        events = batch.get("events")
        if not isinstance(events, list) or not events:
            self._reject(name, "EMPTY_BATCH", raw)
            raise SyncError("empty batch")
        batch_origin = batch.get("context_id")
        if not isinstance(batch_origin, str) or not batch_origin:
            self._reject(name, "INVALID_BATCH_CONTEXT", raw)
            raise SyncError("invalid batch context")
        index = self._received_index()
        accepted, duplicates, pending = [], [], []
        prev_origin_hash = None
        prev_origin_seq = None
        observed_origin = None

        # Preflight the entire batch before appending any received event. A malformed later
        # event must not leave an earlier prefix partially applied.
        for ev in events:
            if not isinstance(ev, dict) or any(f not in ev for f in REQUIRED_EVENT_FIELDS):
                self._reject(name, "MISSING_REQUIRED_FIELD", raw)
                raise SyncError("missing required field")
            if (not isinstance(ev["event_id"], str) or not ev["event_id"]
                    or not isinstance(ev["event_type"], str) or not ev["event_type"]
                    or not isinstance(ev["origin_context"], str) or not ev["origin_context"]
                    or not isinstance(ev["origin_seq"], int) or isinstance(ev["origin_seq"], bool)
                    or ev["origin_seq"] < 1):
                self._reject(name, "INVALID_EVENT_METADATA", raw)
                raise SyncError("invalid event metadata")
            if ev["origin_context"] == self.context_id:
                self._reject(name, "SELF_ORIGIN_EVENT", raw)
                raise SyncError("self-origin event")
            if observed_origin is None:
                observed_origin = ev["origin_context"]
                if batch_origin is not None and batch_origin != observed_origin:
                    self._reject(name, "BATCH_ORIGIN_MISMATCH", raw)
                    raise SyncError("batch origin mismatch")
            elif ev["origin_context"] != observed_origin:
                self._reject(name, "MIXED_ORIGIN_CONTEXTS", raw)
                raise SyncError("mixed origin contexts")
            if (not _is_sha256(ev["payload_hash"]) or not _is_sha256(ev["origin_prev_hash"])
                    or not _is_sha256(ev["origin_hash"])):
                self._reject(name, "INVALID_HASH_FORMAT", raw)
                raise SyncError("invalid hash format")
            if digest(ev["payload"]) != ev["payload_hash"]:
                self._reject(name, "PAYLOAD_HASH_MISMATCH", raw)
                raise SyncError("payload hash mismatch")
            origin_record = ev["origin_record"]
            if not isinstance(origin_record, dict) or any(
                    field not in origin_record for field in REQUIRED_ORIGIN_RECORD_FIELDS):
                self._reject(name, "INVALID_ORIGIN_RECORD", raw)
                raise SyncError("invalid origin record")
            origin_core = {key: value for key, value in origin_record.items() if key != "record_hash"}
            if (origin_record.get("record_hash") != ev["origin_hash"]
                    or digest(origin_core) != ev["origin_hash"]):
                self._reject(name, "ORIGIN_RECORD_HASH_MISMATCH", raw)
                raise SyncError("origin record hash mismatch")
            if origin_record.get("schema") != SCHEMA or origin_record.get("product_id") != PRODUCT_ID:
                self._reject(name, "UNSUPPORTED_ORIGIN_RECORD_SCHEMA", raw)
                raise SyncError("unsupported origin record schema")
            if (origin_record.get("event_id") != ev["event_id"]
                    or origin_record.get("event_type") != ev["event_type"]
                    or origin_record.get("payload") != ev["payload"]
                    or origin_record.get("seq") != ev["origin_seq"]
                    or origin_record.get("prev_hash") != ev["origin_prev_hash"]):
                self._reject(name, "ORIGIN_RECORD_ENVELOPE_MISMATCH", raw)
                raise SyncError("origin record envelope mismatch")
            if prev_origin_hash is not None and (
                    ev["origin_prev_hash"] != prev_origin_hash
                    or ev["origin_seq"] != prev_origin_seq + 1):
                self._reject(name, "IN_BATCH_CHAIN_BREAK", raw)
                raise SyncError("in-batch chain break")
            prev_origin_hash = ev["origin_hash"]
            prev_origin_seq = ev["origin_seq"]
            key = (ev["origin_context"], ev["event_id"])
            if key in index:
                known = index[key]
                if all(known.get(field) == ev.get(field) for field in
                       ("event_type", "payload_hash", "origin_seq", "origin_prev_hash", "origin_hash")):
                    duplicates.append(ev["event_id"])
                    continue
                self._conflict(name, "DUPLICATE_EVENT_ID_DIFFERENT_PROVENANCE", raw)
                raise SyncError("duplicate event id with different provenance")
            index[key] = {field: ev.get(field) for field in
                          ("event_type", "payload_hash", "origin_seq", "origin_prev_hash", "origin_hash")}
            accepted.append(ev["event_id"])
            pending.append(ev)

        # Only apply after every event has passed preflight validation.
        for ev in pending:
            self.store.emit("sync.received", {"event_id": ev["event_id"], "event_type": ev["event_type"],
                                              "payload": ev["payload"], "payload_hash": ev["payload_hash"],
                                              "origin_context": ev["origin_context"], "origin_seq": ev["origin_seq"],
                                              "origin_prev_hash": ev["origin_prev_hash"], "origin_hash": ev["origin_hash"],
                                              "origin_record": ev["origin_record"]})
        os.replace(path, os.path.join(self.spool, "inbox", ".consumed-" + name))
        self._audit({"op": "import", "file": name, "accepted": accepted, "duplicates": duplicates,
                     "batch_hash": digest(batch), "at": self._clock()})
        return {"accepted": accepted, "duplicates": duplicates}

    # ------------------------------------------ authenticated transactional import
    def import_authenticated_batch(self, path_or_name: str, gate) -> dict:
        """Authenticate and validate a whole batch, idempotently import, then commit cursor.

        Crash semantics: import writes idempotent per-event envelopes before cursor commit.
        If the process dies after any append but before cursor persistence, retrying the same
        authenticated batch revalidates from the old cursor; already-imported event IDs are skipped,
        remaining events are appended, and only then is the cursor advanced. The caller must
        supply a gate with a receiver-owned cursor path distinct from the StateStore directory.
        """
        if not isinstance(path_or_name, str) or os.path.basename(path_or_name) != path_or_name:
            raise SyncError("invalid inbox filename")
        path = os.path.join(os.path.realpath(os.path.join(self.spool, "inbox")), path_or_name)
        if os.path.islink(path) or not os.path.isfile(path) or os.path.realpath(path) != path:
            raise SyncError("batch file missing or unsafe")
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
            batch = json.loads(raw.decode("utf-8"), object_pairs_hook=_object_without_duplicate_keys,
                               parse_constant=_reject_json_constant)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise SyncError("malformed authenticated batch") from exc
        # Gate checks peer authentication and trusted origin sequence/hash before import.
        state_dir = os.path.realpath(self.store.dir)
        cursor_path = os.path.realpath(gate.cursor_path)
        if os.path.commonpath((state_dir, cursor_path)) == state_dir:
            raise SyncError("authenticated cursor must be outside StateStore directory")
        proposal = gate.verify(batch)
        # Validate/import the exact same parsed object whose authentication tag was checked.
        # import_batch validates every envelope before first write and is idempotent.
        result = self.import_batch(path_or_name, _authenticated_batch=batch, _authenticated_raw=raw)
        # Cursor is durable only after every event has been imported or confirmed duplicate.
        gate.commit(proposal)
        return {**result, "cursor": {"peer_id": proposal["peer_id"], "seq": proposal["seq"],
                                     "hash": proposal["hash"]}}

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
