"""Authenticated MAEP HTTP seam tests; all state is isolated in temporary directories."""
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from types import SimpleNamespace
from unittest.mock import patch

from hg.auth import BearerAuthenticator
from hg.maep import MaepOrchestrator
from hg.server import HGHTTPServer
from hg.sqlite_state import SQLiteStateStore
from hg.workflow_store_adapter import CanonicalWorkflowAdapter

READ_TOKEN = "test-hg-api-read-token"
WRITE_TOKEN = "test-hg-api-write-token"


def make_task(task_id="api-maep-task"):
    return {
        "task_id": task_id,
        "OBJECTIVE": "Verify authenticated MAEP API",
        "SCOPE": {"repository": "OAI-GIANG/HG2"},
        "INPUT": {"source": "test fixture"},
        "OUTPUT": {"kind": "checkpoint"},
        "ACCEPTANCE_CRITERIA": [{
            "id": "C1", "description": "Task checkpoint persists",
            "required": True, "verification": "GET task after POST",
        }],
        "EVIDENCE": [],
        "RISKS": [],
        "STOP_CONDITION": "Stop if authorization or evidence is missing",
        "NEXT_ACTION": "Verify the persisted checkpoint",
        "CLOSURE_CONDITIONS": ["Required criterion has verified evidence"],
        "REPOSITORY": "OAI-GIANG/HG2",
    }


class MaepApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {
            "HG_API_READ_TOKEN": READ_TOKEN,
            "HG_API_WRITE_TOKEN": WRITE_TOKEN,
            "HG_API_READ_TOKEN_ID": "read-v1",
            "HG_API_WRITE_TOKEN_ID": "write-v1",
            "HG_API_READ_TOKEN_EXPIRES_AT": "4102444800",
            "HG_API_WRITE_TOKEN_EXPIRES_AT": "4102444800",
            "HG_API_REVOKED_TOKEN_IDS": "",
            "HG_API_PRINCIPAL_ID": "test-owner",
            "HG_MEMORY_READ_SCOPES": "owner,global,HG",
            "HG_MEMORY_WRITE_SCOPES": "owner,global,HG",
        }, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.store = SQLiteStateStore(os.path.join(self.temp.name, "state"))
        self.addCleanup(self.store.close)
        self.principal = BearerAuthenticator(
            "maep-checkpoint-token", {"audit.append"}, principal_id="test-owner"
        ).authenticate("Bearer maep-checkpoint-token")
        self.adapter = CanonicalWorkflowAdapter(
            self.store, principal=self.principal, actor_id="test-owner", clock=time.time
        )
        self.engine = self.adapter.maep_orchestrator()
        self.runtime = SimpleNamespace(store=self.store)
        self.server = HGHTTPServer(
            ("127.0.0.1", 0), runtime=self.runtime, maep_orchestrator=self.engine
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.base = "http://127.0.0.1:%d" % self.server.server_port
        self.server.read_scopes = frozenset({"workflow.task.read"})
        self.server.write_scopes = frozenset({
            "workflow.task.create", "workflow.task.transition", "audit.append"
        })

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def call(self, path, method="GET", obj=None, token=READ_TOKEN):
        data = None if obj is None else json.dumps(obj).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if token:
            req.add_header("Authorization", "Bearer " + token)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=3) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def test_create_read_and_run_fail_closed_without_stage_adapters(self):
        status, body = self.call(
            "/api/maep/tasks", "POST", {"task": make_task()}, token=WRITE_TOKEN
        )
        self.assertEqual(status, 201)
        self.assertEqual(body["task"]["CURRENT_STATE"], "S0")
        self.assertEqual(body["task"]["status"], "IN_PROGRESS")

        status, body = self.call("/api/maep/tasks/api-maep-task", token=READ_TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(body["task"]["task_id"], "api-maep-task")

        status, body = self.call(
            "/api/maep/tasks", "POST", {"task": make_task()}, token=WRITE_TOKEN
        )
        self.assertEqual(status, 409)
        self.assertEqual(body["error"]["code"], "MAEP_TASK_ALREADY_EXISTS")

        status, body = self.call(
            "/api/maep/tasks/api-maep-task/run", "POST", {"max_steps": 1}, token=WRITE_TOKEN
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["task"]["status"], "BLOCKED")
        self.assertEqual(body["task"]["block"]["code"], "STAGE_HANDLER_UNAVAILABLE")
        self.assertNotEqual(body["task"]["status"], "CLOSED_VERIFIED")

    def test_authentication_and_scope_gates_precede_mutation(self):
        status, body = self.call(
            "/api/maep/tasks", "POST", {"task": make_task("unauth-task")}, token=None
        )
        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["code"], "UNAUTHORIZED")
        self.assertFalse(any(e.get("event_type") == "maep.task_checkpoint"
                             for e in self.store.replay()))

        self.server.write_scopes = frozenset({"workflow.task.create"})
        status, body = self.call(
            "/api/maep/tasks", "POST", {"task": make_task("scope-denied-task")}, token=WRITE_TOKEN
        )
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "MAEP_SCOPE_DENIED")
        self.assertFalse(any(e.get("event_type") == "maep.task_checkpoint"
                             for e in self.store.replay()))

    def test_store_identity_mismatch_is_rejected_at_server_construction(self):
        legacy_dir = os.path.join(self.temp.name, "legacy")
        from hg.phone_runtime import PhoneRuntime
        legacy_runtime = PhoneRuntime(state_dir=legacy_dir)
        with self.assertRaisesRegex(RuntimeError, "MAEP_RUNTIME_STORE_MISMATCH"):
            HGHTTPServer(
                ("127.0.0.1", 0), runtime=legacy_runtime, maep_orchestrator=self.engine
            )

    def test_unconfigured_maep_returns_503_after_authentication(self):
        self.server.maep_orchestrator = None
        status, body = self.call(
            "/api/maep/tasks", "POST", {"task": make_task("not-bound-task")}, token=WRITE_TOKEN
        )
        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["code"], "MAEP_RUNTIME_NOT_CONFIGURED")
        self.assertFalse(any(e.get("event_type") == "maep.task_checkpoint"
                             for e in self.store.replay()))


if __name__ == "__main__":
    unittest.main()
