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
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .provenance import runtime_identity, runtime_manifest, validate_build
from .limits import FixedWindowRateLimiter

from .memory import MemoryConflict, MemoryDenied, MemoryErrorBase, MemoryIdempotencyConflict, MemoryStore, MemoryValidationError
from .model_gateway import ModelGatewayError, ModelNotConfigured
from .durable import DurableError
from .phone_runtime import PhoneRuntime
from .brain_orchestrator import BrainOrchestrator, BRANCH_CAPABILITIES
from .contracts import BRAIN_REQUEST_V1, CAPABILITY_RESULT_V1, canonical_digest

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
        self.runtime = runtime or PhoneRuntime()
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
        self._connection_slots = threading.BoundedSemaphore(self.max_connections)
        self.build_root = Path(__file__).resolve().parents[1]
        self.build_identity = runtime_identity(self.build_root, commit=os.environ.get("HG_BUILD_COMMIT", "UNDECLARED"))
        super().__init__(address, HGRequestHandler)

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
            grants = self._auth(write=False)
            if grants is None: return
            try:
                body = self._body()
                query = body.get("query")
                if not isinstance(query, str) or not query.strip() or len(query) > 12000:
                    raise MemoryValidationError("query must contain 1..12000 characters")
                if not self.server.runtime.model_gateway.status().get("configured"):
                    raise ModelNotConfigured("model gateway configuration missing")
                request_id = "ask-" + uuid.uuid4().hex
                correlation_id = "corr-" + uuid.uuid4().hex
                source_revision = self.server.build_identity.get("source_manifest_sha256", "")
                request = {"schema_version": BRAIN_REQUEST_V1, "request_id": request_id,
                           "correlation_id": correlation_id, "goal": query,
                           "constraints": {"required_capabilities": ["memory.search", "synthesis.propose"],
                                           "max_branches": 2, "max_steps": 2, "deadline_seconds": 50.0,
                                           "conflict_policy": "INDEPENDENT_OUTPUTS"},
                           "source_revision": source_revision}
                payloads = {}
                evidence = {}
                def capability_result(ctx, *, status, digest, error_code=None, evidence_refs=None):
                    return {"schema_version": CAPABILITY_RESULT_V1,
                            "request_id": ctx["request_id"], "correlation_id": ctx["correlation_id"],
                            "status": status, "output_digest": digest, "error_code": error_code,
                            "evidence_refs": [] if evidence_refs is None else evidence_refs,
                            "source_revision": ctx["source_revision"]}
                def memory_worker(ctx):
                    context_value = self.server.runtime.memory.build_context(
                        query, grants=grants, limit=10, max_chars=12000)
                    digest = canonical_digest(context_value["manifest"])
                    evidence[digest] = context_value["manifest"]
                    payloads["context"] = context_value
                    return capability_result(ctx, status="SUCCESS", digest=digest,
                                             evidence_refs=["evidence:sha256:" + digest])
                def synthesis_worker(ctx):
                    context_value = payloads.get("context")
                    if not isinstance(context_value, dict):
                        return capability_result(ctx, status="BLOCKED", digest=None,
                                                 error_code="AUTHORIZED_MEMORY_CONTEXT_UNAVAILABLE")
                    audit_start = {
                        "operation": "model_answer",
                        "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
                        "context_manifest_sha256": context_value["manifest"].get("manifest_sha256"),
                        "brain_plan_digest": ctx.get("plan_digest"),
                        "brain_request_id": ctx["request_id"],
                    }
                    try:
                        self.server.runtime.store.emit(
                            "model.call.started", audit_start,
                            correlation_id=correlation_id,
                            event_id="model-call-start:" + ctx["request_id"],
                        )
                    except Exception:
                        # Fail closed: do not contact the provider without a durable start record.
                        return capability_result(ctx, status="BLOCKED", digest=None,
                                                 error_code="PRECALL_AUDIT_WRITE_FAILED")
                    result_value = self.server.runtime.model_gateway.ask(query, context_value)
                    digest = canonical_digest(result_value["manifest"])
                    payloads["result"] = result_value
                    payloads["model_digest"] = digest
                    # A provider response proves that text was returned, not that an external action was executed.
                    return capability_result(ctx, status="RESPONSE_ONLY", digest=digest,
                                             error_code="PROVIDER_RESPONSE_ONLY_NOT_EXECUTION_PROOF")
                workers = {"memory_knowledge": memory_worker, "research_synthesis": synthesis_worker}
                inventory = {"memory_knowledge": {"memory.search"},
                             "research_synthesis": {"synthesis.propose"}}
                brain_result = BrainOrchestrator().execute(
                    request, available_capabilities=inventory, workers=workers,
                    evidence_verifier=lambda ref: (isinstance(ref, str) and ref.startswith("evidence:sha256:")
                        and ref[16:] in evidence and canonical_digest(evidence[ref[16:]]) == ref[16:]))
                if brain_result["status"] not in {"PARTIAL", "SUCCESS"} or "result" not in payloads:
                    self._send(503, {"ok": False, "error": {"code": "BRAIN_ORCHESTRATION_" + str(brain_result["status"])},
                                     "brain": brain_result})
                    return
                context = payloads["context"]
                result = payloads["result"]
                manifest = result["manifest"]
                audit = {"operation": "model_answer", "model": result.get("model"),
                         "query_sha256": manifest.get("query_sha256"),
                         "context_manifest_sha256": manifest.get("context_manifest_sha256"),
                         "request_sha256": manifest.get("request_sha256"),
                         "response_sha256": manifest.get("response_sha256"),
                         "manifest_sha256": manifest.get("manifest_sha256"),
                         "brain_status": brain_result["status"],
                         "brain_plan_digest": brain_result.get("plan_digest"),
                         "brain_request_id": request_id}
                self.server.runtime.store.emit("model.call.completed", audit,
                    correlation_id=correlation_id, event_id="model-call:" + str(manifest.get("manifest_sha256")))
                self._send(200, {"ok": True, "answer": result["answer"], "model": result["model"],
                                 "context_manifest": context["manifest"], "model_manifest": manifest,
                                 "brain": {"request_id": request_id, "correlation_id": correlation_id,
                                           "source_revision": source_revision, "status": brain_result["status"],
                                           "plan_digest": brain_result.get("plan_digest"),
                                           "invoked_branches": brain_result.get("invoked_branches", []),
                                           "branch_results": brain_result.get("branch_results", [])}})
            except TimeoutError:
                self.close_connection = True
                self._send(408, {"ok": False, "error": {"code": "REQUEST_TIMEOUT"}}, headers={"Connection": "close"})
            except OverflowError:
                self._send(413, {"ok": False, "error": {"code": "BODY_TOO_LARGE"}})
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                self._send(400, {"ok": False, "error": {"code": "INVALID_JSON"}})
            except MemoryDenied as exc:
                self._send(403, {"ok": False, "error": {"code": exc.code}})
            except MemoryErrorBase as exc:
                self._send(422, {"ok": False, "error": {"code": exc.code}})
            except ModelNotConfigured as exc:
                self._send(503, {"ok": False, "error": {"code": exc.code}})
            except ModelGatewayError as exc:
                self._send(502, {"ok": False, "error": {"code": exc.code}})
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
    state_dir = os.environ.get("HG_STATE_DIR")
    runtime = PhoneRuntime(state_dir=state_dir)
    server = HGHTTPServer((host, port), runtime=runtime)
    print(json.dumps({"event": "HG_API_STARTED", "product": "HG", "host": host, "port": port,
                      "runtime_id": runtime.store.runtime_id, "build": build_check}, sort_keys=True), flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
