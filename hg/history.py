"""Append-only, hash-chained HG state and history. Fail-closed on any integrity failure."""
from __future__ import annotations

import hashlib, json, math, os, threading, time, uuid

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


class StateStore:
    def __init__(self, directory, *, clock=time.time):
        self.dir = str(directory)
        os.makedirs(self.dir, exist_ok=True)
        self.log = os.path.join(self.dir, "history.jsonl")
        self.head = os.path.join(self.dir, "head.json")
        self.state = os.path.join(self.dir, "state.json")
        self._clock = clock
        self._preexisting = {"log": os.path.exists(self.log), "head": os.path.exists(self.head),
                             "state": os.path.exists(self.state),
                             "runtime_id": os.path.exists(os.path.join(self.dir, "runtime_id"))}
        present = {name for name, exists in self._preexisting.items() if exists}
        if present and len(present) != len(self._preexisting):
            raise HistoryError("incomplete state artifact set: " + ",".join(sorted(present)))
        self.runtime_id = self._runtime_id()
        self._lock = threading.RLock()
        self._events = []
        self._by_id = {}
        self._sessions = {}
        self._counters = {}
        self._load()
        if not self._events:
            self.emit(GENESIS_EVENT, {"product_id": PRODUCT_ID, "schema": SCHEMA}, correlation_id="genesis")

    def _runtime_id(self):
        p = os.path.join(self.dir, "runtime_id")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                v = fh.read().strip()
            if v:
                return v
        v = uuid.uuid4().hex
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(v + "\n")
        return v

    def _head(self):
        return (0, ZERO) if not self._events else (self._events[-1]["seq"], self._events[-1]["record_hash"])

    @staticmethod
    def _record_shape_error(rec, lineno, expected_runtime_id=None):
        """Return a stable validation error for a decoded history record."""
        if not isinstance(rec, dict):
            return "record is not an object line %d" % lineno
        required = {
            "seq", "event_id", "event_type", "recorded_at", "correlation_id",
            "causation_id", "product_id", "runtime_id", "schema", "payload",
            "prev_hash", "record_hash",
        }
        if not required.issubset(rec):
            return "record missing required fields line %d" % lineno
        if (isinstance(rec["seq"], bool) or not isinstance(rec["seq"], int)
                or rec["seq"] < 1
                or not isinstance(rec["event_id"], str) or not rec["event_id"].strip()
                or not isinstance(rec["event_type"], str) or not rec["event_type"].strip()
                or isinstance(rec["recorded_at"], bool)
                or not isinstance(rec["recorded_at"], (int, float))
                or (isinstance(rec["recorded_at"], float) and not math.isfinite(rec["recorded_at"]))
                or not isinstance(rec["correlation_id"], str) or not rec["correlation_id"].strip()
                or (rec["causation_id"] is not None and not isinstance(rec["causation_id"], str))
                or rec["product_id"] != PRODUCT_ID
                or not isinstance(rec["runtime_id"], str) or not rec["runtime_id"].strip()
                or rec["schema"] != SCHEMA
                or not isinstance(rec["payload"], dict)
                or not isinstance(rec["prev_hash"], str)
                or not isinstance(rec["record_hash"], str)):
            return "record has invalid field types or identity line %d" % lineno
        if expected_runtime_id is not None and rec["runtime_id"] != expected_runtime_id:
            return "record runtime_id mismatch line %d" % lineno
        return None

    def _load(self):
        have_log = self._preexisting["log"]
        have_head = self._preexisting["head"]
        have_state = self._preexisting["state"]
        have_rid = self._preexisting["runtime_id"]
        if not have_log:
            if have_head or have_state or have_rid:
                raise HistoryError("history log missing while other state artifacts exist")
            return
        if not have_head:
            raise HistoryError("head checkpoint missing while history log exists")
        prev, seq, seen = ZERO, 0, set()
        try:
            with open(self.log, encoding="utf-8") as fh:
                for n, line in enumerate(fh, 1):
                    if not line.endswith("\n"):
                        raise HistoryError("incomplete append line %d" % n)
                    if not line.strip():
                        raise HistoryError("blank history line %d" % n)
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise HistoryError("malformed record line %d" % n) from exc
                    shape_error = self._record_shape_error(rec, n, self.runtime_id)
                    if shape_error:
                        raise HistoryError(shape_error)
                    rh = rec["record_hash"]
                    core = {k: v for k, v in rec.items() if k != "record_hash"}
                    if digest(core) != rh:
                        raise HistoryError("record hash mismatch line %d" % n)
                    if rec["prev_hash"] != prev:
                        raise HistoryError("chain break line %d" % n)
                    if rec["seq"] != seq + 1:
                        raise HistoryError("sequence gap line %d" % n)
                    if rec["event_id"] in seen:
                        raise HistoryError("duplicate event_id line %d" % n)
                    seen.add(rec["event_id"])
                    prev, seq = rh, rec["seq"]
                    self._events.append(rec)
                    self._by_id[rec["event_id"]] = rec
                    self._apply(rec)
        except (OSError, UnicodeError) as exc:
            raise HistoryError("history unreadable") from exc
        if os.path.exists(self.head):
            try:
                with open(self.head, encoding="utf-8") as fh:
                    hd = json.load(fh)
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise HistoryError("head checkpoint unreadable") from exc
            expected_head = {"seq": seq, "head_hash": prev}
            if not isinstance(hd, dict):
                raise HistoryError("head checkpoint is not an object")
            if hd != expected_head:
                raise HistoryError("log does not match head checkpoint")
        self._checkpoint_check()
        if have_state:
            self._projection_check()
        self._write_state()
        self._write_head()

    def _checkpoint_check(self):
        try:
            with open(self.head, encoding="utf-8") as fh:
                hd = json.loads(fh.read())
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise HistoryError("head checkpoint unreadable") from exc
        if not isinstance(hd, dict):
            raise HistoryError("head checkpoint is not an object")
        s, h = self._head()
        if hd != {"seq": s, "head_hash": h}:
            raise HistoryError("log does not match head checkpoint")

    def _projection_check(self):
        try:
            with open(self.state, encoding="utf-8") as fh:
                doc = json.loads(fh.read())
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise HistoryError("state projection unreadable") from exc
        if not isinstance(doc, dict):
            raise HistoryError("state projection is not an object")
        current = self._doc()
        # The projection is a derived cache, but any divergence is an integrity
        # failure. Do not silently repair it during startup: an operator must
        # explicitly investigate the discrepancy before recovery is permitted.
        if doc != current:
            raise HistoryError("state projection does not match history")

    def _apply(self, rec):
        if rec["event_type"] == "session.created" and "session_id" in rec["payload"]:
            self._sessions[rec["payload"]["session_id"]] = dict(rec["payload"])
        self._counters[rec["event_type"]] = self._counters.get(rec["event_type"], 0) + 1

    def _doc(self):
        s, h = self._head()
        return {"schema": SCHEMA, "product_id": PRODUCT_ID, "runtime_id": self.runtime_id, "last_seq": s,
                "head_hash": h, "sessions": self._sessions, "counters": self._counters}

    def _write_state(self):
        tmp = self.state + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(canonical(self._doc()))
        os.replace(tmp, self.state)

    def _write_head(self):
        tmp = self.head + ".tmp"
        s, h = self._head()
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(canonical({"seq": s, "head_hash": h}))
        os.replace(tmp, self.head)

    def emit(self, event_type, payload, *, correlation_id=None, causation_id=None, event_id=None):
        with self._lock:
            if event_id and event_id in self._by_id:
                existing = self._by_id[event_id]
                if existing["event_type"] != event_type or existing["payload"] != payload:
                    raise HistoryError("event_id_conflict")
                return existing
            seq = (self._events[-1]["seq"] if self._events else 0) + 1
            prev = self._events[-1]["record_hash"] if self._events else ZERO
            core = {"seq": seq, "event_id": event_id or uuid.uuid4().hex, "event_type": event_type,
                    "recorded_at": self._clock(), "correlation_id": correlation_id or uuid.uuid4().hex,
                    "causation_id": causation_id, "product_id": PRODUCT_ID, "runtime_id": self.runtime_id,
                    "schema": SCHEMA, "payload": payload, "prev_hash": prev}
            rec = dict(core)
            rec["record_hash"] = digest(core)
            with open(self.log, "a", encoding="utf-8") as fh:
                fh.write(canonical(rec) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            self._events.append(rec)
            self._by_id[rec["event_id"]] = rec
            self._apply(rec)
            self._write_state()
            self._write_head()
            return rec

    def verify(self):
        if not os.path.exists(self.log):
            if any(os.path.exists(path) for path in (self.head, self.state, os.path.join(self.dir, "runtime_id"))):
                return {"ok": False, "events": 0, "reason": "log_missing_while_state_present"}
            return {"ok": True, "events": 0, "reason": "empty_log"}
        prev, seq, seen, n = ZERO, 0, set(), 0
        try:
            with open(os.path.join(self.dir, "runtime_id"), encoding="utf-8") as fh:
                expected_runtime_id = fh.read().strip()
            if not expected_runtime_id:
                return {"ok": False, "events": 0, "reason": "runtime_id_invalid"}
        except (OSError, UnicodeError):
            expected_runtime_id = None
        try:
            with open(self.log, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    if not line.endswith("\n"):
                        return {"ok": False, "events": n, "reason": "incomplete_append_line_%d" % lineno}
                    if not line.strip():
                        return {"ok": False, "events": n, "reason": "blank_history_line_%d" % lineno}
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        return {"ok": False, "events": n, "reason": "malformed_record_line_%d" % lineno}
                    shape_error = self._record_shape_error(rec, lineno, expected_runtime_id)
                    if shape_error:
                        if "not an object" in shape_error:
                            reason = "record_not_object_line_%d" % lineno
                        elif "missing required fields" in shape_error:
                            reason = "record_missing_fields_line_%d" % lineno
                        elif "runtime_id mismatch" in shape_error:
                            reason = "record_runtime_id_mismatch_line_%d" % lineno
                        else:
                            reason = "record_invalid_field_types_line_%d" % lineno
                        return {"ok": False, "events": n, "reason": reason}
                    rh = rec["record_hash"]
                    core = {k: v for k, v in rec.items() if k != "record_hash"}
                    if digest(core) != rh:
                        return {"ok": False, "events": n, "reason": "record_hash_mismatch_line_%d" % lineno}
                    if rec["prev_hash"] != prev:
                        return {"ok": False, "events": n, "reason": "chain_break_line_%d" % lineno}
                    if rec["seq"] != seq + 1:
                        return {"ok": False, "events": n, "reason": "sequence_gap_line_%d" % lineno}
                    if rec["event_id"] in seen:
                        return {"ok": False, "events": n, "reason": "duplicate_event_id_line_%d" % lineno}
                    seen.add(rec["event_id"])
                    prev, seq, n = rh, rec["seq"], n + 1
        except (OSError, UnicodeError):
            return {"ok": False, "events": n, "reason": "history_unreadable"}
        if expected_runtime_id is None:
            return {"ok": False, "events": n, "reason": "runtime_id_unreadable"}
        if not os.path.exists(self.head):
            return {"ok": False, "events": n, "reason": "checkpoint_missing"}
        if not os.path.exists(self.state):
            return {"ok": False, "events": n, "reason": "state_projection_missing"}
        if os.path.exists(self.head):
            try:
                with open(self.head, encoding="utf-8") as fh:
                    hd = json.load(fh)
            except (OSError, UnicodeError, json.JSONDecodeError):
                return {"ok": False, "events": n, "reason": "checkpoint_unreadable"}
            if not isinstance(hd, dict):
                return {"ok": False, "events": n, "reason": "checkpoint_not_object"}
            if hd != {"seq": seq, "head_hash": prev}:
                return {"ok": False, "events": n, "reason": "checkpoint_mismatch"}
        try:
            with open(self.state, encoding="utf-8") as fh:
                projection = json.load(fh)
            if not isinstance(projection, dict) or projection != self._doc():
                return {"ok": False, "events": n, "reason": "state_projection_mismatch"}
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {"ok": False, "events": n, "reason": "state_projection_unreadable"}
        return {"ok": True, "events": n, "head_hash": prev, "reason": "chain_ok"}

    def replay(self):
        return [dict(e) for e in self._events]

    def audit_export(self):
        s, h = self._head()
        return {"schema": SCHEMA, "product_id": PRODUCT_ID, "runtime_id": self.runtime_id,
                "events": len(self._events), "last_seq": s, "head_hash": h, "verify": self.verify(),
                "state": self._doc()}
