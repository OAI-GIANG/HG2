"""Authenticated, append-only SQLite replica for the HG2 durable batch contract.

Backup/relay only. No memory query/mutation API. Keep this process bound to
loopback and expose it only behind an authenticated HTTPS edge.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .history import SCHEMA, PRODUCT_ID, canonical, digest

CONTRACT = "HG2_DURABLE_BATCH_V1"
MEMORY_SCHEMA = "HG_MEMORY_V1"
MEMORY_EVENTS = {"memory.mutated", "memory.tombstoned"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
MAX_BODY = 2 * 1024 * 1024
MAX_BATCH = 100


class ReplicaError(Exception):
    def __init__(self, code: str, status: int = 422):
        super().__init__(code)
        self.code = code
        self.status = status


def _event_batch_id(event: dict) -> str:
    return hashlib.sha256(canonical({
        "event_id": event["event_id"],
        "record_hash": event["record_hash"],
    }).encode("utf-8")).hexdigest()


def _validate_entry(entry: object, allowed_scopes: frozenset[str]) -> tuple[dict, str]:
    if not isinstance(entry, dict) or set(entry) != {"batch_id", "event"}:
        raise ReplicaError("INVALID_BATCH_ENTRY", 400)
    event = entry["event"]
    if not isinstance(event, dict):
        raise ReplicaError("INVALID_EVENT", 400)
    required = {"seq", "event_id", "event_type", "recorded_at", "correlation_id",
                "causation_id", "product_id", "runtime_id", "schema", "payload",
                "prev_hash", "record_hash"}
    if set(event) != required:
        raise ReplicaError("INVALID_EVENT_SCHEMA", 400)
    if event.get("schema") != SCHEMA or event.get("product_id") != PRODUCT_ID:
        raise ReplicaError("UNSUPPORTED_EVENT_SCHEMA", 422)
    if event.get("event_type") not in MEMORY_EVENTS:
        raise ReplicaError("UNSUPPORTED_EVENT_TYPE", 422)
    if not isinstance(event.get("seq"), int) or isinstance(event.get("seq"), bool) or event["seq"] < 1:
        raise ReplicaError("INVALID_EVENT_SEQUENCE", 400)
    if not isinstance(event.get("runtime_id"), str) or not 1 <= len(event["runtime_id"]) <= 128:
        raise ReplicaError("INVALID_RUNTIME_ID", 400)
    if not isinstance(event.get("event_id"), str) or not ID_RE.fullmatch(event["event_id"]):
        raise ReplicaError("INVALID_EVENT_ID", 400)
    if not isinstance(event.get("record_hash"), str) or not HEX64.fullmatch(event["record_hash"]):
        raise ReplicaError("INVALID_RECORD_HASH", 400)
    if not isinstance(event.get("prev_hash"), str) or not HEX64.fullmatch(event["prev_hash"]):
        raise ReplicaError("INVALID_PREVIOUS_HASH", 400)
    if not isinstance(event.get("recorded_at"), (int, float)) or isinstance(event.get("recorded_at"), bool):
        raise ReplicaError("INVALID_RECORDED_AT", 400)
    if not isinstance(event.get("correlation_id"), str) or not event["correlation_id"]:
        raise ReplicaError("INVALID_CORRELATION_ID", 400)
    if event.get("causation_id") is not None and not isinstance(event.get("causation_id"), str):
        raise ReplicaError("INVALID_CAUSATION_ID", 400)
    core = {k: v for k, v in event.items() if k != "record_hash"}
    if digest(core) != event["record_hash"]:
        raise ReplicaError("EVENT_HASH_MISMATCH", 422)
    payload = event.get("payload")
    if not isinstance(payload, dict) or not isinstance(payload.get("record"), dict):
        raise ReplicaError("INVALID_MEMORY_PAYLOAD", 400)
    record = payload["record"]
    if not isinstance(record.get("id"), str) or not ID_RE.fullmatch(record["id"]):
        raise ReplicaError("INVALID_MEMORY_ID", 400)
    scope_id = record.get("scope_id")
    if not isinstance(scope_id, str) or not scope_id or scope_id not in allowed_scopes:
        raise ReplicaError("MEMORY_SCOPE_DENIED", 403)
    status = record.get("status")
    expected_status = "active" if event["event_type"] == "memory.mutated" else "tombstoned"
    if status != expected_status:
        raise ReplicaError("TOMBSTONE_CONTRACT_MISMATCH", 422)
    checksum = record.get("checksum")
    if not isinstance(checksum, str) or not HEX64.fullmatch(checksum):
        raise ReplicaError("INVALID_MEMORY_CHECKSUM", 400)
    rec_core = {k: v for k, v in record.items() if k != "checksum"}
    if digest(rec_core) != checksum:
        raise ReplicaError("MEMORY_CHECKSUM_MISMATCH", 422)
    if entry["batch_id"] != _event_batch_id(event):
        raise ReplicaError("EVENT_BATCH_ID_MISMATCH", 422)
    return event, scope_id


class ReplicaStore:
    """SQLite receiver with atomic, idempotent batch ingestion."""

    def __init__(self, database_path: str, allowed_scopes):
        scopes = frozenset(s for s in allowed_scopes if isinstance(s, str) and s and s != "*")
        if not scopes:
            raise RuntimeError("HG_REPLICA_ALLOWED_SCOPES must be explicit and non-empty")
        self.database_path = database_path
        parent = os.path.dirname(os.path.abspath(database_path))
        os.makedirs(parent, mode=0o700, exist_ok=True)
        if os.path.islink(database_path):
            raise RuntimeError("HG replica database must not be a symlink")
        if os.stat(parent).st_mode & 0o077:
            raise RuntimeError("HG replica database directory must be private (mode 0700)")
        self.allowed_scopes = scopes
        self._lock = threading.RLock()
        self._db = sqlite3.connect(database_path, timeout=10, isolation_level=None, check_same_thread=False)
        if database_path != ":memory:":
            os.chmod(database_path, 0o600)
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("PRAGMA busy_timeout=10000")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS replica_events (
                source_runtime_id TEXT NOT NULL,
                source_event_id TEXT NOT NULL,
                source_seq INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                scope_id TEXT NOT NULL,
                record_hash TEXT NOT NULL,
                event_json TEXT NOT NULL,
                accepted_at REAL NOT NULL,
                PRIMARY KEY (source_runtime_id, source_event_id)
            );
            CREATE INDEX IF NOT EXISTS replica_events_scope
                ON replica_events(scope_id, source_runtime_id, source_seq);
            CREATE TABLE IF NOT EXISTS batch_receipts (
                batch_id TEXT PRIMARY KEY,
                request_sha256 TEXT NOT NULL,
                accepted_count INTEGER NOT NULL,
                receipt_json TEXT NOT NULL,
                created_at REAL NOT NULL
            );
        """)

    def close(self):
        with self._lock:
            self._db.close()

    def capabilities(self):
        return {"contract": CONTRACT, "memory_schema": MEMORY_SCHEMA,
                "supports_tombstones": True, "supports_scopes": True,
                "required_scope": "MEMORY_PERSIST", "replica_only": True}

    def ingest(self, body: object, idempotency_key: str) -> dict:
        if not isinstance(body, dict) or set(body) != {"contract", "batch_id", "events"}:
            raise ReplicaError("INVALID_BATCH", 400)
        if body.get("contract") != CONTRACT:
            raise ReplicaError("CONTRACT_MISMATCH", 422)
        items = body.get("events")
        batch_id = body.get("batch_id")
        if not isinstance(items, list) or not 1 <= len(items) <= MAX_BATCH:
            raise ReplicaError("INVALID_BATCH_SIZE", 400)
        if not isinstance(batch_id, str) or not HEX64.fullmatch(batch_id) or idempotency_key != batch_id:
            raise ReplicaError("IDEMPOTENCY_KEY_MISMATCH", 400)
        item_ids = [x.get("batch_id") if isinstance(x, dict) else None for x in items]
        expected_batch_id = hashlib.sha256(canonical(item_ids).encode("utf-8")).hexdigest()
        if expected_batch_id != batch_id:
            raise ReplicaError("BATCH_ID_MISMATCH", 422)
        normalized = [_validate_entry(entry, self.allowed_scopes) for entry in items]
        # Duplicate IDs inside one batch are ambiguous and are not accepted.
        pairs = [(e["runtime_id"], e["event_id"]) for e, _ in normalized]
        if len(set(pairs)) != len(pairs):
            raise ReplicaError("DUPLICATE_EVENT_IN_BATCH", 400)
        request_hash = hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()
        with self._lock:
            cur = self._db.cursor()
            try:
                cur.execute("BEGIN IMMEDIATE")
                prior = cur.execute(
                    "SELECT request_sha256, receipt_json FROM batch_receipts WHERE batch_id=?",
                    (batch_id,),
                ).fetchone()
                if prior:
                    if prior[0] != request_hash:
                        raise ReplicaError("IDEMPOTENCY_CONFLICT", 409)
                    receipt = json.loads(prior[1])
                    cur.execute("COMMIT")
                    return receipt
                for event, _scope in normalized:
                    prior_event = cur.execute(
                        "SELECT record_hash FROM replica_events WHERE source_runtime_id=? AND source_event_id=?",
                        (event["runtime_id"], event["event_id"]),
                    ).fetchone()
                    if prior_event and prior_event[0] != event["record_hash"]:
                        raise ReplicaError("EVENT_ID_CONFLICT", 409)
                accepted_at = time.time()
                for event, scope_id in normalized:
                    cur.execute(
                        """INSERT OR IGNORE INTO replica_events
                           (source_runtime_id, source_event_id, source_seq, event_type, scope_id,
                            record_hash, event_json, accepted_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (event["runtime_id"], event["event_id"], event["seq"], event["event_type"],
                         scope_id, event["record_hash"], canonical(event), accepted_at),
                    )
                receipt = {"ok": True, "contract": CONTRACT, "batch_id": batch_id,
                           "accepted_count": len(items), "replica_only": True}
                cur.execute(
                    "INSERT INTO batch_receipts(batch_id, request_sha256, accepted_count, receipt_json, created_at) VALUES (?, ?, ?, ?, ?)",
                    (batch_id, request_hash, len(items), canonical(receipt), accepted_at),
                )
                cur.execute("COMMIT")
                return receipt
            except Exception:
                if self._db.in_transaction:
                    cur.execute("ROLLBACK")
                raise
            finally:
                cur.close()

    def status(self):
        with self._lock:
            events = self._db.execute("SELECT COUNT(*) FROM replica_events").fetchone()[0]
            batches = self._db.execute("SELECT COUNT(*) FROM batch_receipts").fetchone()[0]
            scopes = sorted(r[0] for r in self._db.execute("SELECT DISTINCT scope_id FROM replica_events"))
            return {"ok": True, "role": "BACKUP_REPLICA_ONLY", "event_count": events,
                    "batch_count": batches, "scopes": scopes}


class ReplicaHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, store: ReplicaStore, token: str):
        if address[0] not in ("127.0.0.1", "::1", "localhost"):
            raise RuntimeError("HG replica must bind to loopback and use an authenticated HTTPS edge")
        if not token or len(token) < 32:
            raise RuntimeError("HG_REPLICA_TOKEN must be provisioned and at least 32 characters")
        self.store = store
        self.token = token
        super().__init__(address, ReplicaRequestHandler)


class ReplicaRequestHandler(BaseHTTPRequestHandler):
    server: ReplicaHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    def _send(self, status: int, value: dict):
        raw = canonical(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def _authorized(self):
        header = self.headers.get("Authorization", "")
        supplied = header[7:] if header.startswith("Bearer ") else ""
        if not supplied or not hmac.compare_digest(supplied, self.server.token):
            self._send(401, {"ok": False, "error": {"code": "UNAUTHORIZED"}})
            return False
        return True

    def _body(self):
        length = self.headers.get("Content-Length", "0")
        if not length.isdigit():
            raise ReplicaError("INVALID_CONTENT_LENGTH", 400)
        size = int(length)
        if size > MAX_BODY:
            raise ReplicaError("BODY_TOO_LARGE", 413)
        if self.headers.get("Transfer-Encoding"):
            raise ReplicaError("TRANSFER_ENCODING_UNSUPPORTED", 400)
        raw = self.rfile.read(size)
        def unique_pairs(pairs):
            obj = {}
            for key, value in pairs:
                if key in obj:
                    raise ReplicaError("DUPLICATE_JSON_KEY", 400)
                obj[key] = value
            return obj
        try:
            parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs,
                                parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid constant")))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            raise ReplicaError("INVALID_JSON", 400) from None
        if not isinstance(parsed, dict):
            raise ReplicaError("JSON_OBJECT_REQUIRED", 400)
        return parsed

    def do_GET(self):
        if urlsplit(self.path).path != "/backend/hg2/capabilities":
            self._send(404, {"ok": False, "error": {"code": "NOT_FOUND"}})
            return
        if not self._authorized():
            return
        self._send(200, self.server.store.capabilities())

    def do_POST(self):
        if urlsplit(self.path).path != "/backend/hg2/memory/batch":
            self._send(404, {"ok": False, "error": {"code": "NOT_FOUND"}})
            return
        if not self._authorized():
            return
        try:
            receipt = self.server.store.ingest(self._body(), self.headers.get("Idempotency-Key", ""))
            self._send(200, receipt)
        except ReplicaError as exc:
            self._send(exc.status, {"ok": False, "error": {"code": exc.code}})
        except sqlite3.Error:
            self._send(503, {"ok": False, "error": {"code": "REPLICA_STORAGE_UNAVAILABLE"}})


def main():
    host = os.environ.get("HG_REPLICA_BIND", "127.0.0.1")
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise RuntimeError("HG replica must bind to loopback and use an authenticated HTTPS edge")
    port = int(os.environ.get("HG_REPLICA_PORT", "8890"))
    database = os.environ.get("HG_REPLICA_DB", os.path.join(os.getcwd(), "hg-replica.sqlite3"))
    token = os.environ.get("HG_REPLICA_TOKEN", "")
    scopes = [s.strip() for s in os.environ.get("HG_REPLICA_ALLOWED_SCOPES", "").split(",") if s.strip()]
    store = ReplicaStore(database, scopes)
    server = ReplicaHTTPServer((host, port), store, token)
    print(canonical({"event": "HG_REPLICA_STARTED", "role": "BACKUP_REPLICA_ONLY",
                     "host": host, "port": port, "database": os.path.abspath(database)}), flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        store.close()


if __name__ == "__main__":
    main()
