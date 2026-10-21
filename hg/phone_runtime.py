"""Phone-primary HG runtime: the single canonical state owner."""
from __future__ import annotations

import json, os, secrets, urllib.error, urllib.request
from .sync import SyncContext
from .sync_auth import AuthenticatedBatchGate
from .authority import authorize
from .history import StateStore
from .memory import MemoryStore
from .model_gateway import ModelGateway
from .durable import DurableOutbox


class PhoneRuntime:
    def __init__(self, state_dir=None, edge_url="", edge_token="", device_id=None, timeout=3.0,
                 *, sync_context_id=None, sync_spool_dir=None, authenticated_sync_gate=None):
        self.state_dir = state_dir or os.environ.get("HG_STATE_DIR") or os.path.join(os.getcwd(), "hg-state")
        self.edge_url = edge_url or os.environ.get("HG_EDGE_URL", "")
        self.edge_token = edge_token or os.environ.get("HG_EDGE_TOKEN", "")
        self.device_id = device_id or os.environ.get("HG_DEVICE_ID") or "phone-" + secrets.token_hex(4)
        self.timeout = timeout
        self.store = StateStore(self.state_dir)
        # Compose API services over the canonical state owner; do not create a second store.
        self.memory = MemoryStore(self.store)
        self.model_gateway = ModelGateway(timeout=45)
        self.durable = DurableOutbox(self.store, timeout=timeout)
        self._recover_incomplete_model_calls()
        self.sync_context = None
        self.authenticated_sync_gate = None
        # Authenticated synchronization is opt-in. The adapter reuses this exact store;
        # it is not allowed to create another StateStore for the same runtime directory.
        if any(v is not None for v in (sync_context_id, sync_spool_dir, authenticated_sync_gate)):
            self.configure_authenticated_sync(sync_context_id, sync_spool_dir, authenticated_sync_gate)

    def _recover_incomplete_model_calls(self):
        """Mark calls with a durable start but no terminal receipt IN_DOUBT; never replay them."""
        events = self.store.replay()
        completed = set()
        in_doubt = set()
        starts = {}
        for event in events:
            event_type = event.get("event_type")
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            request_id = payload.get("brain_request_id")
            if not isinstance(request_id, str) or not request_id:
                continue
            if event_type == "model.call.started":
                starts[request_id] = event
            elif event_type == "model.call.completed":
                completed.add(request_id)
            elif event_type == "model.call.in_doubt":
                in_doubt.add(request_id)
        for request_id, event in starts.items():
            if request_id in completed or request_id in in_doubt:
                continue
            source = event.get("payload", {})
            correlation_id = event.get("correlation_id")
            payload = {
                "operation": "model_answer",
                "brain_request_id": request_id,
                "correlation_id": correlation_id,
                "query_sha256": source.get("query_sha256"),
                "context_manifest_sha256": source.get("context_manifest_sha256"),
                "brain_plan_digest": source.get("brain_plan_digest"),
                "reason": "OUTCOME_UNKNOWN_AFTER_START",
            }
            self.store.emit(
                "model.call.in_doubt", payload,
                correlation_id=correlation_id,
                causation_id=event.get("event_id"),
                event_id="model-call-in-doubt:" + request_id,
            )

    def mark_model_call_in_doubt(self, start_event):
        """Persist the same conservative recovery marker from a duplicate-request path."""
        if not isinstance(start_event, dict) or start_event.get("event_type") != "model.call.started":
            raise ValueError("MODEL_CALL_START_EVENT_REQUIRED")
        source = start_event.get("payload")
        if not isinstance(source, dict):
            raise ValueError("MODEL_CALL_START_PAYLOAD_INVALID")
        request_id = source.get("brain_request_id")
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("MODEL_CALL_REQUEST_ID_MISSING")
        correlation_id = start_event.get("correlation_id")
        payload = {
            "operation": "model_answer",
            "brain_request_id": request_id,
            "correlation_id": correlation_id,
            "query_sha256": source.get("query_sha256"),
            "context_manifest_sha256": source.get("context_manifest_sha256"),
            "brain_plan_digest": source.get("brain_plan_digest"),
            "reason": "OUTCOME_UNKNOWN_AFTER_START",
        }
        return self.store.emit(
            "model.call.in_doubt", payload,
            correlation_id=correlation_id,
            causation_id=start_event.get("event_id"),
            event_id="model-call-in-doubt:" + request_id,
        )

    def configure_authenticated_sync(self, context_id, spool_dir, gate):
        if not isinstance(context_id, str) or not context_id.strip():
            raise ValueError("sync_context_id required when sync is configured")
        if not isinstance(spool_dir, str) or not spool_dir:
            raise ValueError("sync_spool_dir required when sync is configured")
        if not isinstance(gate, AuthenticatedBatchGate):
            raise ValueError("authenticated sync gate required; fail closed")
        state = os.path.realpath(self.store.dir)
        cursor = os.path.realpath(gate.cursor_path)
        try:
            cursor_inside_state = os.path.commonpath((state, cursor)) == state
        except ValueError:
            cursor_inside_state = False
        if cursor_inside_state:
            raise ValueError("authenticated cursor must be outside StateStore directory")
        self.sync_context = SyncContext(context_id, self.state_dir, spool_dir, store=self.store)
        if self.sync_context.store is not self.store:
            raise RuntimeError("sync adapter must reuse the canonical StateStore")
        self.authenticated_sync_gate = gate

    def publish_sync_event(self, event_type: str, payload: dict) -> dict:
        if self.sync_context is None:
            raise PermissionError("sync is not configured")
        return self.sync_context.publish(event_type, payload)

    def import_authenticated_batch(self, filename: str) -> dict:
        if self.sync_context is None or self.authenticated_sync_gate is None:
            raise PermissionError("authenticated sync is not configured")
        return self.sync_context.import_authenticated_batch(filename, self.authenticated_sync_gate)

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
