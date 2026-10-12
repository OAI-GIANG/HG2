"""Append-only, hash-chained HG state and history. Fail-closed on integrity failures."""
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
    """Raised when durable history or its derived artifacts are not trustworthy."""


class StateStore:
    def __init__(self, directory, *, clock=time.time):
        self.dir = str(directory)
        os.makedirs(self.dir, exist_ok=True)
        self.log = os.path.join(self.dir, "history.jsonl")
        self.head = os.path.join(self.dir, "head.json")
        self.state = os.path.join(self.dir, "state.json")
        self._clock = clock
        self._lock = threading.RLock()
        self._events = []
        self._by_id = {}
        self._sessions = {}
        self._counters = {}
        self.runtime_id = self._runtime_id()
        self._load()
        if not self._events:
            # An empty directory is the only state that may be initialized implicitly.
            self.emit(GENESIS_EVENT, {"product_id": PRODUCT_ID, "schema": SCHEMA}, correlation_id="genesis")

    def _runtime_id(self):
        p = os.path.join(self.dir, "runtime_id")
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    v = fh.read().strip()
            except (OSError, UnicodeError) as exc:
                raise HistoryError("runtime_id unreadable") from exc
            if not v:
                raise HistoryError("runtime_id empty")
            return v
        # Creation is permitted only for a genuinely new store; do not repair an existing one.
        if any(os.path.exists(p) for p in (self.log, self.head, self.state)):
            raise HistoryError("runtime_id missing while store artifacts exist")
        v = uuid.uuid4().hex
        with open(p, "x", encoding="utf-8") as fh:
            fh.write(v + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return v

    def _head(self):
        return (0, ZERO) if not self._events else (self._events[-1]["seq"], self._events[-1]["record_hash"])

    @staticmethod
    def _read_json(path, label):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise HistoryError("%s missing or malformed" % label) from exc

    def _load(self):
        artifacts = (self.log, self.head, self.state)
        present = tuple(os.path.exists(p) for p in artifacts)
        if not any(present):
            return
        if not all(present):
            missing = [label for label, exists in zip(("history", "head checkpoint", "state projection"), present) if not exists]
            raise HistoryError("required artifact missing: " + ", ".join(missing))

        prev, seq, seen = ZERO, 0, set()
        try:
            with open(self.log, encoding="utf-8") as fh:
                for n, line in enumerate(fh, 1):
                    if not line.endswith("\n"):
                        raise HistoryError("incomplete append line %d" % n)
                    line = line.strip()
                    if not line:
                        raise HistoryError("blank history line %d" % n)
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise HistoryError("malformed record line %d" % n) from exc
                    try:
                        rh = rec.get("record_hash")
                        core = {k: v for k, v in rec.items() if k != "record_hash"}
                        if not rh or digest(core) != rh:
                            raise HistoryError("record hash mismatch line %d" % n)
                        if rec["prev_hash"] != prev:
                            raise HistoryError("chain break line %d" % n)
                        if rec["seq"] != seq + 1:
                            raise HistoryError("sequence gap line %d" % n)
                        if not rec.get("event_id") or rec["event_id"] in seen:
                            raise HistoryError("duplicate or missing event_id line %d" % n)
                        if rec.get("schema") != SCHEMA or rec.get("product_id") != PRODUCT_ID or rec.get("runtime_id") != self.runtime_id:
                            raise HistoryError("record identity mismatch line %d" % n)
                    except (KeyError, TypeError, ValueError) as exc:
                        raise HistoryError("invalid record structure line %d" % n) from exc
                    seen.add(rec["event_id"])
                    prev, seq = rh, rec["seq"]
                    self._events.append(rec)
                    self._by_id[rec["event_id"]] = rec
                    self._apply(rec)
        except (OSError, UnicodeError) as exc:
            raise HistoryError("history unreadable") from exc

        hd = self._read_json(self.head, "head checkpoint")
        expected_head = {"seq": seq, "head_hash": prev}
        if hd != expected_head:
            raise HistoryError("log does not match head checkpoint")
        projected = self._read_json(self.state, "state projection")
        expected_state = self._doc()
        if projected != expected_state:
            raise HistoryError("state projection does not match history replay")

    def _apply(self, rec):
        payload = rec.get("payload")
        if rec.get("event_type") == "session.created" and isinstance(payload, dict) and "session_id" in payload:
            self._sessions[payload["session_id"]] = dict(payload)
        event_type = rec.get("event_type")
        self._counters[event_type] = self._counters.get(event_type, 0) + 1

    def _doc(self):
        s, h = self._head()
        return {"schema": SCHEMA, "product_id": PRODUCT_ID, "runtime_id": self.runtime_id, "last_seq": s,
                "head_hash": h, "sessions": self._sessions, "counters": self._counters}

    def _write_state(self):
        tmp = self.state + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(canonical(self._doc()))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.state)

    def _write_head(self):
        tmp = self.head + ".tmp"
        s, h = self._head()
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(canonical({"seq": s, "head_hash": h}))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.head)

    def emit(self, event_type, payload, *, correlation_id=None, causation_id=None, event_id=None):
        with self._lock:
            if event_id and event_id in self._by_id:
                return self._by_id[event_id]
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
        """Independently replay disk history and compare every durable artifact."""
        try:
            if not all(os.path.exists(p) for p in (self.log, self.head, self.state, os.path.join(self.dir, "runtime_id"))):
                return {"ok": False, "events": 0, "reason": "required_artifact_missing"}
            runtime_id = self._read_runtime_id_for_verify()
            prev, seq, seen, n = ZERO, 0, set(), 0
            sessions, counters = {}, {}
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
                    try:
                        rh = rec.get("record_hash")
                        core = {k: v for k, v in rec.items() if k != "record_hash"}
                        if not rh or digest(core) != rh:
                            return {"ok": False, "events": n, "reason": "record_hash_mismatch_line_%d" % lineno}
                        if rec["prev_hash"] != prev:
                            return {"ok": False, "events": n, "reason": "chain_break_line_%d" % lineno}
                        if rec["seq"] != seq + 1:
                            return {"ok": False, "events": n, "reason": "sequence_gap_line_%d" % lineno}
                        if not rec.get("event_id") or rec["event_id"] in seen:
                            return {"ok": False, "events": n, "reason": "duplicate_event_id_line_%d" % lineno}
                        if rec.get("schema") != SCHEMA or rec.get("product_id") != PRODUCT_ID or rec.get("runtime_id") != runtime_id:
                            return {"ok": False, "events": n, "reason": "record_identity_mismatch_line_%d" % lineno}
                    except (KeyError, TypeError, ValueError):
                        return {"ok": False, "events": n, "reason": "invalid_record_structure_line_%d" % lineno}
                    seen.add(rec["event_id"])
                    prev, seq, n = rh, rec["seq"], n + 1
                    event_type, payload = rec.get("event_type"), rec.get("payload")
                    counters[event_type] = counters.get(event_type, 0) + 1
                    if event_type == "session.created" and isinstance(payload, dict) and "session_id" in payload:
                        sessions[payload["session_id"]] = dict(payload)
            hd = self._read_json(self.head, "head checkpoint")
            if hd != {"seq": seq, "head_hash": prev}:
                return {"ok": False, "events": n, "reason": "checkpoint_mismatch"}
            expected_state = {"schema": SCHEMA, "product_id": PRODUCT_ID, "runtime_id": runtime_id,
                              "last_seq": seq, "head_hash": prev, "sessions": sessions, "counters": counters}
            projected = self._read_json(self.state, "state projection")
            if projected != expected_state:
                return {"ok": False, "events": n, "reason": "projection_mismatch"}
            return {"ok": True, "events": n, "head_hash": prev, "reason": "chain_projection_checkpoint_ok"}
        except HistoryError as exc:
            return {"ok": False, "events": 0, "reason": str(exc).replace(" ", "_").lower()}
        except (OSError, UnicodeError, TypeError, ValueError):
            return {"ok": False, "events": 0, "reason": "artifact_read_or_validation_error"}

    def _read_runtime_id_for_verify(self):
        path = os.path.join(self.dir, "runtime_id")
        try:
            with open(path, encoding="utf-8") as fh:
                value = fh.read().strip()
        except (OSError, UnicodeError) as exc:
            raise HistoryError("runtime_id missing or unreadable") from exc
        if not value:
            raise HistoryError("runtime_id empty")
        return value

    def replay(self):
        return [dict(e) for e in self._events]

    def audit_export(self):
        s, h = self._head()
        return {"schema": SCHEMA, "product_id": PRODUCT_ID, "runtime_id": self.runtime_id,
                "events": len(self._events), "last_seq": s, "head_hash": h, "verify": self.verify(),
                "state": self._doc()}
