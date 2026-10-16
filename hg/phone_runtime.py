"""Phone-only HG runtime with local durable state and no network integration."""
from __future__ import annotations

import os
import secrets
from .sync import SyncContext
from .sync_auth import AuthenticatedBatchGate
from .authority import authorize
from .history import StateStore
from .provenance import loaded_module_identity


class PhoneRuntime:
    def __init__(self, state_dir=None, session_authenticator=None, *, sync_context_id=None,
                 sync_spool_dir=None, authenticated_sync_gate=None):
        self.state_dir = state_dir or os.environ.get("HG_STATE_DIR") or os.path.join(os.getcwd(), "hg-state")
        # Session creation requires an explicit credential verifier.
        # No implicit authenticated=True shortcut is permitted.
        self.session_authenticator = session_authenticator
        self.store = StateStore(self.state_dir)
        self.sync_context = None
        self.authenticated_sync_gate = None
        # Sync is opt-in. The runtime reuses its one canonical StateStore; no second
        # StateStore is constructed for the same directory. No network listener is added.
        if any(v is not None for v in (sync_context_id, sync_spool_dir, authenticated_sync_gate)):
            self.configure_authenticated_sync(sync_context_id, sync_spool_dir, authenticated_sync_gate)

    def configure_authenticated_sync(self, context_id, spool_dir, gate):
        if not isinstance(context_id, str) or not context_id.strip():
            raise ValueError("sync_context_id required when sync is configured")
        if not isinstance(spool_dir, str) or not spool_dir:
            raise ValueError("sync_spool_dir required when sync is configured")
        if not isinstance(gate, AuthenticatedBatchGate):
            raise ValueError("authenticated sync gate required; fail closed")
        cursor = os.path.realpath(gate.cursor_path)
        state = os.path.realpath(self.store.dir)
        if os.path.commonpath((state, cursor)) == state:
            raise ValueError("authenticated cursor must be outside StateStore directory")
        self.sync_context = SyncContext(context_id, self.state_dir, spool_dir, store=self.store)
        self.authenticated_sync_gate = gate

    def import_authenticated_batch(self, filename: str) -> dict:
        if self.sync_context is None or self.authenticated_sync_gate is None:
            raise PermissionError("authenticated sync is not configured")
        return self.sync_context.import_authenticated_batch(filename, self.authenticated_sync_gate)

    def publish_sync_event(self, event_type: str, payload: dict) -> dict:
        if self.sync_context is None:
            raise PermissionError("sync is not configured")
        return self.sync_context.publish(event_type, payload)

    def health(self):
        # Report the Python code objects loaded in this process separately from the
        # current on-disk hashes. This is diagnostic evidence, not remote attestation.
        return {"ok": True, "product": "HG", "runtime_id": self.store.runtime_id,
                "integrity": self.store.verify(), "network_integration": False,
                "runtime_identity": loaded_module_identity()}

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
