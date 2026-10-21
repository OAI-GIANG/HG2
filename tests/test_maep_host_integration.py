"""Isolated integration checks for MAEP host binding, sealed scopes, and durable restart."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hg.auth import BearerAuthenticator
from hg.maep_host_binding import MaepHostBinding, MaepHostBindingError
from hg.sqlite_state import SQLiteStateStore
from hg.workflow_store_adapter import CanonicalWorkflowAdapter


def _task(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "OBJECTIVE": "Verify host binding with an authenticated principal",
        "SCOPE": {"include": ["HG2"], "exclude": ["production cutover"]},
        "INPUT": {"source": "isolated integration fixture"},
        "OUTPUT": {"artifact": "durable MAEP checkpoint"},
        "ACCEPTANCE_CRITERIA": [{
            "id": "criterion:host-binding",
            "description": "A scoped phase executes and survives store reopen",
            "required": True,
            "verification": "isolated integration test",
        }],
        "EVIDENCE": [{"type": "test", "purpose": "host binding integration"}],
        "RISKS": [{"id": "risk:duplicate", "severity": "HIGH"}],
        "STOP_CONDITION": "Stop on authorization or evidence uncertainty",
        "NEXT_ACTION": "Run one authorized phase",
        "CLOSURE_CONDITIONS": ["phase checkpoint is durable"],
        "REPOSITORY": "OAI-GIANG/HG2",
        "BRANCH": "test/maep-host-integration",
        "HEAD": "isolated-fixture-head",
        "WORKING_TREE": "clean",
    }


class MaepHostIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hg-maep-host-integration-")
        self.addCleanup(self.temp.cleanup)
        self.store = SQLiteStateStore(str(Path(self.temp.name) / "state"), clock=lambda: 100.0)
        self.addCleanup(lambda: self.store.close())
        self.principal = BearerAuthenticator(
            "integration-token", {"audit.append", "brain.request"}, principal_id="integration-owner"
        ).authenticate("Bearer integration-token")
        self.adapter = CanonicalWorkflowAdapter(
            self.store, principal=self.principal, actor_id="integration-owner", clock=lambda: 100.0
        )
        self.verified_fixture_ids = {"ev:entry:S0", "ev:exit:S0", "ev:stage:S0"}
        self.invocations = []

        def prepare(state, context):
            return {"passed": True, "evidence_ids": ["ev:entry:S0"]}

        def run(state, context):
            self.invocations.append((context["phase_id"], context["idempotency_key"]))
            return {
                "status": "COMPLETE",
                "exit_criteria": {"passed": True, "evidence_ids": ["ev:exit:S0"]},
                "evidence_ids": ["ev:stage:S0"],
            }

        self.handlers = {
            "brain.request": {"action": "brain.request", "prepare": prepare, "run": run}
        }

        def authorize(action, context):
            if not self.principal.allows(action):
                return False, "principal-scope-denied"
            if context.get("phase_id") != "S0" or action != "brain.request":
                return False, "phase-action-mismatch"
            return True, "isolated-policy:integration-owner:brain.request"

        def verify_evidence(ids, context):
            if not ids or any(item not in self.verified_fixture_ids for item in ids):
                return False, "fixture-evidence-not-registered"
            return True, "isolated-evidence-registry:v1"

        self.authorizer = authorize
        self.verifier = verify_evidence
        self.phase_actions = {"S0": "brain.request"}
        self.action_scopes = {"brain.request": "brain.request"}

    def _binding(self):
        return MaepHostBinding(
            self.adapter,
            phase_actions=self.phase_actions,
            handler_registry=self.handlers,
            action_scopes=self.action_scopes,
            authorizer=self.authorizer,
            evidence_verifier=self.verifier,
        )

    def test_scoped_phase_is_authorized_and_checkpoint_survives_reopen(self):
        engine = self._binding().build_orchestrator()
        engine.create_task(_task("task:host-binding-integration"))
        state = engine.run_next("task:host-binding-integration")
        self.assertEqual(state["CURRENT_STATE"], "S1")
        self.assertEqual(state["status"], "IN_PROGRESS")
        self.assertEqual(self.invocations, [("S0", "task:host-binding-integration:S0")])
        self.assertTrue(self.store.verify()["ok"])

        self.store.close()
        self.store = SQLiteStateStore(str(Path(self.temp.name) / "state"), clock=lambda: 100.0)
        self.adapter = CanonicalWorkflowAdapter(
            self.store, principal=self.principal, actor_id="integration-owner", clock=lambda: 100.0
        )
        reopened = self._binding().build_orchestrator()
        restored = reopened.load_task("task:host-binding-integration")
        self.assertEqual(restored["CURRENT_STATE"], "S1")
        self.assertEqual(restored["revision"], state["revision"])
        self.assertEqual(restored["stage_results"]["S0"]["status"], "COMPLETE")
        self.assertTrue(self.store.verify()["ok"])

    def test_unscoped_principal_cannot_bind_privileged_phase(self):
        unscoped = BearerAuthenticator(
            "read-only-token", {"audit.append"}, principal_id="read-only"
        ).authenticate("Bearer read-only-token")
        adapter = CanonicalWorkflowAdapter(
            self.store, principal=unscoped, actor_id="read-only", clock=lambda: 100.0
        )
        with self.assertRaisesRegex(MaepHostBindingError, "ACTION_SCOPE_NOT_GRANTED"):
            MaepHostBinding(
                adapter,
                phase_actions=self.phase_actions,
                handler_registry=self.handlers,
                action_scopes=self.action_scopes,
                authorizer=self.authorizer,
                evidence_verifier=self.verifier,
            )

    def test_unregistered_evidence_blocks_phase_before_checkpoint_advances(self):
        self.verifier = lambda ids, context: (False, "fixture-evidence-not-registered")
        engine = self._binding().build_orchestrator()
        engine.create_task(_task("task:host-binding-evidence-deny"))
        state = engine.run_next("task:host-binding-evidence-deny")
        self.assertEqual(state["status"], "BLOCKED")
        self.assertEqual(state["CURRENT_STATE"], "S0")
        self.assertEqual(self.invocations, [])
        self.assertEqual(state["block"]["code"], "ENTRY_EVIDENCE_UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
