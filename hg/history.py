"""Append-only, hash-chained HG state and history. Fail-closed on any integrity failure."""
from __future__ import annotations

import json, os, threading, time, uuid

from .contracts import ContractError, canonical_digest, canonical_json, parse_json_no_duplicate_keys

SCHEMA = "HG_STATE_V1"
PRODUCT_ID = "HG"
GENESIS_EVENT = "hg.genesis"
ZERO = "0" * 64


def canonical(o):
    return canonical_json(o)


def digest(o):
    return canonical_digest(o)


class HistoryError(Exception):
    pass


class StateStore:
    def __init__(self, directory, *, clock=time.time):
        self.dir = str(directory)
        os.makedirs(self.dir, exist_ok=True)
        self.log = os.path.join(self.dir, "history.jsonl")
        self.head = os.path.join(self.dir, "head.json")
        self.state = os.path.join(self.dir, "state.json")
        self.runtime_path = os.path.join(self.dir, "runtime_id")
        artifact_paths = {
            "history log": self.log,
            "head checkpoint": self.head,
            "state projection": self.state,
            "runtime identity": self.runtime_path,
        }
        present = {name: os.path.lexists(path) for name, path in artifact_paths.items()}
        self._had_state_artifacts = any(present.values())
        if self._had_state_artifacts:
            missing = [name for name, exists in present.items() if not exists]
            if missing:
                raise HistoryError("incomplete durable state artifacts; missing: " + ", ".join(missing))
        self._clock = clock
        self.runtime_id = self._runtime_id()
        self._lock = threading.RLock()
        self._events = []
        self._by_id = {}
        self._sessions = {}
        self._counters = {}
        self._load()
        if not self._events:
            if self._had_state_artifacts:
                raise HistoryError("history log empty while durable state artifacts exist")
            self.emit(GENESIS_EVENT, {"product_id": PRODUCT_ID, "schema": SCHEMA}, correlation_id="genesis")

    def _runtime_id(self):
        p = self.runtime_path
        if os.path.lexists(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    value = fh.read().strip()
            except OSError as exc:
                raise HistoryError("runtime identity unreadable") from exc
            if not value:
                raise HistoryError("runtime identity malformed")
            return value
        if self._had_state_artifacts:
            raise HistoryError("runtime identity missing while state artifacts exist")
        value = uuid.uuid4().hex
        try:
            with open(p, "x", encoding="utf-8") as fh:
                fh.write(value + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        except OSError as exc:
            raise HistoryError("runtime identity could not be initialized") from exc
        return value

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
                    rec = parse_json_no_duplicate_keys(line)
                except ContractError as exc:
                    raise HistoryError("malformed record line %d" % n) from exc
                if not isinstance(rec, dict):
                    raise HistoryError("record is not an object line %d" % n)
                rh = rec.get("record_hash")
                core = {k: v for k, v in rec.items() if k != "record_hash"}
                if not rh or digest(core) != rh:
                    raise HistoryError("record hash mismatch line %d" % n)
                required = {"seq", "event_id", "event_type", "recorded_at", "correlation_id",
                            "causation_id", "product_id", "runtime_id", "schema", "payload", "prev_hash"}
                if not required.issubset(rec):
                    raise HistoryError("record fields missing line %d" % n)
                if rec.get("product_id") != PRODUCT_ID or rec.get("schema") != SCHEMA:
                    raise HistoryError("identity/schema mismatch line %d" % n)
                if rec.get("runtime_id") != self.runtime_id:
                    raise HistoryError("runtime identity mismatch line %d" % n)
                if rec["prev_hash"] != prev:
                    raise HistoryError("chain break line %d" % n)
                if isinstance(rec["seq"], bool) or not isinstance(rec["seq"], int) or rec["seq"] != seq + 1:
                    raise HistoryError("sequence gap line %d" % n)
                if not isinstance(rec["event_id"], str) or not rec["event_id"] or rec["event_id"] in seen:
                    raise HistoryError("invalid or duplicate event_id line %d" % n)
                if not isinstance(rec["event_type"], str) or not rec["event_type"]:
                    raise HistoryError("invalid event_type line %d" % n)
                if not isinstance(rec["payload"], dict):
                    raise HistoryError("invalid payload line %d" % n)
                seen.add(rec["event_id"])
                prev, seq = rh, rec["seq"]
                self._events.append(rec)
                self._by_id[rec["event_id"]] = rec
                self._apply(rec)
        if self._had_state_artifacts and not self._events:
            raise HistoryError("history log empty while durable state artifacts exist")
        if self._had_state_artifacts:
            try:
                with open(self.head, encoding="utf-8") as fh:
                    checkpoint = parse_json_no_duplicate_keys(fh.read())
            except (OSError, ContractError) as exc:
                raise HistoryError("head checkpoint unreadable or malformed") from exc
            if not isinstance(checkpoint, dict):
                raise HistoryError("head checkpoint is not an object")
            seq, head_hash = self._head()
            if checkpoint.get("seq") != seq or checkpoint.get("head_hash") != head_hash:
                raise HistoryError("log does not match head checkpoint")
            try:
                with open(self.state, encoding="utf-8") as fh:
                    projection = parse_json_no_duplicate_keys(fh.read())
            except (OSError, ContractError) as exc:
                raise HistoryError("state projection unreadable or malformed") from exc
            if not isinstance(projection, dict) or projection != self._doc():
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
                    try:
                        rec = parse_json_no_duplicate_keys(line)
                    except ContractError:
                        return {"ok": False, "events": n, "reason": "malformed_record_line_%d" % lineno}
                    if not isinstance(rec, dict):
                        return {"ok": False, "events": n, "reason": "record_not_object_line_%d" % lineno}
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
        except (json.JSONDecodeError, ContractError, RecursionError):
            return {"ok": False, "events": n, "reason": "malformed_record"}
        if os.path.exists(self.head):
            with open(self.head, encoding="utf-8") as fh:
                try:
                    hd = parse_json_no_duplicate_keys(fh.read())
                except ContractError:
                    return {"ok": False, "events": n, "reason": "malformed_checkpoint"}
            if not isinstance(hd, dict):
                return {"ok": False, "events": n, "reason": "checkpoint_not_object"}
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
