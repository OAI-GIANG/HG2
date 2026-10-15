"""Phone-only HG runtime with local durable state and no network integration."""
from __future__ import annotations

import os
import secrets
from .authority import authorize
from .history import StateStore


class PhoneRuntime:
    def __init__(self, state_dir=None, session_authenticator=None):
        self.state_dir = state_dir or os.environ.get("HG_STATE_DIR") or os.path.join(os.getcwd(), "hg-state")
        # Session creation requires an explicit credential verifier.
        # No implicit authenticated=True shortcut is permitted.
        self.session_authenticator = session_authenticator
        self.store = StateStore(self.state_dir)

    def health(self):
        return {"ok": True, "product": "HG", "runtime_id": self.store.runtime_id,
                "integrity": self.store.verify(), "network_integration": False}

    def start_session(self, correlation_id=None, *, credential=None):
        authenticated = False
        verifier = self.session_authenticator
        if callable(verifier):
            try:
                authenticated = verifier(credential) is True
            except Exception:
                authenticated = False
        d = authorize("session.create", authenticated=authenticated)
        if not d.allowed:
            raise PermissionError(d.reason)
        rec = self.store.emit("session.created", {"session_id": secrets.token_urlsafe(18), "product": "HG"},
                              correlation_id=correlation_id)
        return dict(rec["payload"])
