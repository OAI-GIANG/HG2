"""Phone-primary HG runtime: the single canonical state owner."""
from __future__ import annotations

import json, os, secrets, urllib.error, urllib.request
from .authority import authorize
from .history import StateStore
from .memory import MemoryStore


class PhoneRuntime:
    def __init__(self, state_dir=None, edge_url="", edge_token="", device_id=None, timeout=3.0):
        self.state_dir = state_dir or os.environ.get("HG_STATE_DIR") or os.path.join(os.getcwd(), "hg-state")
        self.edge_url = edge_url or os.environ.get("HG_EDGE_URL", "")
        self.edge_token = edge_token or os.environ.get("HG_EDGE_TOKEN", "")
        self.device_id = device_id or os.environ.get("HG_DEVICE_ID") or "phone-" + secrets.token_hex(4)
        self.timeout = timeout
        self.store = StateStore(self.state_dir)
        # Memory shares the sole canonical state owner; no second database/runtime.
        self.memory = MemoryStore(self.store)

    def health(self):
        return {"ok": True, "product": "HG", "runtime_id": self.store.runtime_id,
                "edge_configured": bool(self.edge_url), "integrity": self.store.verify()}

    def start_session(self, correlation_id=None):
        d = authorize("session.create", authenticated=True)
        if not d.allowed:
            raise PermissionError(d.reason)
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
