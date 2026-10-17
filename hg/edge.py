"""VPS1 edge / HTTPS relay. Relays only; owns no canonical state and holds no model key."""
from __future__ import annotations

import hmac, os, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .contracts import ContractError, canonical_json, parse_json_no_duplicate_keys

MAX_BODY = 8192
DEVICES = {}
_LOCK = threading.RLock()


def _contains_model_key_field(value):
    """Inspect field names, not arbitrary string values, for model-key material."""
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = "".join(ch.lower() for ch in key if ch.isalnum())
            if "model" in normalized and "key" in normalized:
                return True
            if _contains_model_key_field(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_model_key_field(item) for item in value)
    return False


_PAYLOAD_FIELDS = {
    "/edge/register": frozenset({"device_id", "runtime", "architecture"}),
    "/edge/heartbeat": frozenset({"device_id", "runtime", "seq"}),
}


def validate_payload(path, payload):
    """Validate an edge request before any device-state mutation; never coerce fields."""
    if not isinstance(payload, dict):
        return "INVALID_PAYLOAD"
    if _contains_model_key_field(payload):
        return "MODEL_KEY_NOT_ACCEPTED"
    allowed = _PAYLOAD_FIELDS.get(path)
    if allowed is None:
        return "INVALID_ENDPOINT"
    if set(payload) - allowed:
        return "UNKNOWN_FIELD"

    device_id = payload.get("device_id")
    if not isinstance(device_id, str) or not device_id.strip():
        return "DEVICE_ID_REQUIRED"
    if len(device_id) > 128:
        return "DEVICE_ID_TOO_LONG"

    if "runtime" in payload:
        runtime = payload["runtime"]
        if not isinstance(runtime, str):
            return "INVALID_RUNTIME"
        if len(runtime) > 64:
            return "RUNTIME_TOO_LONG"

    if path == "/edge/register" and "architecture" in payload:
        if payload["architecture"] != "PHONE_PRIMARY_V1":
            return "UNSUPPORTED_ARCHITECTURE"

    if path == "/edge/heartbeat":
        seq = payload.get("seq")
        if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
            return "INVALID_SEQUENCE"

    return None


def edge_token():
    return os.environ.get("HG_EDGE_TOKEN", "")


def authenticated(header):
    expected = edge_token()
    if not expected or not isinstance(header, str):
        return False
    scheme, sep, supplied = header.partition(" ")
    if not sep or scheme.lower() != "bearer" or not supplied:
        return False
    return hmac.compare_digest(supplied.encode(), expected.encode())


class Handler(BaseHTTPRequestHandler):
    server_version = "HG-EDGE/1.0"
    sys_version = ""
    timeout = 5

    def log_message(self, fmt, *args):
        return

    def _send(self, status, payload):
        body = canonical_json(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True, "product": "HG", "role": "edge_relay", "devices": len(DEVICES)})
            return
        if self.path == "/edge/status":
            if not authenticated(self.headers.get("Authorization")):
                self._send(403, {"ok": False, "error": "AUTHENTICATION_REQUIRED"})
                return
            with _LOCK:
                self._send(200, {"ok": True, "devices": dict(DEVICES)})
            return
        self._send(404, {"ok": False, "error": "NOT_FOUND"})

    def do_POST(self):
        if self.path not in ("/edge/register", "/edge/heartbeat"):
            self._send(404, {"ok": False, "error": "NOT_FOUND"})
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except (TypeError, ValueError):
            self._send(400, {"ok": False, "error": "INVALID_CONTENT_LENGTH"})
            return
        if length < 0 or length > MAX_BODY:
            self._send(413, {"ok": False, "error": "BODY_LIMIT_EXCEEDED"})
            return
        if not authenticated(self.headers.get("Authorization")):
            self._send(403, {"ok": False, "error": "AUTHENTICATION_REQUIRED"})
            return
        try:
            raw_body = self.rfile.read(length).decode("utf-8")
            payload = parse_json_no_duplicate_keys(raw_body)
        except UnicodeDecodeError:
            self._send(400, {"ok": False, "error": "INVALID_JSON"})
            return
        except ContractError as exc:
            error = "DUPLICATE_JSON_KEY" if str(exc) == "DUPLICATE_JSON_KEY" else "INVALID_JSON"
            self._send(400, {"ok": False, "error": error})
            return

        validation_error = validate_payload(self.path, payload)
        if validation_error:
            self._send(400, {"ok": False, "error": validation_error})
            return
        device_id = payload["device_id"]
        with _LOCK:
            entry = DEVICES.setdefault(device_id, {"device_id": device_id, "first_seen": int(time.time())})
            entry["last_seen"] = int(time.time())
            entry["runtime"] = str(payload.get("runtime", ""))[:64]
            entry["seq"] = payload.get("seq")
        self._send(201, {"ok": True, "registered": self.path.endswith("register"), "device_id": device_id})


def main():
    if not edge_token():
        raise SystemExit("HG_EDGE_TOKEN required (fail-closed)")
    server = ThreadingHTTPServer((os.environ.get("HG_EDGE_BIND", "127.0.0.1"), int(os.environ.get("HG_EDGE_PORT", "8787"))), Handler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
