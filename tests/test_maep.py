"""Adversarial tests for MAEP stage gates, checkpoint recovery, and closure."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hg.history import StateStore
from hg.maep import MaepError, MaepOrchestrator, PHASE_IDS


def make_task(task_id="task:maep-test"):
    return {
        "task_id": task_id,
        "OBJECTIVE": "Verify the MAEP orchestration lifecycle",
        "SCOPE": {"include": ["HG2"], "exclude": ["external repositories"]},
        "INPUT": {"source": "test fixture"},
        "OUTPUT": {"artifact": "verified task result"},
        "ACCEPTANCE_CRITERIA": [{
            "id": "criterion:core",
            "description": "Required acceptance evidence exists",
            "required": True,
            "verification": "evidence verifier",
        }],
        "EVIDENCE": [{"type": "test", "purpose": "stage gate evidence"}],
        "RISKS": [{"id": "risk:retry", "severity": "HIGH"}],
        "STOP_CONDITION": "Stop on unverified authority or ambiguous side effects",
        "NEXT_ACTION": "Run the next authorized phase",
        "CLOSURE_CONDITIONS": ["all required criteria pass"],
        "REPOSITORY": "OAI-GIANG/HG2",
        "BRANCH": "test/maep",
        "HEAD": "test-head",
        "WORKING_TREE": "clean",
    }


def test_authorizer(action, context):
    return True, "TEST_ONLY_AUTH:" + action


def test_evidence_verifier(ids, context):
    ok = bool(ids) and all(isinstance(item, str) and item.startswith("ev:") for item in ids)
    return ok, "TEST_ONLY_EVIDENCE_VERIFIER"


def all_handlers(*, fail_phase=None, omit_exit=False, criterion_status="PASS"):
    handlers = {}
    calls = []

    def make_prepare(phase_id):
        def prepare(state, context):
            return {"passed": True, "evidence_ids": ["ev:entry:" + phase_id]}
        return prepare

    def make_handler(phase_id):
        def run(state, context):
            calls.append((phase_id, context["idempotency_key"]))
            if phase_id == fail_phase:
                raise RuntimeError("simulated interruption after dispatch")
            result = {
                "status": "COMPLETE",
                "exit_criteria": {
                    "passed": True,
                    "evidence_ids": ["ev:exit:" + phase_id],
                },
                "evidence_ids": ["ev:stage:" + phase_id],
            }
            if omit_exit and phase_id == "S0":
                result.pop("exit_criteria")
            if phase_id == "S12":
                result["criterion_results"] = {
                    "criterion:core": {
                        "status": criterion_status,
                        "evidence_ids": ["ev:criterion:core"],
                    }
                }
            if phase_id == "S13":
                result["closure_checks"] = {
                    "all required criteria pass": {
                        "passed": True,
                        "evidence_ids": ["ev:closure:all-required"],
                    }
                }
            return result
        return run

    for phase_id in PHASE_IDS:
        handlers[phase_id] = {
            "action": "test.action:" + phase_id,
            "prepare": make_prepare(phase_id),
            "run": make_handler(phase_id),
        }
    return handlers, calls


class MaepOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hg-maep-test-")
        self.addCleanup(self.temp.cleanup)
        self.state_dir = str(Path(self.temp.name) / "history")
        self.store = StateStore(self.state_dir)
        self.handlers, self.calls = all_handlers()
        self.engine = MaepOrchestrator(
            self.store, handlers=self.handlers,
            authorizer=test_authorizer,
            evidence_verifier=test_evidence_verifier,
        )

    def test_all_phases_close_only_with_verified_evidence(self):
        self.engine.create_task(make_task())
        state = self.engine.run_until_blocked("task:maep-test")
        self.assertEqual(state["status"], "CLOSED_VERIFIED")
        self.assertEqual(state["CURRENT_STATE"], "S13")
        self.assertEqual(set(state["stage_results"]), set(PHASE_IDS))
        self.assertTrue(self.store.verify()["ok"])
        self.assertEqual(len(self.calls), 14)

    def test_checkpoint_survives_store_reopen(self):
        self.engine.create_task(make_task())
        state = self.engine.run_next("task:maep-test")
        self.assertEqual(state["CURRENT_STATE"], "S1")
        reopened = MaepOrchestrator(
            StateStore(self.state_dir), handlers=self.handlers,
            authorizer=test_authorizer, evidence_verifier=test_evidence_verifier,
        )
        restored = reopened.load_task("task:maep-test")
        self.assertEqual(restored["CURRENT_STATE"], "S1")
        self.assertEqual(restored["revision"], state["revision"])

    def test_entry_gate_failure_prevents_side_effect(self):
        handlers, calls = all_handlers()
        handlers["S0"]["prepare"] = lambda state, context: {
            "passed": False, "evidence_ids": ["ev:entry:S0"]
        }
        engine = MaepOrchestrator(
            self.store, handlers=handlers, authorizer=test_authorizer,
            evidence_verifier=test_evidence_verifier,
        )
        engine.create_task(make_task())
        state = engine.run_next("task:maep-test")
        self.assertEqual(state["status"], "BLOCKED")
        self.assertEqual(state["block"]["code"], "ENTRY_GATE_NOT_PASSED")
        self.assertEqual(calls, [])

    def test_stale_checkpoint_write_fails_closed(self):
        self.engine.create_task(make_task())
        stale = self.engine.load_task("task:maep-test")
        self.engine._save(stale)
        stale["NEXT_ACTION"] = "conflicting stale checkpoint"
        with self.assertRaises(MaepError) as caught:
            self.engine._save(stale)
        self.assertEqual(caught.exception.code, "MAEP_CHECKPOINT_CONFLICT")

    def test_repository_scope_is_fixed_to_hg2(self):
        task = make_task("task:scope-check")
        task["REPOSITORY"] = "OTHER/REPO"
        with self.assertRaises(MaepError) as caught:
            self.engine.create_task(task)
        self.assertEqual(caught.exception.code, "MAEP_SCOPE_VIOLATION")

    def test_missing_handler_fails_closed(self):
        engine = MaepOrchestrator(
            self.store, authorizer=test_authorizer,
            evidence_verifier=test_evidence_verifier,
        )
        engine.create_task(make_task())
        state = engine.run_next("task:maep-test")
        self.assertEqual(state["status"], "BLOCKED")
        self.assertEqual(state["block"]["code"], "STAGE_HANDLER_UNAVAILABLE")
        self.assertEqual(self.calls, [])

    def test_authorization_denial_prevents_action(self):
        engine = MaepOrchestrator(
            self.store, handlers=self.handlers,
            authorizer=lambda action, context: (False, "POLICY_DENIED"),
            evidence_verifier=test_evidence_verifier,
        )
        engine.create_task(make_task())
        state = engine.run_next("task:maep-test")
        self.assertEqual(state["status"], "BLOCKED")
        self.assertEqual(state["block"]["code"], "ACTION_NOT_AUTHORIZED")
        self.assertEqual(self.calls, [])

    def test_handler_exception_is_in_doubt_and_not_retried(self):
        handlers, calls = all_handlers(fail_phase="S0")
        engine = MaepOrchestrator(
            self.store, handlers=handlers, authorizer=test_authorizer,
            evidence_verifier=test_evidence_verifier,
        )
        engine.create_task(make_task())
        first = engine.run_next("task:maep-test")
        second = engine.run_next("task:maep-test")
        self.assertEqual(first["status"], "BLOCKED")
        self.assertEqual(first["stage_results"]["S0"]["status"], "IN_DOUBT")
        self.assertEqual(second["revision"], first["revision"])
        self.assertEqual(len(calls), 1)

    def test_missing_exit_gate_evidence_does_not_advance(self):
        handlers, calls = all_handlers(omit_exit=True)
        engine = MaepOrchestrator(
            self.store, handlers=handlers, authorizer=test_authorizer,
            evidence_verifier=test_evidence_verifier,
        )
        engine.create_task(make_task())
        state = engine.run_next("task:maep-test")
        self.assertEqual(state["status"], "BLOCKED")
        self.assertEqual(state["CURRENT_STATE"], "S0")
        self.assertEqual(state["stage_results"]["S0"]["status"], "IN_DOUBT")
        self.assertEqual(len(calls), 1)

    def test_required_criterion_failure_blocks_closure(self):
        handlers, calls = all_handlers(criterion_status="FAIL")
        engine = MaepOrchestrator(
            self.store, handlers=handlers, authorizer=test_authorizer,
            evidence_verifier=test_evidence_verifier,
        )
        engine.create_task(make_task())
        state = engine.run_until_blocked("task:maep-test")
        self.assertEqual(state["status"], "BLOCKED")
        self.assertEqual(state["CURRENT_STATE"], "S13")
        self.assertNotEqual(state["status"], "CLOSED_VERIFIED")
        self.assertEqual(state["block"]["code"], "CLOSURE_GATE_FAILED")

    def test_interrupted_running_stage_requires_reconciliation(self):
        self.engine.create_task(make_task())
        state = self.engine.load_task("task:maep-test")
        state["stage_results"] = {
            "S0": {"status": "RUNNING", "idempotency_key": "task:maep-test:S0"}
        }
        self.engine._save(state)
        restored = self.engine.run_next("task:maep-test")
        self.assertEqual(restored["status"], "BLOCKED")
        self.assertEqual(restored["block"]["code"], "INTERRUPTED_IN_FLIGHT_REQUIRES_RECONCILIATION")
        self.assertEqual(self.calls, [])

    def test_reconciliation_allows_retry_only_when_not_performed_is_proven(self):
        handlers, calls = all_handlers(fail_phase="S0")
        engine = MaepOrchestrator(
            self.store, handlers=handlers, authorizer=test_authorizer,
            evidence_verifier=test_evidence_verifier,
        )
        engine.create_task(make_task())
        blocked = engine.run_next("task:maep-test")
        self.assertEqual(blocked["status"], "BLOCKED")
        with self.assertRaises(MaepError):
            engine.reconcile_interrupted(
                "task:maep-test", side_effect_state="UNKNOWN",
                reason="not enough evidence", evidence_ids=["ev:reconcile"],
            )
        resumed = engine.reconcile_interrupted(
            "task:maep-test", side_effect_state="NOT_PERFORMED",
            reason="test oracle proves handler was not dispatched",
            evidence_ids=["ev:reconcile"],
        )
        self.assertEqual(resumed["status"], "IN_PROGRESS")
        self.assertNotIn("S0", resumed["stage_results"])

    def test_phone_runtime_reuses_canonical_state_store(self):
        from hg.phone_runtime import PhoneRuntime

        runtime = PhoneRuntime(state_dir=self.state_dir)
        engine = runtime.maep_orchestrator(
            handlers=self.handlers, authorizer=test_authorizer,
            evidence_verifier=test_evidence_verifier,
        )
        self.assertIs(engine.store, runtime.store)
        engine.create_task(make_task("task:phone-runtime"))
        restored = runtime.maep_orchestrator().load_task("task:phone-runtime")
        self.assertEqual(restored["CURRENT_STATE"], "S0")
        self.assertTrue(runtime.health()["integrity"]["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
