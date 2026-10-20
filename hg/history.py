"""Append-only, hash-chained HG state and history. Fail-closed on any integrity failure."""
from __future__ import annotations

import hashlib, json, os, threading, time, uuid

SCHEMA = "HG_STATE_V1"
PRODUCT_ID = "HG"
GENESIS_EVENT = "hg.genesis"
ZERO = "0" * 64


def canonical(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(o):
    return hashlib.sha256(canonical(o).encode("utf-8")).hexdigest()


class HistoryError(Exception):
    pass


_HISTORY_V1_FIELDS = frozenset({
    "seq", "event_id", "event_type", "recorded_at", "correlation_id",
    "causation_id", "product_id", "runtime_id", "schema", "payload",
    "prev_hash", "record_hash",
})
_HISTORY_V2_FIELDS = _HISTORY_V1_FIELDS | frozenset({
    "event_schema", "actor_id", "authority_context", "authorization_action", "idempotency_key",
})
HISTORY_EVENT_SCHEMA_V2 = "HG_HISTORY_EVENT_V2"


def history_record_contract(record):
    """Classify a history envelope as supported V1 or structurally valid V2.

    This is a read/contract helper only: it never consumes a MutationPermit and never
    treats structure validation as authorization to append a record. V2 mutation authority
    remains owned by policy-authorized durable stores until a backend migration is approved.
    """
    if not isinstance(record, dict):
        raise HistoryError("record is not an object")
    if "event_schema" not in record:
        if set(record) != _HISTORY_V1_FIELDS:
            raise HistoryError("V1 record schema mismatch")
        return "V1"
    if set(record) != _HISTORY_V2_FIELDS or record.get("event_schema") != HISTORY_EVENT_SCHEMA_V2:
        raise HistoryError("V2 record schema mismatch")
    actor = record.get("actor_id")
    authority = record.get("authority_context")
    action = record.get("authorization_action")
    key = record.get("idempotency_key")
    if not isinstance(actor, str) or not actor.strip():
        raise HistoryError("V2 actor invalid")
    if not isinstance(authority, dict) or authority != {"principal": actor, "scope": action}:
        raise HistoryError("V2 authority context invalid")
    if not isinstance(action, str) or not action.strip():
        raise HistoryError("V2 authorization action invalid")
    if key is not None and (not isinstance(key, str) or not key.strip()):
        raise HistoryError("V2 idempotency key invalid")
    return "V2"


class StateStore:
    def __init__(self, directory, *, clock=time.time):
        self.dir = str(directory)
        os.makedirs(self.dir, exist_ok=True)
        self.log = os.path.join(self.dir, "history.jsonl")
        self.head = os.path.join(self.dir, "head.json")
        self.state = os.path.join(self.dir, "state.json")
        self.runtime_id_path = os.path.join(self.dir, "runtime_id")
        self.bootstrap_path = os.path.join(self.dir, "history.bootstrap.pending")
        self._clock = clock
        self._preexisting = {"log": os.path.exists(self.log), "head": os.path.exists(self.head),
                             "state": os.path.exists(self.state),
                             "runtime_id": os.path.exists(self.runtime_id_path),
                             "bootstrap": os.path.exists(self.bootstrap_path)}
        self._bootstrap_active = self._preexisting["bootstrap"]
        self._bootstrap_new = False
        if self._bootstrap_active:
            self._bootstrap_marker = self._read_bootstrap_marker()
            self.runtime_id = self._bootstrap_marker["runtime_id"]
            if self._preexisting["runtime_id"] and self._runtime_id() != self.runtime_id:
                raise HistoryError("bootstrap runtime identity mismatch")
        elif self._preexisting["runtime_id"]:
            self.runtime_id = self._runtime_id()
        elif not any(self._preexisting[k] for k in ("log", "head", "state")):
            # Defer creating runtime_id until a durable bootstrap intent exists.
            self.runtime_id = uuid.uuid4().hex
            self._bootstrap_new = True
        else:
            raise HistoryError("runtime identity missing while state artifacts exist")
        self._lock = threading.RLock()
        self._events = []
        self._by_id = {}
        self._sessions = {}
        self._counters = {}
        # Once a write boundary fails, this instance must not append another event.
        # A fresh StateStore instance must validate and reconcile the durable journal first.
        self._recovery_required = False
        self._load()
        if not self._events:
            if self._bootstrap_new:
                self._start_bootstrap()
            self.emit(GENESIS_EVENT, {"product_id": PRODUCT_ID, "schema": SCHEMA}, correlation_id="genesis")
        self._emit_pending_recovery_events()
        if self._bootstrap_active:
            self._finish_bootstrap()

    def _runtime_id(self):
        """Read an existing runtime identity; creation is gated by bootstrap intent."""
        p = self.runtime_id_path
        if not os.path.exists(p):
            raise HistoryError("runtime identity missing")
        try:
            with open(p, encoding="utf-8") as fh:
                value = fh.read().strip()
        except (OSError, UnicodeDecodeError) as exc:
            raise HistoryError("runtime identity unreadable") from exc
        if not value:
            raise HistoryError("runtime identity empty")
        return value

    def _read_bootstrap_marker(self):
        try:
            with open(self.bootstrap_path, encoding="utf-8") as fh:
                marker = json.loads(fh.read())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HistoryError("bootstrap marker unreadable") from exc
        if not isinstance(marker, dict):
            raise HistoryError("bootstrap marker invalid")
        core = {k: v for k, v in marker.items() if k != "marker_digest"}
        if (set(marker) != {"schema_version", "runtime_id", "expected_genesis", "marker_digest"}
                or marker.get("schema_version") != "HG_STATE_BOOTSTRAP_V1"
                or marker.get("expected_genesis") != GENESIS_EVENT
                or not isinstance(marker.get("runtime_id"), str) or not marker["runtime_id"].strip()
                or marker.get("marker_digest") != digest(core)):
            raise HistoryError("bootstrap marker integrity failure")
        return marker

    def _start_bootstrap(self):
        core = {"schema_version": "HG_STATE_BOOTSTRAP_V1",
                "runtime_id": self.runtime_id, "expected_genesis": GENESIS_EVENT}
        marker = dict(core, marker_digest=digest(core))
        self._atomic_write_bytes(self.bootstrap_path, (canonical(marker) + "\n").encode("utf-8"))
        self._bootstrap_marker = marker
        self._bootstrap_active = True
        self._bootstrap_new = False
        if os.path.exists(self.runtime_id_path):
            if self._runtime_id() != self.runtime_id:
                raise HistoryError("bootstrap runtime identity mismatch")
        else:
            self._atomic_write_bytes(self.runtime_id_path, (self.runtime_id + "\n").encode("utf-8"))
        self._write_state()
        self._write_head()

    def _ensure_bootstrap_baseline(self):
        """Recreate only empty seq-0 derived artifacts while a valid bootstrap intent exists."""
        marker = self._read_bootstrap_marker()
        if marker["runtime_id"] != self.runtime_id:
            raise HistoryError("bootstrap runtime identity mismatch")
        if os.path.exists(self.runtime_id_path):
            if self._runtime_id() != self.runtime_id:
                raise HistoryError("bootstrap runtime identity mismatch")
        else:
            self._atomic_write_bytes(self.runtime_id_path, (self.runtime_id + "\n").encode("utf-8"))
        empty_projection = self._projection_for_events([])
        existing_state = self._read_state_projection()
        if existing_state is not None and existing_state != empty_projection:
            raise HistoryError("bootstrap state is not the empty baseline")
        if os.path.exists(self.head):
            hd = self._read_head_checkpoint()
            if hd != {"seq": 0, "head_hash": ZERO}:
                raise HistoryError("bootstrap checkpoint is not the empty baseline")
        if existing_state is None:
            self._write_state()
        if not os.path.exists(self.head):
            self._write_head()

    def _finish_bootstrap(self):
        if not os.path.exists(self.bootstrap_path):
            self._bootstrap_active = False
            return
        if not self._events or self._events[0].get("event_type") != GENESIS_EVENT:
            raise HistoryError("bootstrap completion lacks verified genesis")
        if not self.verify().get("ok"):
            raise HistoryError("bootstrap completion history verification failed")
        if self._read_state_projection() != self._projection_for_events(self._events):
            raise HistoryError("bootstrap completion projection mismatch")
        hd = self._read_head_checkpoint()
        seq, head_hash = self._head()
        if hd != {"seq": seq, "head_hash": head_hash}:
            raise HistoryError("bootstrap completion checkpoint mismatch")
        os.unlink(self.bootstrap_path)
        self._fsync_directory()
        self._bootstrap_active = False

    def _head(self):
        return (0, ZERO) if not self._events else (self._events[-1]["seq"], self._events[-1]["record_hash"])

    def _fsync_directory(self):
        """Persist directory-entry replacements where the filesystem supports it."""
        fd = os.open(self.dir, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _atomic_write_bytes(self, path, data):
        """Write a file via fsynced temp + atomic replace + directory fsync."""
        tmp = path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        self._fsync_directory()

    def _projection_for_events(self, events):
        sessions = {}
        counters = {}
        for rec in events:
            if rec["event_type"] == "session.created" and "session_id" in rec["payload"]:
                sessions[rec["payload"]["session_id"]] = dict(rec["payload"])
            counters[rec["event_type"]] = counters.get(rec["event_type"], 0) + 1
        seq = events[-1]["seq"] if events else 0
        head_hash = events[-1]["record_hash"] if events else ZERO
        return {"schema": SCHEMA, "product_id": PRODUCT_ID, "runtime_id": self.runtime_id,
                "last_seq": seq, "head_hash": head_hash, "sessions": sessions, "counters": counters}

    def _parse_history(self, raw):
        if raw and not raw.endswith(b"\n"):
            raise HistoryError("history log missing final newline")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HistoryError("history unreadable: invalid UTF-8") from exc
        prev, seq, seen, events = ZERO, 0, set(), []
        required = {"seq", "event_id", "event_type", "recorded_at", "correlation_id",
                    "causation_id", "product_id", "runtime_id", "schema", "payload",
                    "prev_hash", "record_hash"}
        for n, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                raise HistoryError("blank history record line %d" % n)
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                raise HistoryError("malformed record line %d" % n) from exc
            if not isinstance(rec, dict):
                raise HistoryError("record is not an object line %d" % n)
            if not required.issubset(rec):
                raise HistoryError("record missing required fields line %d" % n)
            if not isinstance(rec["seq"], int) or isinstance(rec["seq"], bool):
                raise HistoryError("record has invalid field types line %d" % n)
            if rec["seq"] != seq + 1:
                raise HistoryError("sequence gap or invalid sequence line %d" % n)
            if not isinstance(rec["event_id"], str) or not rec["event_id"].strip():
                raise HistoryError("invalid event_id line %d" % n)
            if not isinstance(rec["event_type"], str) or not rec["event_type"].strip():
                raise HistoryError("invalid event_type line %d" % n)
            if (not isinstance(rec["recorded_at"], (int, float)) or isinstance(rec["recorded_at"], bool)
                    or not __import__("math").isfinite(rec["recorded_at"])
                    or not isinstance(rec["correlation_id"], str) or not rec["correlation_id"].strip()
                    or rec["causation_id"] is not None and not isinstance(rec["causation_id"], str)
                    or rec["product_id"] != PRODUCT_ID
                    or not isinstance(rec["runtime_id"], str) or not rec["runtime_id"].strip()
                    or rec["runtime_id"] != self.runtime_id
                    or rec["schema"] != SCHEMA
                    or not isinstance(rec["prev_hash"], str)):
                raise HistoryError("invalid field values line %d" % n)
            if not isinstance(rec["payload"], dict):
                raise HistoryError("invalid payload line %d" % n)
            rh = rec["record_hash"]
            core = {k: v for k, v in rec.items() if k != "record_hash"}
            if not isinstance(rh, str) or not rh or digest(core) != rh:
                raise HistoryError("record hash mismatch line %d" % n)
            if rec["prev_hash"] != prev:
                raise HistoryError("chain break line %d" % n)
            if rec["event_id"] in seen:
                raise HistoryError("duplicate event_id line %d" % n)
            seen.add(rec["event_id"])
            prev, seq = rh, rec["seq"]
            events.append(rec)
        return events

    def _read_head_checkpoint(self):
        if not os.path.exists(self.head):
            raise HistoryError("head checkpoint missing while history log exists")
        try:
            with open(self.head, encoding="utf-8") as fh:
                hd = json.loads(fh.read())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HistoryError("head checkpoint unreadable") from exc
        if not isinstance(hd, dict):
            raise HistoryError("head checkpoint is not an object")
        if (not isinstance(hd.get("seq"), int) or isinstance(hd.get("seq"), bool)
                or hd["seq"] < 0 or not isinstance(hd.get("head_hash"), str)
                or len(hd["head_hash"]) != 64
                or any(ch not in "0123456789abcdef" for ch in hd["head_hash"])):
            raise HistoryError("head checkpoint invalid")
        if hd["seq"] == 0 and (not self._bootstrap_active or hd["head_hash"] != ZERO):
            raise HistoryError("zero checkpoint allowed only for verified bootstrap intent")
        return hd

    def _read_state_projection(self):
        if not os.path.exists(self.state):
            return None
        try:
            with open(self.state, encoding="utf-8") as fh:
                doc = json.loads(fh.read())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HistoryError("state projection unreadable") from exc
        if not isinstance(doc, dict):
            raise HistoryError("state projection is not an object")
        return doc

    def _write_recovery_receipt(self, reason, evidence):
        """Persist an evidence receipt; it never authorizes state repair by itself."""
        core = {"schema_version": "HG_STATE_RECOVERY_V1", "reason": reason, "evidence": evidence}
        recovery_id = digest(core)
        receipt = dict(core, recovery_id=recovery_id)
        path = os.path.join(self.dir, "history.recovery." + recovery_id + ".json")
        encoded = (canonical(receipt) + "\n").encode("utf-8")
        if os.path.exists(path):
            try:
                with open(path, "rb") as fh:
                    prior = fh.read()
            except OSError as exc:
                raise HistoryError("recovery receipt unreadable") from exc
            if prior != encoded:
                raise HistoryError("recovery receipt conflicts with computed evidence")
        else:
            self._atomic_write_bytes(path, encoded)
        return receipt

    def _quarantine_incomplete_tail(self, tail):
        tail_hash = hashlib.sha256(tail).hexdigest()
        path = os.path.join(self.dir, "history.incomplete-tail." + tail_hash + ".bin")
        if os.path.exists(path):
            try:
                with open(path, "rb") as fh:
                    existing = fh.read()
            except OSError as exc:
                raise HistoryError("incomplete tail evidence unreadable") from exc
            if existing != tail:
                raise HistoryError("incomplete tail evidence hash collision or tamper")
        else:
            self._atomic_write_bytes(path, tail)
        return tail_hash

    def _truncate_journal(self, offset):
        with open(self.log, "r+b") as fh:
            fh.truncate(offset)
            fh.flush()
            os.fsync(fh.fileno())
        self._fsync_directory()

    def _emit_pending_recovery_events(self):
        """Append stable audit events for receipts after the journal is consistent."""
        receipts = []
        for name in sorted(os.listdir(self.dir)):
            if not (name.startswith("history.recovery.") and name.endswith(".json")):
                continue
            path = os.path.join(self.dir, name)
            try:
                with open(path, encoding="utf-8") as fh:
                    receipt = json.loads(fh.read())
                recovery_id = receipt.get("recovery_id") if isinstance(receipt, dict) else None
                core = {k: v for k, v in receipt.items() if k != "recovery_id"} if isinstance(receipt, dict) else None
                if (not isinstance(recovery_id, str) or not isinstance(core, dict)
                        or receipt.get("schema_version") != "HG_STATE_RECOVERY_V1"
                        or digest(core) != recovery_id
                        or name != "history.recovery." + recovery_id + ".json"):
                    continue
                receipts.append(receipt)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
                # Auxiliary recovery evidence cannot override a verified journal.
                continue
        for receipt in receipts:
            recovery_id = receipt["recovery_id"]
            if any(e.get("event_type") == "history.state.recovered"
                   and (e.get("payload") or {}).get("recovery_id") == recovery_id
                   for e in self._events):
                continue
            self.emit("history.state.recovered",
                      {"recovery_id": recovery_id, "reason": receipt["reason"],
                       "evidence": receipt["evidence"]},
                      correlation_id="recovery:" + recovery_id,
                      event_id="state-recovered:" + recovery_id)

    def _load(self):
        have_log = self._preexisting["log"]
        have_head = self._preexisting["head"]
        have_state = self._preexisting["state"]
        have_rid = self._preexisting["runtime_id"]
        if not have_log:
            if self._bootstrap_active:
                self._ensure_bootstrap_baseline()
                return
            if have_head or have_state or have_rid or self._preexisting["bootstrap"]:
                raise HistoryError("history log missing while other state artifacts exist")
            return

        try:
            with open(self.log, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            raise HistoryError("history log unreadable") from exc

        incomplete_tail = None
        valid_len = len(raw)
        if raw and not raw.endswith(b"\n"):
            valid_len = raw.rfind(b"\n") + 1
            incomplete_tail = raw[valid_len:]
            if valid_len <= 0 and not self._bootstrap_active:
                raise HistoryError("history log has no complete record for safe recovery")
            # A complete JSON frame missing only its delimiter is ambiguous: it may
            # be a valid committed event whose newline was lost. Never discard it.
            try:
                json.loads(incomplete_tail.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
            else:
                raise HistoryError("complete journal record missing final newline")
        events = self._parse_history(raw[:valid_len])
        if not events:
            if self._bootstrap_active and (not raw or incomplete_tail is not None):
                # The bootstrap marker and seq-0 checkpoint prove genesis was not
                # committed. Preserve an incomplete frame, then retry genesis later.
                self._ensure_bootstrap_baseline()
                if incomplete_tail is not None:
                    hd = self._read_head_checkpoint()
                    if hd != {"seq": 0, "head_hash": ZERO}:
                        raise HistoryError("partial genesis lacks the empty checkpoint anchor")
                    if self._read_state_projection() != self._projection_for_events([]):
                        raise HistoryError("partial genesis lacks the empty projection anchor")
                    tail_hash = self._quarantine_incomplete_tail(incomplete_tail)
                    self._write_recovery_receipt(
                        "INCOMPLETE_GENESIS_FRAME_QUARANTINED",
                        {"base_seq": 0, "base_hash": ZERO, "tail_sha256": tail_hash,
                         "tail_bytes": len(incomplete_tail), "verified_prefix_bytes": 0},
                    )
                    self._truncate_journal(0)
                self._events, self._by_id, self._sessions, self._counters = [], {}, {}, {}
                return
            raise HistoryError("history log has no verified event")

        self._events = events
        self._by_id = {rec["event_id"]: rec for rec in events}
        self._sessions = {}
        self._counters = {}
        for rec in events:
            self._apply(rec)

        hd = self._read_head_checkpoint()
        head_seq, head_hash = hd["seq"], hd["head_hash"]
        if head_seq == 0:
            if not (self._bootstrap_active and head_hash == ZERO and len(events) == 1
                    and events[0].get("event_type") == GENESIS_EVENT):
                raise HistoryError("zero checkpoint is not anchored by bootstrap genesis")
        elif head_seq > len(events) or events[head_seq - 1]["record_hash"] != head_hash:
            raise HistoryError("head checkpoint is not an ancestor of verified history")
        tail_seq = len(events)
        tail_hash = events[-1]["record_hash"]
        projection = self._read_state_projection()
        expected_tail = self._projection_for_events(events)

        if incomplete_tail is not None:
            # A partial frame can be discarded only when the last complete journal
            # record is anchored by BOTH the head checkpoint and matching projection.
            if head_seq != tail_seq or projection != expected_tail:
                raise HistoryError("incomplete journal tail lacks matching checkpoint and projection")
            tail_hash_raw = self._quarantine_incomplete_tail(incomplete_tail)
            self._write_recovery_receipt(
                "INCOMPLETE_JOURNAL_TAIL_QUARANTINED",
                {"base_seq": tail_seq, "base_hash": tail_hash, "tail_sha256": tail_hash_raw,
                 "tail_bytes": len(incomplete_tail), "verified_prefix_bytes": valid_len},
            )
            self._truncate_journal(valid_len)
        elif head_seq == tail_seq:
            if projection != expected_tail:
                raise HistoryError("state projection does not match history")
        elif head_seq == tail_seq - 1:
            # The only recoverable complete-frame split write is one event beyond
            # an anchored head. State must match the known pre- or post-projection.
            expected_head = self._projection_for_events(events[:head_seq])
            if projection not in (expected_head, expected_tail):
                raise HistoryError("state projection matches neither side of interrupted commit")
            self._write_recovery_receipt(
                "ONE_EVENT_AHEAD_OF_CHECKPOINT",
                {"prior_head_seq": head_seq, "prior_head_hash": head_hash,
                 "recovered_tail_seq": tail_seq, "recovered_tail_hash": tail_hash,
                 "recovered_event_id": events[-1]["event_id"]},
            )
            self._write_state()
            self._write_head()
        else:
            raise HistoryError("checkpoint lag exceeds safe one-event recovery window")


    def _apply(self, rec):
        if rec["event_type"] == "session.created" and "session_id" in rec["payload"]:
            self._sessions[rec["payload"]["session_id"]] = dict(rec["payload"])
        self._counters[rec["event_type"]] = self._counters.get(rec["event_type"], 0) + 1

    def _doc(self):
        s, h = self._head()
        return {"schema": SCHEMA, "product_id": PRODUCT_ID, "runtime_id": self.runtime_id, "last_seq": s,
                "head_hash": h, "sessions": self._sessions, "counters": self._counters}

    def _write_state(self):
        self._atomic_write_bytes(self.state, canonical(self._doc()).encode("utf-8"))

    def _write_head(self):
        s, h = self._head()
        self._atomic_write_bytes(self.head, canonical({"seq": s, "head_hash": h}).encode("utf-8"))

    def emit(self, event_type, payload, *, correlation_id=None, causation_id=None, event_id=None):
        with self._lock:
            if self._recovery_required:
                raise HistoryError("state recovery required; reopen StateStore before further writes")
            if not isinstance(event_type, str) or not event_type.strip():
                raise HistoryError("event_type must be a non-empty string")
            if not isinstance(payload, dict):
                raise HistoryError("payload must be an object")
            try:
                json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False)
            except (TypeError, ValueError) as exc:
                raise HistoryError("payload is not canonical JSON data") from exc
            if correlation_id is not None and (not isinstance(correlation_id, str) or not correlation_id.strip()):
                raise HistoryError("correlation_id must be a non-empty string or null")
            if causation_id is not None and not isinstance(causation_id, str):
                raise HistoryError("causation_id must be a string or null")
            if (event_type == "session.created" and "session_id" in payload
                    and (not isinstance(payload["session_id"], str) or not payload["session_id"].strip())):
                raise HistoryError("session_id must be a non-empty string")
            if event_id is not None:
                if not isinstance(event_id, str) or not event_id.strip():
                    raise HistoryError("event_id must be a non-empty string")
                existing = self._by_id.get(event_id)
                if existing is not None:
                    # Idempotency means the same identity and same operation, not
                    # silently accepting a different event body under an old ID.
                    same_operation = (
                        existing.get("event_type") == event_type
                        and canonical(existing.get("payload")) == canonical(payload)
                        and (correlation_id is None or existing.get("correlation_id") == correlation_id)
                        and (causation_id is None or existing.get("causation_id") == causation_id)
                    )
                    if not same_operation:
                        raise HistoryError("event_id reused for a different operation")
                    return existing
            recorded_at = self._clock()
            if (not isinstance(recorded_at, (int, float)) or isinstance(recorded_at, bool)
                    or not __import__("math").isfinite(recorded_at)):
                raise HistoryError("recorded_at clock must return a finite number")
            seq = (self._events[-1]["seq"] if self._events else 0) + 1
            prev = self._events[-1]["record_hash"] if self._events else ZERO
            core = {"seq": seq, "event_id": event_id or uuid.uuid4().hex, "event_type": event_type,
                    "recorded_at": recorded_at, "correlation_id": correlation_id or uuid.uuid4().hex,
                    "causation_id": causation_id, "product_id": PRODUCT_ID, "runtime_id": self.runtime_id,
                    "schema": SCHEMA, "payload": payload, "prev_hash": prev}
            rec = dict(core)
            rec["record_hash"] = digest(core)
            try:
                with open(self.log, "a", encoding="utf-8") as fh:
                    fh.write(canonical(rec) + "\n")
                    fh.flush()
                    os.fsync(fh.fileno())
            except BaseException:
                # The append outcome may be absent, partial or complete. Require a
                # fresh instance to inspect disk evidence before any further mutation.
                self._recovery_required = True
                raise
            try:
                self._events.append(rec)
                self._by_id[rec["event_id"]] = rec
                self._apply(rec)
                self._write_state()
                self._write_head()
            except BaseException:
                # Once the journal append may have committed, any projection/application
                # failure requires a fresh, disk-validated instance before another write.
                self._recovery_required = True
                raise
            return rec

    def verify(self):
        if not os.path.exists(self.log):
            if os.path.exists(self.head) or os.path.exists(self.state):
                return {"ok": False, "events": 0, "reason": "log_missing_while_state_present"}
            return {"ok": True, "events": 0, "reason": "empty_log"}
        prev, seq, seen, n = ZERO, 0, set(), 0
        required = {"seq", "event_id", "event_type", "recorded_at", "correlation_id",
                    "causation_id", "product_id", "runtime_id", "schema", "payload",
                    "prev_hash", "record_hash"}
        try:
            with open(self.log, "rb") as fh:
                raw = fh.read()
            if raw and not raw.endswith(b"\n"):
                return {"ok": False, "events": 0, "reason": "missing_final_newline"}
            text = raw.decode("utf-8")
            for lineno, line in enumerate(text.splitlines(), 1):
                if not line.strip():
                    return {"ok": False, "events": n, "reason": "blank_line_%d" % lineno}
                rec = json.loads(line)
                if not isinstance(rec, dict):
                    return {"ok": False, "events": n, "reason": "record_not_object_line_%d" % lineno}
                if not required.issubset(rec):
                    return {"ok": False, "events": n, "reason": "record_missing_fields_line_%d" % lineno}
                if not isinstance(rec["seq"], int) or isinstance(rec["seq"], bool):
                    return {"ok": False, "events": n, "reason": "record_invalid_field_types_line_%d" % lineno}
                if rec["seq"] != seq + 1:
                    return {"ok": False, "events": n, "reason": "sequence_gap_line_%d" % lineno}
                if not isinstance(rec["event_id"], str) or not rec["event_id"].strip():
                    return {"ok": False, "events": n, "reason": "invalid_event_id_line_%d" % lineno}
                if not isinstance(rec["event_type"], str) or not rec["event_type"].strip():
                    return {"ok": False, "events": n, "reason": "invalid_event_type_line_%d" % lineno}
                if (not isinstance(rec["recorded_at"], (int, float)) or isinstance(rec["recorded_at"], bool)
                        or not __import__("math").isfinite(rec["recorded_at"])
                        or not isinstance(rec["correlation_id"], str) or not rec["correlation_id"].strip()
                        or rec["causation_id"] is not None and not isinstance(rec["causation_id"], str)
                        or rec["product_id"] != PRODUCT_ID
                        or not isinstance(rec["runtime_id"], str) or not rec["runtime_id"].strip()
                        or rec["runtime_id"] != self.runtime_id
                        or rec["schema"] != SCHEMA
                        or not isinstance(rec["prev_hash"], str)):
                    return {"ok": False, "events": n, "reason": "record_invalid_field_types_line_%d" % lineno}
                if not isinstance(rec["payload"], dict):
                    return {"ok": False, "events": n, "reason": "record_invalid_field_types_line_%d" % lineno}
                rh = rec["record_hash"]
                core = {k: v for k, v in rec.items() if k != "record_hash"}
                if not isinstance(rh, str) or not rh or digest(core) != rh:
                    return {"ok": False, "events": n, "reason": "record_hash_mismatch_line_%d" % lineno}
                if rec["prev_hash"] != prev:
                    return {"ok": False, "events": n, "reason": "chain_break_line_%d" % lineno}
                if rec["event_id"] in seen:
                    return {"ok": False, "events": n, "reason": "duplicate_event_id_line_%d" % lineno}
                seen.add(rec["event_id"])
                prev, seq, n = rh, rec["seq"], n + 1
        except UnicodeDecodeError:
            return {"ok": False, "events": n, "reason": "history_unreadable"}
        except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError, AttributeError):
            return {"ok": False, "events": n, "reason": "malformed_record"}
        if os.path.exists(self.head):
            try:
                with open(self.head, encoding="utf-8") as fh:
                    hd = json.loads(fh.read())
                if not isinstance(hd, dict):
                    return {"ok": False, "events": n, "reason": "checkpoint_not_object"}
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                return {"ok": False, "events": n, "reason": "checkpoint_unreadable"}
            if hd.get("seq") != seq or hd.get("head_hash") != prev:
                return {"ok": False, "events": n, "reason": "checkpoint_mismatch"}
        return {"ok": True, "events": n, "head_hash": prev, "reason": "chain_ok"}

    def replay(self):
        return [dict(e) for e in self._events]

    def audit_export(self):
        s, h = self._head()
        return {"schema": SCHEMA, "product_id": PRODUCT_ID, "runtime_id": self.runtime_id,
                "events": len(self._events), "last_seq": s, "head_hash": h, "verify": self.verify(),
                "state": self._doc()}
