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


class StateStore:
    def __init__(self, directory, *, clock=time.time):
        self.dir = str(directory)
        os.makedirs(self.dir, exist_ok=True)
        self.log = os.path.join(self.dir, "history.jsonl")
        self.head = os.path.join(self.dir, "head.json")
        self.state = os.path.join(self.dir, "state.json")
        self._clock = clock
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

    def _load(self):
        if not os.path.exists(self.log):
            return
        prev, seq, seen = ZERO, 0, set()
        with open(self.log, encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise HistoryError("malformed record line %d" % n) from exc
                rh = rec.get("record_hash")
                core = {k: v for k, v in rec.items() if k != "record_hash"}
                if not rh or digest(core) != rh:
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
        if os.path.exists(self.head):
            with open(self.head, encoding="utf-8") as fh:
                hd = json.loads(fh.read())
            s, h = self._head()
            if hd.get("seq") != s or hd.get("head_hash") != h:
                raise HistoryError("log does not match head checkpoint")
        self._write_state()
        self._write_head()

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
        if not os.path.exists(self.log):
            return {"ok": True, "events": 0, "reason": "empty_log"}
        prev, seq, seen, n = ZERO, 0, set(), 0
        try:
            with open(self.log, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    rh = rec.get("record_hash")
                    core = {k: v for k, v in rec.items() if k != "record_hash"}
                    if not rh or digest(core) != rh:
                        return {"ok": False, "events": n, "reason": "record_hash_mismatch_line_%d" % lineno}
                    if rec["prev_hash"] != prev:
                        return {"ok": False, "events": n, "reason": "chain_break_line_%d" % lineno}
                    if rec["seq"] != seq + 1:
                        return {"ok": False, "events": n, "reason": "sequence_gap_line_%d" % lineno}
                    if rec["event_id"] in seen:
                        return {"ok": False, "events": n, "reason": "duplicate_event_id_line_%d" % lineno}
                    seen.add(rec["event_id"])
                    prev, seq, n = rh, rec["seq"], n + 1
        except json.JSONDecodeError:
            return {"ok": False, "events": n, "reason": "malformed_record"}
        if os.path.exists(self.head):
            with open(self.head, encoding="utf-8") as fh:
                hd = json.loads(fh.read())
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
