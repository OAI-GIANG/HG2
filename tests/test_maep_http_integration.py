"""HTTP-level MAEP integration tests with one isolated SQLite state owner."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import urllib.error
import urllib.request
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hg.auth import BearerAuthenticator
from hg.maep_host_binding import MaepHostBinding
from hg.server import HGHTTPServer
from hg.sqlite_state import SQLiteStateStore
from hg.workflow_store_adapter import CanonicalWorkflowAdapter

READ_TOKEN = "test-maep-read-token"
WRITE_TOKEN = "test-maep-write-token"
MAEP_SCOPES = "audit.append,brain.request"


def task(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "OBJECTIVE": "HTTP MAEP integration acceptance",
        "SCOPE": {"include": ["HG2"], "exclude": ["production cutover"]},
        "INPUT": {"source": "isolated HTTP fixture"},
        "OUTPUT": {"artifact": "MAEP checkpoint"},
        "ACCEPTANCE_CRITERIA": [{
            "id": "criterion:http",
            "description": "HTTP route is idempotent and durable",
            "required": True,
            "verification": "isolated HTTP integration test",
        }],
        "EVIDENCE": [{"type": "test", "purpose": "HTTP integration"}],
        "RISKS": [{"id": "risk:retry", "severity": "HIGH"}],
        "STOP_CONDITION": "Stop on authorization or evidence uncertainty",
        "NEXT_ACTION": "Run one authorized phase",
        "CLOSURE_CONDITIONS": ["phase checkpoint is durable"],
        "REPOSITORY": "OAI-GIANG/HG2",
        "BRANCH": "test/maep-http-integration",
        "HEAD": "isolated-http-fixture-head",
        "WORKING_TREE": "clean",
    }


class MaepHttpIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hg-maep-http-")
        self.addCleanup(self.temp.cleanup)
        self.state_dir = os.path.join(self.temp.name, "state")
        self.invocations = []
        self.env = patch.dict(os.environ, {
            "HG_API_READ_TOKEN": READ_TOKEN,
            "HG_API_WRITE_TOKEN": WRITE_TOKEN,
            "HG_API_READ_TOKEN_ID": "maep-read-v1",
            "HG_API_WRITE_TOKEN_ID": "maep-write-v1",
            "HG_API_READ_TOKEN_EXPIRES_AT": "4102444800",
            "HG_API_WRITE_TOKEN_EXPIRES_AT": "4102444800",
            "HG_API_REVOKED_TOKEN_IDS": "",
            "HG_API_PRINCIPAL_ID": "maep-http-owner",
            "HG_MEMORY_READ_SCOPES": "owner,global,HG",
            "HG_MEMORY_WRITE_SCOPES": "owner,global,HG",
            "HG_MAEP_SCOPES": MAEP_SCOPES,
        }, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self._open_runtime()
        self._start_server()
        self.addCleanup(self._cleanup_runtime)

    def _open_runtime(self):
        self.store = SQLiteStateStore(self.state_dir, clock=lambda: 100.0)
        # HGHTTPServer's process lock is scoped to the canonical store directory.
        self.store.dir = self.store.directory
        principal = BearerAuthenticator(
            WRITE_TOKEN, {"audit.append", "brain.request"}, principal_id="maep-http-owner"
        ).authenticate("Bearer " + WRITE_TOKEN)
        self.adapter = CanonicalWorkflowAdapter(
            self.store, principal=principal, actor_id="maep-http-owner", clock=lambda: 100.0
        )
        verified = {"ev:entry:S0", "ev:exit:S0", "ev:stage:S0"}

        def prepare(state, context):
            return {"passed": True, "evidence_ids": ["ev:entry:S0"]}

        def run(state, context):
            self.invocations.append((context["task_id"], context["phase_id"], context["idempotency_key"]))
            return {
                "status": "COMPLETE",
                "exit_criteria": {"passed": True, "evidence_ids": ["ev:exit:S0"]},
                "evidence_ids": ["ev:stage:S0"],
            }

        def authorize(action, context):
            if not principal.allows(action):
                return False, "principal-scope-denied"
            if context.get("phase_id") != "S0" or action != "brain.request":
                return False, "phase-action-mismatch"
            return True, "isolated-http-policy:maep-http-owner:brain.request"

        def verify_evidence(ids, context):
            if not ids or any(item not in verified for item in ids):
                return False, "fixture-evidence-not-registered"
            return True, "isolated-http-evidence-registry:v1"

        self.binding = MaepHostBinding(
            self.adapter,
            phase_actions={"S0": "brain.request"},
            handler_registry={"brain.request": {
                "action": "brain.request", "prepare": prepare, "run": run,
            }},
            action_scopes={"brain.request": "brain.request"},
            authorizer=authorize,
            evidence_verifier=verify_evidence,
        )
        self.runtime = SimpleNamespace(store=self.store, maep_binding=self.binding)

    def _start_server(self):
        self.server = HGHTTPServer(("127.0.0.1", 0), runtime=self.runtime)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.server.server_port

    def _stop_server(self):
        server = getattr(self, "server", None)
        thread = getattr(self, "thread", None)
        if server is not None:
            server.shutdown()
            server.server_close()
            self.server = None
        if thread is not None:
            thread.join(timeout=2)
            self.thread = None

    def _cleanup_runtime(self):
        self._stop_server()
        store = getattr(self, "store", None)
        if store is not None:
            try:
                store.close()
            except Exception:
                pass
            self.store = None

    def call(self, path, method="POST", obj=None, token=WRITE_TOKEN, key=None):
        data = None if obj is None else json.dumps(obj).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if token:
            req.add_header("Authorization", "Bearer " + token)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if key is not None:
            req.add_header("Idempotency-Key", key)
        try:
            with urllib.request.urlopen(req, timeout=3) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def test_task_create_and_phase_are_http_idempotent_across_store_reopen(self):
        task_id = "task:http-maep-idempotency"
        status, created = self.call("/api/maep/tasks", obj={"task": task(task_id)}, key=task_id)
        self.assertEqual(status, 201)
        self.assertFalse(created["idempotency"]["replayed"])

        status, replayed_create = self.call("/api/maep/tasks", obj={"task": task(task_id)}, key=task_id)
        self.assertEqual(status, 200)
        self.assertTrue(replayed_create["idempotency"]["replayed"])
        self.assertEqual(replayed_create["task"]["revision"], created["task"]["revision"])

        status, ran = self.call(
            f"/api/maep/tasks/{task_id}/run-next", obj={}, key=task_id + ":S0"
        )
        self.assertEqual(status, 200)
        self.assertEqual(ran["task"]["CURRENT_STATE"], "S1")
        self.assertEqual(len(self.invocations), 1)

        status, replayed_run = self.call(
            f"/api/maep/tasks/{task_id}/run-next", obj={}, key=task_id + ":S0"
        )
        self.assertEqual(status, 200)
        self.assertTrue(replayed_run["idempotency"]["replayed"])
        self.assertEqual(replayed_run["task"]["revision"], ran["task"]["revision"])
        self.assertEqual(len(self.invocations), 1)

        self._stop_server()
        self.store.close()
        self._open_runtime()
        self._start_server()
        status, after_restart = self.call(
            f"/api/maep/tasks/{task_id}/run-next", obj={}, key=task_id + ":S0"
        )
        self.assertEqual(status, 200)
        self.assertTrue(after_restart["idempotency"]["replayed"])
        self.assertEqual(after_restart["task"]["CURRENT_STATE"], "S1")
        self.assertEqual(len(self.invocations), 1)
        self.assertTrue(self.store.verify()["ok"])

    def test_interrupted_running_checkpoint_is_blocked_without_replaying_handler(self):
        task_id = "task:http-maep-crash"
        status, created = self.call("/api/maep/tasks", obj={"task": task(task_id)}, key=task_id)
        self.assertEqual(status, 201)
        engine = self.binding.build_orchestrator()
        state = engine.load_task(task_id)
        state["stage_results"] = {
            "S0": {
                "status": "RUNNING",
                "action": "brain.request",
                "authorization_ref": "isolated-http-policy:maep-http-owner:brain.request",
                "started_at": 101.0,
                "idempotency_key": task_id + ":S0",
                "entry_gate": {"passed": True, "evidence_ids": ["ev:entry:S0"],
                               "verification_ref": "isolated-http-evidence-registry:v1"},
            }
        }
        engine._save(state)
        self._stop_server()
        self.store.close()
        self._open_runtime()
        self._start_server()

        status, blocked = self.call(
            f"/api/maep/tasks/{task_id}/run-next", obj={}, key=task_id + ":S0"
        )
        self.assertEqual(status, 409)
        self.assertEqual(blocked["error"]["code"], "MAEP_INTERRUPTED_ACTION_REQUIRES_RECONCILIATION")
        self.assertEqual(blocked["task"]["status"], "BLOCKED")
        self.assertEqual(self.invocations, [])
        self.assertTrue(self.store.verify()["ok"])

        status, replay = self.call(
            f"/api/maep/tasks/{task_id}/run-next", obj={}, key=task_id + ":S0"
        )
        self.assertEqual(status, 200)
        self.assertTrue(replay["idempotency"]["replayed"])
        self.assertEqual(self.invocations, [])

    def test_route_fails_closed_without_same_store_binding_or_sealed_principal(self):
        self.runtime.maep_binding = None
        status, body = self.call("/api/maep/tasks", obj={"task": task("task:no-binding")}, key="task:no-binding")
        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["code"], "MAEP_RUNTIME_BINDING_UNAVAILABLE")

        self.runtime.maep_binding = self.binding
        status, body = self.call("/api/maep/tasks", obj={"task": task("task:no-auth")}, key="task:no-auth", token=None)
        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["code"], "UNAUTHORIZED")


if __name__ == "__main__":
    unittest.main()
