"""Append-only, hash-chained HG state and history. Fail-closed on any integrity failure."""
from __future__ import annotations

import hashlib, json, os, threading, time, uuid
from contextlib import contextmanager

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


@contextmanager
def _exclusive_file_lock(path):
    """Cross-process exclusive lock for one state directory's writer."""
    fh = open(path, "a+", encoding="utf-8")
    lock_kind = None
    try:
        try:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            lock_kind = ("fcntl", fcntl)
        except ImportError:
            try:
                import msvcrt
            except ImportError as exc:
                raise HistoryError("exclusive writer locking unavailable on this platform") from exc
            fh.seek(0, os.SEEK_END)
            if fh.tell() == 0:
                fh.write("0")
                fh.flush()
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            lock_kind = ("msvcrt", msvcrt)
        yield
    finally:
        if lock_kind:
            kind, module = lock_kind
            try:
                if kind == "fcntl":
                    module.flock(fh.fileno(), module.LOCK_UN)
                else:
                    fh.seek(0)
                    module.locking(fh.fileno(), module.LK_UNLCK, 1)
            finally:
                fh.close()
        else:
            fh.close()


def _fsync_directory(directory):
    """Persist directory-entry changes or fail closed if unsupported."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(directory, flags)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise HistoryError("directory fsync unavailable or failed: %s" % directory) from exc


def _atomic_write(path, content):
    """Atomically replace a UTF-8 file after syncing contents and directory entry."""
    directory = os.path.dirname(path) or "."
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        _fsync_directory(directory)
    except Exception:
        # Cleanup is best-effort; it must not mask the persistence failure.
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise


class StateStore:
    def __init__(self, directory, *, clock=time.time):
        self.dir = str(directory)
        os.makedirs(self.dir, exist_ok=True)
        self.log = os.path.join(self.dir, "history.jsonl")
        self.head = os.path.join(self.dir, "head.json")
        self.state = os.path.join(self.dir, "state.json")
        self._clock = clock
        self._lock = threading.RLock()
        self._poisoned = False
        self._events = []
        self._by_id = {}
        self._sessions = {}
        self._counters = {}
        # Loading must share the writer lock: otherwise another process can
        # observe the append between log fsync and checkpoint replacement.
        with _exclusive_file_lock(os.path.join(self.dir, ".writer.lock")):
            self._preexisting = {"log": os.path.exists(self.log), "head": os.path.exists(self.head),
                                 "state": os.path.exists(self.state),
                                 "runtime_id": os.path.exists(os.path.join(self.dir, "runtime_id"))}
            self.runtime_id = self._runtime_id()
            self._load()
        if not self._events:
            self.emit(GENESIS_EVENT, {"product_id": PRODUCT_ID, "schema": SCHEMA}, correlation_id="genesis")

    def _runtime_id(self):
        p = os.path.join(self.dir, "runtime_id")
        if self._preexisting["runtime_id"]:
            try:
                with open(p, encoding="utf-8") as fh:
                    value = fh.read().strip()
            except OSError as exc:
                raise HistoryError("runtime identity unreadable") from exc
            if not value:
                raise HistoryError("runtime identity empty")
            return value
        # A runtime identity may only be minted for a genuinely new store.
        # Never replace a missing identity when any durable state remains.
        if any(self._preexisting[name] for name in ("log", "head", "state")):
            raise HistoryError("runtime identity missing while state artifacts exist")
        value = uuid.uuid4().hex
        try:
            with open(p, "x", encoding="utf-8") as fh:
                fh.write(value + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            _fsync_directory(self.dir)
        except (OSError, HistoryError) as exc:
            raise HistoryError("runtime identity could not be initialized durably") from exc
        return value

    def _head(self):
        return (0, ZERO) if not self._events else (self._events[-1]["seq"], self._events[-1]["record_hash"])

    def _refresh_from_disk(self):
        """Reload a current, verified snapshot while holding the writer lock."""
        had_events = bool(self._events)
        self._preexisting = {"log": os.path.exists(self.log), "head": os.path.exists(self.head),
                             "state": os.path.exists(self.state),
                             "runtime_id": os.path.exists(os.path.join(self.dir, "runtime_id"))}
        if had_events and not any(self._preexisting.values()):
            raise HistoryError("all durable state artifacts disappeared")
        self.runtime_id = self._runtime_id()
        self._events = []
        self._by_id = {}
        self._sessions = {}
        self._counters = {}
        self._load()

    def _load(self):
        have_log = self._preexisting["log"]
        have_head = self._preexisting["head"]
        have_state = self._preexisting["state"]
        have_rid = self._preexisting["runtime_id"]
        if not have_log:
            if have_head or have_state or have_rid:
                raise HistoryError("history log missing while other state artifacts exist")
            return
        missing = [name for name, present in (("head checkpoint", have_head),
                                               ("state projection", have_state),
                                               ("runtime identity", have_rid)) if not present]
        if missing:
            raise HistoryError("required state artifact missing: " + ", ".join(missing))
        prev, seq, seen = ZERO, 0, set()
        try:
            with open(self.log, encoding="utf-8") as fh:
                for line_no, line in enumerate(fh, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise HistoryError("malformed record line %d" % line_no) from exc
                    if not isinstance(rec, dict):
                        raise HistoryError("record is not an object line %d" % line_no)
                    required = {"seq", "event_id", "event_type", "recorded_at", "correlation_id",
                                "causation_id", "product_id", "runtime_id", "schema", "payload",
                                "prev_hash", "record_hash"}
                    if not required.issubset(rec):
                        raise HistoryError("record fields missing line %d" % line_no)
                    if isinstance(rec["seq"], bool) or not isinstance(rec["seq"], int) or rec["seq"] != seq + 1:
                        raise HistoryError("sequence gap line %d" % line_no)
                    if not isinstance(rec["event_id"], str) or not rec["event_id"] or rec["event_id"] in seen:
                        raise HistoryError("invalid or duplicate event_id line %d" % line_no)
                    if not isinstance(rec["event_type"], str) or not rec["event_type"]:
                        raise HistoryError("invalid event_type line %d" % line_no)
                    if not isinstance(rec["payload"], dict):
                        raise HistoryError("invalid payload line %d" % line_no)
                    if rec["product_id"] != PRODUCT_ID or rec["schema"] != SCHEMA:
                        raise HistoryError("identity/schema mismatch line %d" % line_no)
                    if rec["runtime_id"] != self.runtime_id:
                        raise HistoryError("runtime identity mismatch line %d" % line_no)
                    if rec["prev_hash"] != prev:
                        raise HistoryError("chain break line %d" % line_no)
                    core = {key: value for key, value in rec.items() if key != "record_hash"}
                    if not isinstance(rec["record_hash"], str) or digest(core) != rec["record_hash"]:
                        raise HistoryError("record hash mismatch line %d" % line_no)
                    if seq == 0 and (rec["event_type"] != GENESIS_EVENT or
                                     rec["payload"].get("product_id") != PRODUCT_ID or
                                     rec["payload"].get("schema") != SCHEMA):
                        raise HistoryError("invalid genesis record")
                    seen.add(rec["event_id"])
                    prev, seq = rec["record_hash"], rec["seq"]
                    self._events.append(rec)
                    self._by_id[rec["event_id"]] = rec
                    self._apply(rec)
        except OSError as exc:
            raise HistoryError("history log unreadable") from exc
        if not self._events:
            raise HistoryError("history log empty while durable state artifacts exist")
        self._checkpoint_check()
        self._projection_check()

    def _checkpoint_check(self):
        try:
            with open(self.head, encoding="utf-8") as fh:
                hd = json.loads(fh.read())
        except (OSError, json.JSONDecodeError) as exc:
            raise HistoryError("head checkpoint unreadable") from exc
        s, h = self._head()
        if not isinstance(hd, dict) or hd.get("seq") != s or hd.get("head_hash") != h:
            raise HistoryError("log does not match head checkpoint")

    def _projection_check(self):
        try:
            with open(self.state, encoding="utf-8") as fh:
                doc = json.loads(fh.read())
        except (OSError, json.JSONDecodeError) as exc:
            raise HistoryError("state projection unreadable") from exc
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
        _atomic_write(self.state, canonical(self._doc()))

    def _write_head(self):
        s, h = self._head()
        _atomic_write(self.head, canonical({"seq": s, "head_hash": h}))

    def emit(self, event_type, payload, *, correlation_id=None, causation_id=None, event_id=None):
        # Validate caller input before touching the append-only log. Writing an
        # invalid event would make the store fail closed on its next reopen.
        if not isinstance(event_type, str) or not event_type:
            raise HistoryError("event type must be a non-empty string")
        if not isinstance(payload, dict):
            raise HistoryError("event payload must be an object")
        if event_id is not None and (not isinstance(event_id, str) or not event_id):
            raise HistoryError("event_id must be a non-empty string when provided")
        with self._lock:
            if self._poisoned:
                raise HistoryError("state store is poisoned after a persistence failure; reopen only after investigation")
            lock_path = os.path.join(self.dir, ".writer.lock")
            with _exclusive_file_lock(lock_path):
                # A second process/object may have advanced the log. Refresh while
                # exclusively locked so sequence/hash decisions never use stale memory.
                if self._events or os.path.exists(self.log):
                    self._refresh_from_disk()
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
                try:
                    with open(self.log, "a", encoding="utf-8") as fh:
                        fh.write(canonical(rec) + "\n")
                        fh.flush()
                        os.fsync(fh.fileno())
                    self._events.append(rec)
                    self._by_id[rec["event_id"]] = rec
                    self._apply(rec)
                    self._write_state()
                    self._write_head()
                except Exception:
                    # Never allow a later emit to silently heal a partially
                    # committed append/projection/checkpoint sequence.
                    self._poisoned = True
                    raise
                return rec

    def verify(self):
        """Verify all durable artifacts and the replay-derived state, without repairing anything."""
        log_exists = os.path.exists(self.log)
        head_exists = os.path.exists(self.head)
        state_exists = os.path.exists(self.state)
        rid_path = os.path.join(self.dir, "runtime_id")
        rid_exists = os.path.exists(rid_path)
        if not log_exists:
            if head_exists or state_exists or rid_exists:
                return {"ok": False, "events": 0, "reason": "log_missing_while_state_present"}
            return {"ok": True, "events": 0, "reason": "empty_store"}
        if not head_exists:
            return {"ok": False, "events": 0, "reason": "checkpoint_missing"}
        if not state_exists:
            return {"ok": False, "events": 0, "reason": "state_projection_missing"}
        if not rid_exists:
            return {"ok": False, "events": 0, "reason": "runtime_identity_missing"}
        try:
            with open(rid_path, encoding="utf-8") as fh:
                stored_runtime_id = fh.read().strip()
            if not stored_runtime_id or stored_runtime_id != self.runtime_id:
                return {"ok": False, "events": 0, "reason": "runtime_identity_mismatch"}
            prev, seq, seen, count = ZERO, 0, set(), 0
            sessions, counters = {}, {}
            with open(self.log, encoding="utf-8") as fh:
                for line_no, line in enumerate(fh, 1):
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    if not isinstance(rec, dict):
                        return {"ok": False, "events": count, "reason": "record_not_object_line_%d" % line_no}
                    required = {"seq", "event_id", "event_type", "recorded_at", "correlation_id",
                                "causation_id", "product_id", "runtime_id", "schema", "payload",
                                "prev_hash", "record_hash"}
                    if not required.issubset(rec):
                        return {"ok": False, "events": count, "reason": "record_fields_missing_line_%d" % line_no}
                    if isinstance(rec["seq"], bool) or not isinstance(rec["seq"], int) or rec["seq"] != seq + 1:
                        return {"ok": False, "events": count, "reason": "sequence_gap_line_%d" % line_no}
                    if not isinstance(rec["event_id"], str) or not rec["event_id"] or rec["event_id"] in seen:
                        return {"ok": False, "events": count, "reason": "duplicate_or_invalid_event_id_line_%d" % line_no}
                    if not isinstance(rec["event_type"], str) or not rec["event_type"]:
                        return {"ok": False, "events": count, "reason": "invalid_event_type_line_%d" % line_no}
                    if not isinstance(rec["payload"], dict):
                        return {"ok": False, "events": count, "reason": "invalid_payload_line_%d" % line_no}
                    if rec["product_id"] != PRODUCT_ID or rec["schema"] != SCHEMA:
                        return {"ok": False, "events": count, "reason": "identity_schema_mismatch_line_%d" % line_no}
                    if rec["runtime_id"] != stored_runtime_id:
                        return {"ok": False, "events": count, "reason": "runtime_identity_mismatch_line_%d" % line_no}
                    if rec["prev_hash"] != prev:
                        return {"ok": False, "events": count, "reason": "chain_break_line_%d" % line_no}
                    core = {key: value for key, value in rec.items() if key != "record_hash"}
                    if not isinstance(rec["record_hash"], str) or digest(core) != rec["record_hash"]:
                        return {"ok": False, "events": count, "reason": "record_hash_mismatch_line_%d" % line_no}
                    if seq == 0 and (rec["event_type"] != GENESIS_EVENT or
                                     rec["payload"].get("product_id") != PRODUCT_ID or
                                     rec["payload"].get("schema") != SCHEMA):
                        return {"ok": False, "events": count, "reason": "invalid_genesis"}
                    seen.add(rec["event_id"])
                    prev, seq, count = rec["record_hash"], rec["seq"], count + 1
                    if rec["event_type"] == "session.created" and "session_id" in rec["payload"]:
                        sessions[rec["payload"]["session_id"]] = dict(rec["payload"])
                    counters[rec["event_type"]] = counters.get(rec["event_type"], 0) + 1
            if count == 0:
                return {"ok": False, "events": 0, "reason": "history_log_empty"}
            try:
                with open(self.head, encoding="utf-8") as fh:
                    checkpoint = json.load(fh)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                return {"ok": False, "events": count, "reason": "checkpoint_unreadable"}
            if not isinstance(checkpoint, dict) or checkpoint.get("seq") != seq or checkpoint.get("head_hash") != prev:
                return {"ok": False, "events": count, "reason": "checkpoint_mismatch"}
            try:
                with open(self.state, encoding="utf-8") as fh:
                    projection = json.load(fh)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                return {"ok": False, "events": count, "reason": "state_projection_unreadable"}
            expected = {"schema": SCHEMA, "product_id": PRODUCT_ID, "runtime_id": stored_runtime_id,
                        "last_seq": seq, "head_hash": prev, "sessions": sessions, "counters": counters}
            if projection != expected:
                return {"ok": False, "events": count, "reason": "state_projection_mismatch"}
            return {"ok": True, "events": count, "head_hash": prev, "reason": "chain_and_artifacts_ok"}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, KeyError, AttributeError):
            return {"ok": False, "events": 0, "reason": "artifact_unreadable_or_malformed"}

    def replay(self):
        return [dict(e) for e in self._events]

    def audit_export(self):
        s, h = self._head()
        return {"schema": SCHEMA, "product_id": PRODUCT_ID, "runtime_id": self.runtime_id,
                "events": len(self._events), "last_seq": s, "head_hash": h, "verify": self.verify(),
                "state": self._doc()}
