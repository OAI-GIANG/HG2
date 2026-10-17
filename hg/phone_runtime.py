"""Phone-primary HG runtime: the single canonical state owner."""
from __future__ import annotations

import json, os, secrets, urllib.error, urllib.request
from .policy import authorize, authorize_principal
from .history import StateStore
from .sqlite_state import SQLiteStateStore


def open_state_store(state_dir):
    """Select one explicit backend and refuse ambiguous mixed-state directories."""
    backend = os.environ.get("HG_STATE_BACKEND", "legacy").strip().lower()
    sqlite_path = os.path.join(state_dir, "hg2-state.sqlite3")
    legacy_paths = (
        os.path.join(state_dir, "history.jsonl"),
        os.path.join(state_dir, "head.json"),
        os.path.join(state_dir, "state.json"),
        os.path.join(state_dir, "runtime_id"),
    )
    legacy_present = any(os.path.exists(path) for path in legacy_paths)
    sqlite_present = os.path.exists(sqlite_path)

    if backend == "legacy":
        if sqlite_present:
            raise RuntimeError("HG_STATE_BACKEND_CONFLICT")
        return StateStore(state_dir)
    if backend == "sqlite":
        if legacy_present and sqlite_present:
            raise RuntimeError("HG_STATE_BACKEND_CONFLICT")
        if legacy_present:
            raise RuntimeError("HG_STATE_MIGRATION_REQUIRED")
        return SQLiteStateStore(state_dir)
    raise RuntimeError("UNSUPPORTED_HG_STATE_BACKEND")


class PhoneRuntime:
    def __init__(self, state_dir=None, edge_url="", edge_token="", device_id=None, timeout=3.0,
                 session_authenticator=None):
        self.state_dir = state_dir or os.environ.get("HG_STATE_DIR") or os.path.join(os.getcwd(), "hg-state")
        self.edge_url = edge_url or os.environ.get("HG_EDGE_URL", "")
        self.edge_token = edge_token or os.environ.get("HG_EDGE_TOKEN", "")
        self.device_id = device_id or os.environ.get("HG_DEVICE_ID") or "phone-" + secrets.token_hex(4)
        self.timeout = timeout
        # Session creation has no implicit authenticated=True shortcut. The trusted host
        # must inject a real verifier; missing, rejecting, or failing verifiers deny.
        self.session_authenticator = session_authenticator
        self.store = open_state_store(self.state_dir)

    def health(self):
        return {"ok": True, "product": "HG", "runtime_id": self.store.runtime_id,
                "edge_configured": bool(self.edge_url), "integrity": self.store.verify()}

    def start_session(self, correlation_id=None, *, credential=None, principal=None):
        if principal is not None and credential is not None:
            raise PermissionError("AMBIGUOUS_SESSION_CREDENTIAL")
        if principal is None:
            verifier = self.session_authenticator
            if callable(verifier):
                try:
                    principal = verifier(credential)
                except Exception:
                    principal = None
        # A verifier must return a sealed AuthenticatedPrincipal. Boolean True is not
        # authentication proof and is intentionally rejected by policy.
        decision = authorize_principal("session.create", principal)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        rec = self.store.emit("session.created", {"session_id": secrets.token_urlsafe(18), "product": "HG"},
                              correlation_id=correlation_id)
        return dict(rec["payload"])

    def _post(self, path, body):
        if not self.edge_url or not self.edge_token:
            return False
        d = authorize("edge.heartbeat", authenticated=True)
        if not d.allowed:
            raise PermissionError(d.reason)
        req = urllib.request.Request(self.edge_url.rstrip("/") + path,
                                     data=json.dumps(body).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + self.edge_token)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return 200 <= r.status < 300
        except (urllib.error.URLError, OSError):
            return False

    def register(self):
        return self._post("/edge/register", {"device_id": self.device_id, "runtime": self.store.runtime_id,
                                             "architecture": "PHONE_PRIMARY_V1"})

    def heartbeat(self):
        return self._post("/edge/heartbeat", {"device_id": self.device_id, "runtime": self.store.runtime_id,
                                              "seq": self.store.audit_export()["last_seq"]})
