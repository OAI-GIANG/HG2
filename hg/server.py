"""Single-process HTTP surface for the canonical phone-primary HG runtime."""
from __future__ import annotations

import hashlib
import hmac
import uuid
import json
import math
import os
import re
import socket
import threading
import unicodedata
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

try:
    import fcntl as _fcntl
except ImportError:  # The phone-primary production runtime requires an OS process lock.
    _fcntl = None

from .provenance import runtime_identity, runtime_manifest, validate_build
from .provenance_memory import effective_memory_trust
from .limits import FixedWindowRateLimiter

from .memory import MemoryConflict, MemoryDenied, MemoryErrorBase, MemoryIdempotencyConflict, MemoryStore, MemoryValidationError
from .model_gateway import ModelGatewayError, ModelNotConfigured
from .durable import DurableError
from .phone_runtime import PhoneRuntime
from .brain_orchestrator import BrainOrchestrator
from .capability_registry import RuntimeCapabilityRegistry, RuntimeDomainBinding
from .contracts import BRAIN_REQUEST_V1, CAPABILITY_RESULT_V1, canonical_digest
from .unified_harness import UnifiedHarness

MAX_BODY = 256 * 1024
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _json_no_duplicates(raw: bytes):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("duplicate_json_key")
            out[key] = value
        return out
    def bad_constant(_):
        raise ValueError("non_standard_json_constant")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=bad_constant)


def _scopes(name):
    return frozenset(s.strip() for s in os.environ.get(name, "").split(",") if s.strip() and s.strip() != "*")


def _bounded_int(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} is outside the allowed range")
    return value


def _bounded_float(name, default, minimum, maximum):
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name} must be numeric") from exc
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise RuntimeError(f"{name} is outside the allowed range")
    return value


def _credential_id(name):
    value = os.environ.get(name, "")
    if not ID_RE.fullmatch(value) or len(value) > 64:
        raise RuntimeError(f"{name} must be a valid non-empty credential ID")
    return value


def _credential_expiry(name):
    try:
        value = float(os.environ.get(name, ""))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name} must be a Unix timestamp") from exc
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError(f"{name} must be a positive Unix timestamp")
    return value


def _revoked_credential_ids():
    values = [item.strip() for item in os.environ.get("HG_API_REVOKED_TOKEN_IDS", "").split(",") if item.strip()]
    if any(not ID_RE.fullmatch(item) or len(item) > 64 for item in values):
        raise RuntimeError("HG_API_REVOKED_TOKEN_IDS contains an invalid credential ID")
    return frozenset(values)


class HGHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, runtime=None):
        # Validate credentials/configuration before taking the process lock so a
        # configuration error remains distinguishable from a duplicate runtime.
        self.read_token = os.environ.get("HG_API_READ_TOKEN", "")
        self.write_token = os.environ.get("HG_API_WRITE_TOKEN", "")
        if (not self.read_token or not self.write_token
                or hmac.compare_digest(self.read_token, self.write_token)):
            raise RuntimeError("HG_API_READ_TOKEN and HG_API_WRITE_TOKEN must be distinct non-empty credentials")
        self.read_token_id = _credential_id("HG_API_READ_TOKEN_ID")
        self.write_token_id = _credential_id("HG_API_WRITE_TOKEN_ID")
        if self.read_token_id == self.write_token_id:
            raise RuntimeError("HG_API_READ_TOKEN_ID and HG_API_WRITE_TOKEN_ID must be distinct")
        self.read_token_expires_at = _credential_expiry("HG_API_READ_TOKEN_EXPIRES_AT")
        self.write_token_expires_at = _credential_expiry("HG_API_WRITE_TOKEN_EXPIRES_AT")
        self.revoked_token_ids = _revoked_credential_ids()
        self.principal_id = os.environ.get("HG_API_PRINCIPAL_ID", "phone-owner")
        self.read_scopes = _scopes("HG_MEMORY_READ_SCOPES")
        self.write_scopes = _scopes("HG_MEMORY_WRITE_SCOPES")
        self.max_connections = _bounded_int("HG_MAX_CONNECTIONS", 32, 1, 256)
        self.request_timeout = _bounded_float("HG_REQUEST_TIMEOUT_SECONDS", 5.0, 0.1, 60.0)
        rate_limit = _bounded_int("HG_RATE_LIMIT_REQUESTS", 120, 1, 10000)
        rate_window = _bounded_float("HG_RATE_LIMIT_WINDOW_SECONDS", 60.0, 1.0, 3600.0)
        self.rate_limiter = FixedWindowRateLimiter(rate_limit, rate_window)
        # HG Unified Harness is the source-revision and execution-trace gate around
        # the existing Brain/registry path. Standard is fail-closed on invariants;
        # strict mode additionally blocks side effects without enforced timeouts.
        self.harness = UnifiedHarness(profile=os.environ.get("HG_HARNESS_PROFILE", "standard"))
        self._connection_slots = threading.BoundedSemaphore(self.max_connections)
        self._ask_lock = threading.RLock()
        self._ask_active = set()
        self._ask_response_cache = {}
        self.build_root = Path(__file__).resolve().parents[1]
        self.build_identity = runtime_identity(self.build_root, commit=os.environ.get("HG_BUILD_COMMIT", "UNDECLARED"))
        self._runtime_lock_file = None
        if _fcntl is None:
            raise RuntimeError("RUNTIME_PROCESS_LOCK_UNAVAILABLE")

        if runtime is not None:
            state_dir = runtime.store.dir
        else:
            state_dir = (os.environ.get("HG_STATE_DIR")
                         or os.path.join(os.getcwd(), "hg-state"))
        state_dir = os.path.realpath(state_dir)
        # A fresh install may not have created the runtime directory yet.
        # Create the directory before opening the lock, then initialize the
        # runtime only after the lock has been acquired.
        os.makedirs(state_dir, mode=0o700, exist_ok=True)
        lock_path = os.path.join(state_dir, ".hg2-http-runtime.lock")
        lock_file = open(lock_path, "a+", encoding="utf-8")
        try:
            os.chmod(lock_path, 0o600)
            _fcntl.flock(lock_file.fileno(), _fcntl.LOCK_EX | _fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lock_file.close()
            raise RuntimeError("RUNTIME_STATE_DIRECTORY_ALREADY_IN_USE") from exc
        except Exception:
            lock_file.close()
            raise

        self._runtime_lock_file = lock_file
        try:
            # In the production entrypoint, create PhoneRuntime only after the
            # process lock is held; startup recovery can therefore not race a
            # second API process before it starts serving.
            self.runtime = runtime if runtime is not None else PhoneRuntime(state_dir=state_dir)
            super().__init__(address, HGRequestHandler)
        except Exception:
            self._release_runtime_lock()
            raise

    def _release_runtime_lock(self):
        lock_file = self._runtime_lock_file
        self._runtime_lock_file = None
        if lock_file is not None:
            try:
                if _fcntl is not None:
                    _fcntl.flock(lock_file.fileno(), _fcntl.LOCK_UN)
            finally:
                lock_file.close()

    def server_close(self):
        try:
            super().server_close()
        finally:
            self._release_runtime_lock()

    def process_request(self, request, client_address):
        if not self._connection_slots.acquire(blocking=False):
            try:
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\nContent-Length: 0\r\nRetry-After: 1\r\n\r\n")
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._connection_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connection_slots.release()


class HGRequestHandler(BaseHTTPRequestHandler):
    server: HGHTTPServer
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(self.server.request_timeout)

    def handle_one_request(self):
        self._request_deadline = time.monotonic() + self.server.request_timeout
        try:
            return super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            # A disconnected or slow client must not produce an unhandled worker traceback.
            self.close_connection = True
        finally:
            self._request_deadline = None

    def parse_request(self):
        started = time.monotonic()
        try:
            parsed = super().parse_request()
        except (socket.timeout, TimeoutError, ConnectionResetError):
            self.close_connection = True
            return False
        # Some buffered readers may return a partial line/header after a socket timeout.
        # Require a complete request line and enforce a total header-parse deadline too.
        deadline = self._request_deadline
        if (not parsed or not getattr(self, "raw_requestline", b"").endswith(b"\n")
                or time.monotonic() - started >= self.server.request_timeout
                or (deadline is not None and time.monotonic() >= deadline)):
            self.close_connection = True
            return False
        allowed, retry_after = self.server.rate_limiter.allow(self.client_address[0])
        if not allowed:
            self._send(429, {"ok": False, "error": {"code": "RATE_LIMITED"}},
                       headers={"Retry-After": str(retry_after), "Connection": "close"})
            self.close_connection = True
            return False
        return True

    def log_message(self, fmt, *args):
        # Avoid logging memory content, bearer tokens, or request bodies.
        super().log_message("HG_API " + fmt, *args)

    def _send(self, status, obj, headers=None):
        body = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in (headers or {}).items():
            if name.lower() not in {"content-length", "transfer-encoding"}:
                self.send_header(name, str(value))
        self.end_headers()
        self.wfile.write(body)

    def _auth(self, write=False):
        hdr = self.headers.get("Authorization", "")
        supplied = hdr[7:] if hdr.startswith("Bearer ") else ""
        expected = self.server.write_token if write else self.server.read_token
        token_id = self.server.write_token_id if write else self.server.read_token_id
        expires_at = self.server.write_token_expires_at if write else self.server.read_token_expires_at
        if not supplied or not hmac.compare_digest(supplied, expected):
            self._send(401, {"ok": False, "error": {"code": "UNAUTHORIZED"}})
            return None
        if token_id in self.server.revoked_token_ids:
            self._send(401, {"ok": False, "error": {"code": "CREDENTIAL_REVOKED"}})
            return None
        if time.time() >= expires_at:
            self._send(401, {"ok": False, "error": {"code": "CREDENTIAL_EXPIRED"}})
            return None
        scopes = self.server.write_scopes if write else self.server.read_scopes
        if not scopes:
            self._send(403, {"ok": False, "error": {"code": "SCOPE_NOT_CONFIGURED"}})
            return None
        return scopes

    def _body(self):
        raw_len = self.headers.get("Content-Length", "0")
        if not raw_len.isdigit():
            raise ValueError("invalid_content_length")
        n = int(raw_len)
        if n > MAX_BODY:
            raise OverflowError("body_too_large")
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("transfer_encoding_not_supported")
        chunks = []
        remaining_bytes = n
        try:
            while remaining_bytes:
                deadline = self._request_deadline
                remaining_time = (deadline - time.monotonic()) if deadline is not None else self.server.request_timeout
                if remaining_time <= 0:
                    raise TimeoutError("request_deadline_exceeded")
                self.connection.settimeout(remaining_time)
                chunk = self.rfile.read1(min(remaining_bytes, 65536))
                if not chunk:
                    raise ValueError("incomplete_request_body")
                chunks.append(chunk)
                remaining_bytes -= len(chunk)
        finally:
            self.connection.settimeout(self.server.request_timeout)
        value = _json_no_duplicates(b"".join(chunks))
        if not isinstance(value, dict):
            raise ValueError("json_object_required")
        return value

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ("/", "/ui/index.html"):
            page = Path(__file__).resolve().parent.parent / "ui" / "index.html"
            try:
                body = page.read_bytes()
            except OSError:
                self._send(503, {"ok": False, "error": {"code": "UI_UNAVAILABLE"}})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/health":
            health = self.server.runtime.health()
            integ = health.get("integrity", {})
            try:
                current_manifest = runtime_manifest(self.server.build_root)
                provenance_ok = hmac.compare_digest(current_manifest["manifest_sha256"],
                                                    self.server.build_identity["source_manifest_sha256"])
            except (OSError, RuntimeError, ValueError):
                current_manifest = {"manifest_sha256": "UNAVAILABLE", "files": []}
                provenance_ok = False
            ok = bool(health.get("ok") and integ.get("ok") and provenance_ok)
            self._send(200 if ok else 503,
                       {"ok": ok, "product": "HG", "runtime": "READY" if ok else "DEGRADED",
                        "integrity": integ, "provenance": {"ok": provenance_ok,
                        "startup_manifest_sha256": self.server.build_identity["source_manifest_sha256"],
                        "current_manifest_sha256": current_manifest["manifest_sha256"],
                        "file_count": len(current_manifest["files"])},
                        "model_gateway": self.server.runtime.model_gateway.status(),
                        "edge_configured": health.get("edge_configured", False),
                        "durable": self.server.runtime.durable.status(), "build": self.server.build_identity})
            return
        if path == "/api/durable/status":
            grants = self._auth(write=False)
            if grants is None: return
            self._send(200, {"ok": True, "durable": self.server.runtime.durable.status()})
            return
        if path in ("/api/memory/search", "/api/memory/context"):
            grants = self._auth(write=False)
            if grants is None: return
            params = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
            if any(len(v) != 1 for v in params.values()) or set(params) - {"q", "limit", "max_chars"}:
                self._send(400, {"ok": False, "error": {"code": "INVALID_QUERY_PARAMETERS"}}); return
            query = params.get("q", [""])[0]
            try:
                limit = int(params.get("limit", ["10"])[0])
                if path.endswith("/context"):
                    max_chars = int(params.get("max_chars", ["12000"])[0])
                    result = self.server.runtime.memory.build_context(query, grants=grants, limit=limit, max_chars=max_chars)
                    self._send(200, {"ok": True, **result})
                else:
                    result = self.server.runtime.memory.retrieve(query, grants=grants, limit=limit)
                    self._send(200, {"ok": True, **result})
            except ValueError:
                self._send(400, {"ok": False, "error": {"code": "INVALID_QUERY_PARAMETERS"}})
            except MemoryErrorBase as exc:
                self._send(422, {"ok": False, "error": {"code": exc.code}})
            return
        if path == "/api/library":
            grants = self._auth(write=False)
            if grants is None: return
            if not grants.intersection({"global", "HG"}):
                self._send(403, {"ok": False, "error": {"code": "LIBRARY_SCOPE_DENIED"}})
                return
            root = Path(self.server.runtime.store.dir).resolve()
            items = []
            quarantined = 0
            try:
                for event in self.server.runtime.store.replay():
                    typ, payload = event.get("event_type"), event.get("payload", {})
                    if typ == "legacy.library.quarantined":
                        quarantined += 1
                        continue
                    if typ != "legacy.library.asset.imported":
                        continue
                    rel = payload.get("relative_blob")
                    digest = payload.get("sha256")
                    if not isinstance(rel, str) or not re.fullmatch(r"library/[0-9a-f]{64}", rel):
                        raise ValueError("invalid_library_reference")
                    if not isinstance(digest, str) or rel != "library/" + digest:
                        raise ValueError("library_hash_reference_mismatch")
                    candidate = (root / rel).resolve(strict=True)
                    if candidate.parent != (root / "library").resolve() or not candidate.is_file():
                        raise ValueError("library_path_escape")
                    h = hashlib.sha256()
                    with candidate.open("rb") as asset:
                        for chunk in iter(lambda: asset.read(1024 * 1024), b""):
                            h.update(chunk)
                    if not hmac.compare_digest(h.hexdigest(), digest):
                        raise ValueError("library_hash_mismatch")
                    items.append({"id": payload.get("legacy_id"), "name": payload.get("name"),
                                  "sha256": digest, "size": candidate.stat().st_size,
                                  "integrity": "VERIFIED"})
            except (OSError, ValueError, RuntimeError):
                self._send(503, {"ok": False, "error": {"code": "LIBRARY_INTEGRITY_FAILED"}})
                return
            self._send(200, {"ok": True, "count": len(items), "quarantined_count": quarantined,
                             "assets": items, "source": "LOCAL_HASH_VERIFIED_BLOBS"})
            return
        if path == "/api/memory":
            grants = self._auth(write=False)
            if grants is None: return
            try:
                rows = self.server.runtime.memory.list_active(grants=grants, limit=100)
                self._send(200, {"ok": True, "count": len(rows), "memory": rows})
            except MemoryErrorBase as exc:
                self._send(400, {"ok": False, "error": {"code": exc.code}})
            return
        match = re.fullmatch(r"/api/memory/([^/]+)", path)
        if match:
            grants = self._auth(write=False)
            if grants is None: return
            try:
                rec = self.server.runtime.memory.get(match.group(1), grants=grants)
                self._send(200 if rec else 404, {"ok": bool(rec), "memory": rec})
            except MemoryErrorBase as exc:
                self._send(403 if isinstance(exc, MemoryDenied) else 400, {"ok": False, "error": {"code": exc.code}})
            return
        self._send(404, {"ok": False, "error": {"code": "NOT_FOUND"}})

    def _verify_memory_evidence(self, reference, *, context_value, query, grants, request_id):
        """Independently resolve a memory-context receipt against the current event-sourced state."""
        prefix = "evidence:sha256:"
        if not isinstance(reference, str) or not reference.startswith(prefix):
            return False
        claimed_digest = reference[len(prefix):]
        if not re.fullmatch(r"[0-9a-f]{64}", claimed_digest):
            return False
        if not isinstance(context_value, dict) or not isinstance(context_value.get("manifest"), dict):
            return False
        manifest = context_value["manifest"]
        if canonical_digest(manifest) != claimed_digest:
            return False
        internal_manifest_digest = manifest.get("manifest_sha256")
        if (not isinstance(internal_manifest_digest, str)
                or canonical_digest({k: v for k, v in manifest.items() if k != "manifest_sha256"})
                != internal_manifest_digest):
            return False
        if (manifest.get("operation") != "memory_context"
                or manifest.get("model_called") is not False
                or manifest.get("query_sha256") != hashlib.sha256(query.encode("utf-8")).hexdigest()
                or manifest.get("max_chars") != 12000
                or context_value.get("query_id") != manifest.get("query_id")):
            return False

        try:
            audit = self.server.runtime.store.audit_export()
            if not audit.get("verify", {}).get("ok"):
                return False
            events = self.server.runtime.store.replay()
            source_head = manifest.get("source_head_hash")
            source_events = [event for event in events if event.get("record_hash") == source_head]
            if len(source_events) != 1:
                return False
            source_event = source_events[0]
            source_payload = source_event.get("payload")
            if (source_event.get("event_type") != "brain.step.started"
                    or not isinstance(source_payload, dict)
                    or source_payload.get("request_id") != request_id
                    or source_payload.get("domain_id") != "memory_knowledge"):
                return False
            expected_query_id = canonical_digest({"query": query, "state_head": source_head})
            if manifest.get("query_id") != expected_query_id:
                return False

            # Re-read authorized records from the canonical event log, re-check per-record
            # checksums/ACLs, and recompute lexical selection independently of the worker output.
            visible = self.server.runtime.memory.list_active(grants=grants, limit=500)
            stop_words = {
                "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
                "for", "from", "how", "i", "in", "is", "it", "me", "of", "on", "or",
                "please", "tell", "that", "the", "this", "to", "was", "what", "when",
                "where", "which", "who", "why", "with", "you", "your", "one", "s",
            }

            def normalized_terms(value):
                folded = unicodedata.normalize("NFC", unicodedata.normalize("NFC", value).casefold())
                return {term for term in re.findall(r"[^\W_]+", folded, flags=re.UNICODE)
                        if term not in stop_words}

            terms = normalized_terms(query)
            if not terms:
                return False
            provenance_records = [record["provenance_metadata"] for record in visible
                                  if isinstance(record.get("provenance_metadata"), dict)]
            conflict_keys = set()
            if provenance_records:
                from .provenance_memory import detect_memory_conflicts
                conflict_keys = {(item["source_ref"], item["memory_key"])
                                 for item in detect_memory_conflicts(provenance_records)}
            matches = []
            for record in visible:
                freshness_status = "FRESHNESS_UNKNOWN"
                provenance = record.get("provenance_metadata")
                if isinstance(provenance, dict):
                    from .provenance_memory import memory_freshness
                    freshness = memory_freshness(provenance)
                    freshness_status = freshness["status"]
                    if not freshness["usable"]:
                        continue
                searchable = [str(record.get("title", "")), str(record.get("content", ""))]
                aliases = record.get("aliases", [])
                if isinstance(aliases, list):
                    searchable.extend(item for item in aliases if isinstance(item, str))
                text = unicodedata.normalize("NFC", " ".join(searchable))
                words = normalized_terms(text)
                overlap = terms & words
                if not overlap:
                    continue
                score = len(overlap) / len(terms)
                if score <= 0.5:
                    continue
                conflict_key = (
                    provenance.get("source_ref"), provenance.get("memory_key")
                ) if isinstance(provenance, dict) else None
                conflict_status = "CONFLICT_UNRESOLVED" if conflict_key in conflict_keys else "NO_KNOWN_CONFLICT"
                matches.append({**record, "score": round(score, 6),
                                "freshness_status": freshness_status,
                                "memory_conflict_status": conflict_status})
            matches.sort(key=lambda item: (-item["score"], item["id"]))
            matches = matches[:10]
            expected_selected = [
                {"id": item["id"], "version": item["version"], "scope_id": item["scope_id"],
                 "checksum": item["checksum"], "score": item["score"]}
                for item in matches
            ]
            if (manifest.get("visible_record_count") != len(visible)
                    or manifest.get("match_count") != len(matches)
                    or manifest.get("selected") != expected_selected):
                return False

            expected_blocks = []
            used = 0
            for record in matches:
                provenance = record.get("provenance_metadata")
                block = {
                    "source_id": record["id"],
                    "version": record["version"],
                    "scope_id": record["scope_id"],
                    "checksum": record["checksum"],
                    "title": record["title"],
                    "content": record["content"],
                    "freshness_status": record.get("freshness_status", "FRESHNESS_UNKNOWN"),
                    "trust_status": (
                        effective_memory_trust(provenance)
                        if isinstance(provenance, dict) else "UNVERIFIED"
                    ),
                    "memory_conflict_status": record.get("memory_conflict_status", "NO_KNOWN_CONFLICT"),
                    "content_is_untrusted_data": True,
                }
                size = len(block["title"]) + len(block["content"])
                if used + size > 12000:
                    remaining = 12000 - used
                    if remaining <= 0:
                        break
                    block["content"] = block["content"][:remaining]
                    block["truncated"] = True
                    expected_blocks.append(block)
                    used += remaining
                    break
                block["truncated"] = False
                expected_blocks.append(block)
                used += size

            if (manifest.get("context_record_ids") != [block["source_id"] for block in expected_blocks]
                    or manifest.get("context_char_count") != used
                    or canonical_digest(context_value.get("context")) != canonical_digest(expected_blocks)):
                return False
            return True
        except Exception:
            # Any malformed, unavailable or inconsistent source is a verification failure.
            return False

    def _handle_ask(self):
        grants = self._auth(write=False)
        if grants is None:
            return

        active_key = None
        request_id = None
        correlation_id = None
        operation_digest = None
        supplied_idempotency = False
        try:
            body = self._body()
            query = body.get("query")
            if not isinstance(query, str) or not query.strip() or len(query) > 12000:
                raise MemoryValidationError("query must contain 1..12000 characters")

            header_key = self.headers.get("Idempotency-Key")
            body_key = body.get("idempotency_key")
            if header_key is not None and body_key is not None and header_key != body_key:
                self._send(400, {"ok": False, "error": {"code": "IDEMPOTENCY_KEY_MISMATCH"}})
                return
            client_key = header_key if header_key is not None else body_key
            supplied_idempotency = client_key is not None
            if client_key is None:
                self._send(400, {"ok": False, "error": {"code": "IDEMPOTENCY_KEY_REQUIRED"}})
                return
            if not isinstance(client_key, str) or not ID_RE.fullmatch(client_key):
                self._send(400, {"ok": False, "error": {"code": "IDEMPOTENCY_KEY_INVALID"}})
                return

            if not self.server.runtime.model_gateway.status().get("configured"):
                raise ModelNotConfigured("model gateway configuration missing")

            principal_id = self.server.principal_id
            operation_digest = hashlib.sha256(
                ("HG2.ask.v1\0" + principal_id + "\0" + client_key).encode("utf-8")
            ).hexdigest()
            request_id = "ask-" + operation_digest[:32]
            correlation_id = "corr-" + operation_digest[:32]
            input_digest = canonical_digest({
                "schema_version": "HG_ASK_INPUT_V1",
                "principal_id": principal_id,
                "query": query,
            })
            query_digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
            source_revision = self.server.build_identity.get("source_manifest_sha256", "")
            request = {
                "schema_version": BRAIN_REQUEST_V1,
                "request_id": request_id,
                "correlation_id": correlation_id,
                "goal": query,
                "constraints": {
                    "required_capabilities": ["memory.search", "synthesis.propose"],
                    "max_branches": 2,
                    "max_steps": 2,
                    "deadline_seconds": 50.0,
                    "conflict_policy": "INDEPENDENT_OUTPUTS",
                },
                "source_revision": source_revision,
            }
            accepted_event_id = "brain-request-accepted:" + operation_digest
            with self.server._ask_lock:
                events = self.server.runtime.store.replay()
                by_event_id = {e.get("event_id"): e for e in events}
                accepted = by_event_id.get(accepted_event_id)
                if accepted is not None:
                    accepted_payload = accepted.get("payload")
                    if (not isinstance(accepted_payload, dict)
                            or accepted_payload.get("input_sha256") != input_digest
                            or accepted_payload.get("principal_id") != principal_id
                            or accepted_payload.get("source_manifest_sha256") != source_revision):
                        self._send(409, {"ok": False, "error": {
                            "code": ("IDEMPOTENCY_SOURCE_REVISION_CONFLICT"
                                     if isinstance(accepted_payload, dict)
                                     and accepted_payload.get("input_sha256") == input_digest
                                     and accepted_payload.get("principal_id") == principal_id
                                     and accepted_payload.get("source_manifest_sha256") != source_revision
                                     else "IDEMPOTENCY_KEY_CONFLICT"),
                            "request_id": request_id,
                        }})
                        return

                    cached = self.server._ask_response_cache.get(operation_digest)
                    if operation_digest in self.server._ask_active:
                        self._send(409, {"ok": False, "error": {
                            "code": "IDEMPOTENCY_REQUEST_IN_PROGRESS",
                            "request_id": request_id,
                        }})
                        return
                    if cached is not None:
                        if cached.get("input_sha256") != input_digest:
                            self._send(409, {"ok": False, "error": {"code": "IDEMPOTENCY_KEY_CONFLICT"}})
                            return
                        response = dict(cached["response"])
                        response["idempotency"] = {
                            "key_sha256": operation_digest,
                            "key_supplied": supplied_idempotency,
                            "replayed": True,
                        }
                        self._send(200, response)
                        return

                    completed = any(
                        e.get("event_type") in {"model.call.completed", "brain.request.finished"}
                        and isinstance(e.get("payload"), dict)
                        and e["payload"].get("brain_request_id", e["payload"].get("request_id")) == request_id
                        for e in events
                    )
                    doubtful = any(
                        e.get("event_type") in {"model.call.in_doubt", "brain.request.in_doubt"}
                        and isinstance(e.get("payload"), dict)
                        and e["payload"].get("brain_request_id", e["payload"].get("request_id")) == request_id
                        for e in events
                    )
                    start_event = next((e for e in events
                        if e.get("event_type") == "model.call.started"
                        and isinstance(e.get("payload"), dict)
                        and e["payload"].get("brain_request_id") == request_id), None)
                    if completed:
                        self._send(409, {"ok": False, "error": {
                            "code": "IDEMPOTENCY_OUTCOME_FINAL_RESPONSE_NOT_CACHED",
                            "request_id": request_id,
                        }})
                        return
                    if doubtful:
                        self._send(409, {"ok": False, "error": {
                            "code": "MODEL_CALL_OUTCOME_IN_DOUBT",
                            "request_id": request_id,
                        }})
                        return
                    if start_event is not None:
                        # A start receipt proves the provider may have accepted the call.
                        # Do not call it again based only on a timeout/retry.
                        try:
                            self.server.runtime.mark_model_call_in_doubt(start_event)
                        except Exception:
                            self._send(503, {"ok": False, "error": {
                                "code": "IN_DOUBT_RECEIPT_WRITE_FAILED",
                                "request_id": request_id,
                            }})
                            return
                        self._send(409, {"ok": False, "error": {
                            "code": "MODEL_CALL_OUTCOME_IN_DOUBT",
                            "request_id": request_id,
                        }})
                        return
                else:
                    accepted_payload = {
                        "schema_version": "HG_BRAIN_REQUEST_AUDIT_V1",
                        "request_id": request_id,
                        "correlation_id": correlation_id,
                        "input_sha256": input_digest,
                        "query_sha256": query_digest,
                        "source_manifest_sha256": source_revision,
                        "operation_key_sha256": operation_digest,
                        "principal_id": principal_id,
                    }
                    try:
                        self.server.runtime.store.emit(
                            "brain.request.accepted", accepted_payload,
                            correlation_id=correlation_id,
                            event_id=accepted_event_id,
                        )
                    except Exception:
                        self._send(503, {"ok": False, "error": {
                            "code": "BRAIN_REQUEST_ACCEPTANCE_PERSIST_FAILED",
                            "request_id": request_id,
                        }})
                        return
                self.server._ask_active.add(operation_digest)
                active_key = operation_digest

            payloads = {}

            def capability_result(ctx, *, status, digest, error_code=None, evidence_refs=None):
                return {
                    "schema_version": CAPABILITY_RESULT_V1,
                    "request_id": ctx["request_id"],
                    "correlation_id": ctx["correlation_id"],
                    "status": status,
                    "output_digest": digest,
                    "error_code": error_code,
                    "evidence_refs": [] if evidence_refs is None else evidence_refs,
                    "source_revision": ctx["source_revision"],
                }

            def step_event(ctx, event_type, *, status=None, digest=None, error_code=None):
                payload = {
                    "request_id": ctx["request_id"],
                    "correlation_id": ctx["correlation_id"],
                    "attempt_id": ctx["attempt_id"],
                    "plan_digest": ctx.get("plan_digest"),
                    "domain_id": ctx["branch_id"],
                    "required_capabilities": ctx["required_capabilities"],
                }
                if status is not None:
                    payload["status"] = status
                if digest is not None:
                    payload["output_digest"] = digest
                if error_code is not None:
                    payload["error_code"] = error_code
                stage = event_type.rsplit(".", 1)[-1]
                event_id = ("brain-step-" + stage + ":" + ctx["request_id"] + ":"
                            + ctx["attempt_id"] + ":" + ctx["branch_id"])
                return self.server.runtime.store.emit(
                    event_type, payload,
                    correlation_id=ctx["correlation_id"],
                    event_id=event_id,
                )

            def memory_worker(ctx):
                step_event(ctx, "brain.step.started")
                context_value = self.server.runtime.memory.build_context(
                    query, grants=grants, limit=10, max_chars=12000)
                digest = canonical_digest(context_value["manifest"])
                payloads["context"] = context_value
                step_event(ctx, "brain.step.completed", status="SUCCESS", digest=digest)
                return capability_result(
                    ctx, status="SUCCESS", digest=digest,
                    evidence_refs=["evidence:sha256:" + digest],
                )

            def synthesis_worker(ctx):
                context_value = payloads.get("context")
                if not isinstance(context_value, dict):
                    step_event(ctx, "brain.step.blocked", status="BLOCKED",
                               error_code="AUTHORIZED_MEMORY_CONTEXT_UNAVAILABLE")
                    return capability_result(
                        ctx, status="BLOCKED", digest=None,
                        error_code="AUTHORIZED_MEMORY_CONTEXT_UNAVAILABLE",
                    )
                step_event(ctx, "brain.step.started")
                audit_start = {
                    "operation": "model_answer",
                    "query_sha256": query_digest,
                    "context_manifest_sha256": context_value["manifest"].get("manifest_sha256"),
                    "brain_plan_digest": ctx.get("plan_digest"),
                    "brain_request_id": ctx["request_id"],
                    "correlation_id": ctx["correlation_id"],
                    "operation_key_sha256": operation_digest,
                }
                try:
                    self.server.runtime.store.emit(
                        "model.call.started", audit_start,
                        correlation_id=correlation_id,
                        event_id="model-call-start:" + ctx["request_id"],
                    )
                except Exception:
                    step_event(ctx, "brain.step.blocked", status="BLOCKED",
                               error_code="PRECALL_AUDIT_WRITE_FAILED")
                    return capability_result(
                        ctx, status="BLOCKED", digest=None,
                        error_code="PRECALL_AUDIT_WRITE_FAILED",
                    )
                try:
                    result_value = self.server.runtime.model_gateway.ask(query, context_value)
                except Exception:
                    # The call may have reached the provider. Persist uncertainty and never
                    # encode exception text, credentials or the raw prompt in audit.
                    try:
                        self.server.runtime.mark_model_call_in_doubt({
                            "event_type": "model.call.started",
                            "event_id": "model-call-start:" + ctx["request_id"],
                            "correlation_id": correlation_id,
                            "payload": audit_start,
                        })
                    except Exception:
                        pass  # The orphan start receipt is recovered as IN_DOUBT at startup.
                    raise

                manifest = result_value["manifest"]
                digest = canonical_digest(manifest)
                audit = {
                    "operation": "model_answer",
                    "model": result_value.get("model"),
                    "query_sha256": manifest.get("query_sha256"),
                    "context_manifest_sha256": manifest.get("context_manifest_sha256"),
                    "request_sha256": manifest.get("request_sha256"),
                    "response_sha256": manifest.get("response_sha256"),
                    "manifest_sha256": manifest.get("manifest_sha256"),
                    "brain_status": "PARTIAL",
                    "brain_plan_digest": ctx.get("plan_digest"),
                    "brain_request_id": ctx["request_id"],
                    "operation_key_sha256": operation_digest,
                }
                # Event identity is per logical request, not per provider response digest:
                # two distinct requests can legitimately produce identical output bytes.
                self.server.runtime.store.emit(
                    "model.call.completed", audit,
                    correlation_id=correlation_id,
                    causation_id="model-call-start:" + ctx["request_id"],
                    event_id="model-call-completed:" + ctx["request_id"],
                )
                payloads["result"] = result_value
                payloads["model_digest"] = digest
                step_event(ctx, "brain.step.completed", status="RESPONSE_ONLY", digest=digest,
                           error_code="PROVIDER_RESPONSE_ONLY_NOT_EXECUTION_PROOF")
                return capability_result(
                    ctx, status="RESPONSE_ONLY", digest=digest,
                    error_code="PROVIDER_RESPONSE_ONLY_NOT_EXECUTION_PROOF",
                )

            # The static ownership map is only the maximum allowed set. Actual route
            # availability comes from concrete adapters registered for this request.
            # Neither provider configuration nor a registered test status implies that
            # an adapter has been verified as operational in a deployed phone runtime.
            registry = RuntimeCapabilityRegistry()
            registry.register(RuntimeDomainBinding(
                domain_id="memory_knowledge",
                capability_ids=("memory.search",),
                implementation_id="hg.memory.MemoryStore.build_context",
                adapter_version="1",
                input_contract="HG_BRAIN_WORKER_CONTEXT_V1",
                output_contract=CAPABILITY_RESULT_V1,
                authority_contract="authenticated_api_read_scope_and_memory_acl",
                side_effect_class="LOCAL_READ_ONLY",
                declared_timeout_seconds=5.0,
                hard_timeout_enforced=False,
                max_invocations_per_request=1,
                lifecycle_state="TESTED",
                source_revision=source_revision,
                evidence_verifier_id="memory-context-source-integrity-v1",
                adapter=memory_worker,
                readiness_check=lambda: callable(
                    getattr(self.server.runtime.memory, "build_context", None)
                ),
            ))
            registry.register(RuntimeDomainBinding(
                domain_id="research_synthesis",
                capability_ids=("synthesis.propose",),
                implementation_id="hg.model_gateway.ModelGateway.ask",
                adapter_version="1",
                input_contract="HG_BRAIN_WORKER_CONTEXT_V1",
                output_contract=CAPABILITY_RESULT_V1,
                authority_contract="authenticated_api_read_and_configured_provider",
                side_effect_class="OUTBOUND_PROVIDER_CALL",
                declared_timeout_seconds=45.0,
                hard_timeout_enforced=False,
                max_invocations_per_request=1,
                lifecycle_state="TESTED",
                source_revision=source_revision,
                evidence_verifier_id="response-only-no-semantic-verifier",
                adapter=synthesis_worker,
                readiness_check=lambda: (
                    self.server.runtime.model_gateway.status().get("configured") is True
                ),
            ))
            resolved_registry = registry.resolve()
            workers = resolved_registry["workers"]
            inventory = resolved_registry["available_capabilities"]
            registry_snapshot = resolved_registry["snapshot"]
            registry_digest = registry_snapshot["registry_digest"]
            brain = BrainOrchestrator()
            plan = brain.plan(request, available_capabilities=inventory, workers=workers)
            self.server.runtime.store.emit(
                "brain.request.planned", {
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    "input_sha256": input_digest,
                    "source_manifest_sha256": source_revision,
                    "plan_digest": plan.get("plan_digest"),
                    "status": plan.get("status"),
                    "domains": [x.get("branch_id") for x in plan.get("branches", [])],
                    "capability_gaps": plan.get("capability_gaps", []),
                    "registry_schema_version": registry_snapshot["schema_version"],
                    "registry_digest": registry_digest,
                    "registry_entries": registry_snapshot["entries"],
                    "registry_source_revision_set_sha256": registry_snapshot["source_revision_set_sha256"],
                },
                correlation_id=correlation_id,
                event_id="brain-request-planned:" + request_id,
            )
            harness_gate = None
            if plan.get("status") == "ROUTABLE":
                harness_gate = self.server.harness.before_dispatch(
                    plan=plan,
                    registry_snapshot=registry_snapshot,
                    source_revision=source_revision,
                )
                try:
                    self.server.runtime.store.emit(
                        "brain.request.harness.gated", {
                            "schema_version": "HG_UNIFIED_HARNESS_V1",
                            "request_id": request_id,
                            "correlation_id": correlation_id,
                            "input_sha256": input_digest,
                            "plan_digest": plan.get("plan_digest"),
                            "registry_digest": registry_digest,
                            "profile": harness_gate["profile"],
                            "ok": harness_gate["ok"],
                            "reason_code": harness_gate["reason_code"],
                            "receipt_digest": harness_gate["receipt_digest"],
                            "checks": harness_gate["checks"],
                            "warnings": harness_gate["warnings"],
                        },
                        correlation_id=correlation_id,
                        event_id="brain-request-harness-gated:" + request_id,
                    )
                except Exception:
                    self._send(503, {"ok": False, "error": {
                        "code": "HARNESS_PRE_DISPATCH_RECEIPT_WRITE_FAILED",
                        "request_id": request_id,
                    }})
                    return
                if not harness_gate["ok"]:
                    try:
                        self.server.runtime.store.emit(
                            "brain.request.blocked", {
                                "request_id": request_id,
                                "correlation_id": correlation_id,
                                "plan_digest": plan.get("plan_digest"),
                                "status": "BLOCKED_HARNESS_GATE",
                                "error_code": harness_gate["reason_code"],
                                "harness_gate_digest": harness_gate["receipt_digest"],
                            },
                            correlation_id=correlation_id,
                            event_id="brain-request-harness-blocked:" + request_id,
                        )
                    except Exception:
                        self._send(503, {"ok": False, "error": {
                            "code": "HARNESS_BLOCKED_RECEIPT_WRITE_FAILED",
                            "request_id": request_id,
                        }})
                        return
                    self._send(503, {
                        "ok": False,
                        "error": {"code": harness_gate["reason_code"], "request_id": request_id},
                        "brain": {"status": "BLOCKED_HARNESS_GATE", "plan_digest": plan.get("plan_digest")},
                        "harness_gate": harness_gate,
                    })
                    return

            self.server.runtime.store.emit(
                "brain.request.started", {
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    "input_sha256": input_digest,
                    "plan_digest": plan.get("plan_digest"),
                },
                correlation_id=correlation_id,
                event_id="brain-request-started:" + request_id,
            )
            # Attempts are distinct durable records. If the process stops before the
            # provider start receipt, a safe retry can use a new attempt instead of
            # trying to overwrite a previous step event whose memory snapshot changed.
            attempt_id = "attempt-" + uuid.uuid4().hex
            self.server.runtime.store.emit(
                "brain.request.attempt.started", {
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    "attempt_id": attempt_id,
                    "plan_digest": plan.get("plan_digest"),
                },
                correlation_id=correlation_id,
                causation_id="brain-request-started:" + request_id,
                event_id="brain-request-attempt-started:" + request_id + ":" + attempt_id,
            )
            routed_workers = {}
            def bind_attempt(worker):
                def invoke(ctx):
                    return worker({**ctx, "attempt_id": attempt_id})
                return invoke
            routed_workers = {name: bind_attempt(worker) for name, worker in workers.items()}
            brain_result = brain.execute(
                request, available_capabilities=inventory, workers=routed_workers,
                evidence_verifier=lambda ref: self._verify_memory_evidence(
                    ref, context_value=payloads.get("context"), query=query,
                    grants=grants, request_id=request_id,
                ),
            )
            outcome_gate = self.server.harness.verify_outcome(
                plan=plan, result=brain_result, source_revision=source_revision,
            )
            if (not outcome_gate["ok"]
                    or brain_result["status"] not in {"PARTIAL", "SUCCESS"}
                    or "result" not in payloads):
                if not outcome_gate["ok"]:
                    status = "BLOCKED_HARNESS_OUTPUT_GATE"
                    event_type = "brain.request.blocked"
                    code = outcome_gate["reason_code"]
                else:
                    status = brain_result.get("status")
                    event_type = "brain.request.in_doubt" if status == "IN_DOUBT" else "brain.request.blocked"
                    code = ("BRAIN_ORCHESTRATION_" + str(status))
                try:
                    self.server.runtime.store.emit(
                        event_type, {
                            "request_id": request_id,
                            "brain_request_id": request_id,
                            "correlation_id": correlation_id,
                            "plan_digest": brain_result.get("plan_digest", plan.get("plan_digest")),
                            "status": status,
                            "error_code": code,
                            "harness_gate_digest": (outcome_gate.get("receipt_digest")
                                                    if not outcome_gate.get("ok") else None),
                            "harness_profile": self.server.harness.profile,
                        },
                        correlation_id=correlation_id,
                        event_id=event_type.replace(".", "-") + ":" + request_id,
                    )
                except Exception:
                    pass  # Any durable provider start without a terminal state is recovered IN_DOUBT.
                self._send(503, {
                    "ok": False,
                    "error": {"code": code, "request_id": request_id},
                    "brain": brain_result,
                    "unified_harness": {
                        "profile": self.server.harness.profile,
                        "pre_dispatch": harness_gate,
                        "quality_gate": outcome_gate,
                    },
                })
                return

            context = payloads["context"]
            result = payloads["result"]
            manifest = result["manifest"]
            terminal_payload = {
                "request_id": request_id,
                "brain_request_id": request_id,
                "correlation_id": correlation_id,
                "input_sha256": input_digest,
                "plan_digest": brain_result.get("plan_digest"),
                "status": brain_result["status"],
                "model_manifest_sha256": manifest.get("manifest_sha256"),
                "harness_profile": self.server.harness.profile,
                "harness_pre_dispatch_digest": (
                    harness_gate.get("receipt_digest") if isinstance(harness_gate, dict) else None
                ),
                "harness_quality_gate_digest": outcome_gate.get("receipt_digest"),
            }
            self.server.runtime.store.emit(
                "brain.request.finished", terminal_payload,
                correlation_id=correlation_id,
                causation_id="model-call-completed:" + request_id,
                event_id="brain-request-finished:" + request_id,
            )
            response = {
                "ok": True,
                "answer": result["answer"],
                "model": result["model"],
                "context_manifest": context["manifest"],
                "model_manifest": manifest,
                "brain": {
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    "source_revision": source_revision,
                    "status": brain_result["status"],
                    "plan_digest": brain_result.get("plan_digest"),
                    "invoked_branches": brain_result.get("invoked_branches", []),
                    "branch_results": brain_result.get("branch_results", []),
                },
                "idempotency": {
                    "key_sha256": operation_digest,
                    "key_supplied": supplied_idempotency,
                    "replayed": False,
                },
                "unified_harness": {
                    "profile": self.server.harness.profile,
                    "pre_dispatch": harness_gate,
                    "quality_gate": outcome_gate,
                },
                "capability_registry": {
                    "schema_version": registry_snapshot["schema_version"],
                    "registry_digest": registry_digest,
                    "active_capabilities": sorted(
                        capability_id
                        for values in inventory.values()
                        for capability_id in values
                    ),
                },
            }
            with self.server._ask_lock:
                self.server._ask_response_cache[operation_digest] = {
                    "input_sha256": input_digest,
                    "response": response,
                }
                while len(self.server._ask_response_cache) > 32:
                    self.server._ask_response_cache.pop(next(iter(self.server._ask_response_cache)))
            self._send(200, response)
        except TimeoutError:
            self.close_connection = True
            self._send(408, {"ok": False, "error": {"code": "REQUEST_TIMEOUT", "request_id": request_id}},
                       headers={"Connection": "close"})
        except OverflowError:
            self._send(413, {"ok": False, "error": {"code": "BODY_TOO_LARGE"}})
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self._send(400, {"ok": False, "error": {"code": "INVALID_JSON_OR_REQUEST",
                                                   "request_id": request_id}})
        except MemoryDenied as exc:
            self._send(403, {"ok": False, "error": {"code": exc.code, "request_id": request_id}})
        except MemoryErrorBase as exc:
            self._send(422, {"ok": False, "error": {"code": exc.code, "request_id": request_id}})
        except ModelNotConfigured as exc:
            self._send(503, {"ok": False, "error": {"code": exc.code, "request_id": request_id}})
        except ModelGatewayError as exc:
            self._send(502, {"ok": False, "error": {"code": exc.code, "request_id": request_id}})
        except Exception:
            # Do not leak details from an internal exception/provider payload over the API.
            self._send(503, {"ok": False, "error": {
                "code": "BRAIN_REQUEST_PROCESSING_FAILED",
                "request_id": request_id,
            }})
        finally:
            if active_key is not None:
                with self.server._ask_lock:
                    self.server._ask_active.discard(active_key)

    def do_POST(self):
        path = urlsplit(self.path).path
        if path == "/api/durable/sync":
            grants = self._auth(write=True)
            if grants is None: return
            try:
                body = self._body()
                result = self.server.runtime.durable.deliver_once(limit=body.get("limit", 25))
                self._send(200, {"ok": True, "result": result})
            except TimeoutError:
                self.close_connection = True
                self._send(408, {"ok": False, "error": {"code": "REQUEST_TIMEOUT"}}, headers={"Connection": "close"})
            except OverflowError:
                self._send(413, {"ok": False, "error": {"code": "BODY_TOO_LARGE"}})
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                self._send(400, {"ok": False, "error": {"code": "INVALID_JSON"}})
            except DurableError as exc:
                self._send(503, {"ok": False, "error": {"code": exc.code}})
            return
        if path == "/api/ask":
            self._handle_ask()
            return
        if path != "/api/memory":
            self._send(404, {"ok": False, "error": {"code": "NOT_FOUND"}}); return
        grants = self._auth(write=True)
        if grants is None: return
        try:
            body = self._body()
            record = body.get("record")
            if not isinstance(record, dict): raise MemoryValidationError("record object required")
            result = self.server.runtime.memory.remember(
                record, principal_id=self.server.principal_id, grants=grants,
                idempotency_key=body.get("idempotency_key", ""),
                expected_version=body.get("expected_version"),
                correlation_id=body.get("correlation_id"))
            self._send(200 if result.get("version", 1) > 1 else 201, {"ok": True, "memory": result})
        except TimeoutError:
            self.close_connection = True
            self._send(408, {"ok": False, "error": {"code": "REQUEST_TIMEOUT"}}, headers={"Connection": "close"})
        except OverflowError:
            self._send(413, {"ok": False, "error": {"code": "BODY_TOO_LARGE"}})
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self._send(400, {"ok": False, "error": {"code": "INVALID_JSON"}})
        except MemoryDenied as exc:
            self._send(403, {"ok": False, "error": {"code": exc.code}})
        except MemoryConflict as exc:
            self._send(409, {"ok": False, "error": {"code": exc.code}})
        except MemoryIdempotencyConflict as exc:
            self._send(409, {"ok": False, "error": {"code": exc.code}})
        except MemoryErrorBase as exc:
            self._send(422, {"ok": False, "error": {"code": exc.code}})

    def do_DELETE(self):
        match = re.fullmatch(r"/api/memory/([^/]+)", urlsplit(self.path).path)
        if not match or not ID_RE.fullmatch(match.group(1)):
            self._send(404, {"ok": False, "error": {"code": "NOT_FOUND"}}); return
        grants = self._auth(write=True)
        if grants is None: return
        try:
            body = self._body()
            result = self.server.runtime.memory.delete(
                match.group(1), principal_id=self.server.principal_id, grants=grants,
                expected_version=body.get("expected_version"), idempotency_key=body.get("idempotency_key", ""),
                correlation_id=body.get("correlation_id"))
            self._send(200, {"ok": True, "memory": result})
        except TimeoutError:
            self.close_connection = True
            self._send(408, {"ok": False, "error": {"code": "REQUEST_TIMEOUT"}}, headers={"Connection": "close"})
        except OverflowError:
            self._send(413, {"ok": False, "error": {"code": "BODY_TOO_LARGE"}})
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self._send(400, {"ok": False, "error": {"code": "INVALID_JSON"}})
        except MemoryDenied as exc:
            self._send(403, {"ok": False, "error": {"code": exc.code}})
        except MemoryConflict as exc:
            self._send(409, {"ok": False, "error": {"code": exc.code}})
        except MemoryIdempotencyConflict as exc:
            self._send(409, {"ok": False, "error": {"code": exc.code}})
        except MemoryErrorBase as exc:
            self._send(422, {"ok": False, "error": {"code": exc.code}})


def main():
    build_check = validate_build(Path(__file__).resolve().parents[1])
    host = os.environ.get("HG_BIND", "127.0.0.1")
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise RuntimeError("HG phone API must bind to loopback; expose it only through the authenticated HTTPS edge")
    port = int(os.environ.get("HG_PORT", "8787"))
    server = HGHTTPServer((host, port))
    print(json.dumps({"event": "HG_API_STARTED", "product": "HG", "host": host, "port": port,
                      "runtime_id": server.runtime.store.runtime_id, "build": build_check}, sort_keys=True), flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
