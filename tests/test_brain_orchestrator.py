import hashlib
import unittest

from hg.brain_orchestrator import (
    BRANCH_CAPABILITIES,
    BRANCH_ORDER,
    BrainOrchestrator,
    BrainRoutingError,
    aggregate_results,
)
from hg.contracts import CAPABILITY_RESULT_V1, BRAIN_REQUEST_V1, canonical_digest


SOURCE = "1dca305b4d6e9442e259442486efb5127cc0cb09"


def request(capabilities, **constraint_overrides):
    constraints = {"required_capabilities": list(capabilities)}
    constraints.update(constraint_overrides)
    return {
        "schema_version": BRAIN_REQUEST_V1,
        "request_id": "req-001",
        "correlation_id": "corr-001",
        "goal": "exercise orchestration contract",
        "constraints": constraints,
        "source_revision": SOURCE,
    }


def success(request_context, branch, digest=None):
    output_digest = digest or hashlib.sha256(branch.encode()).hexdigest()
    return {
        "schema_version": CAPABILITY_RESULT_V1,
        "request_id": request_context["request_id"],
        "correlation_id": request_context["correlation_id"],
        "status": "SUCCESS",
        "output_digest": output_digest,
        "error_code": None,
        "evidence_refs": ["evidence:sha256:" + "a" * 64],
        "source_revision": request_context["source_revision"],
    }


class BrainOrchestratorTests(unittest.TestCase):
    def test_manifest_declares_dependency_free_coordinator(self):
        from pathlib import Path
        import json
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / "manifest.json").read_text())
        self.assertIn("hg.brain_orchestrator", manifest["modules"])
        self.assertEqual(manifest["dependencies"], {})

    def setUp(self):
        self.brain = BrainOrchestrator(clock=lambda: 10.0)
        self.called = []
        self.handlers = {}
        self.inventory = {}
        for branch, caps in BRANCH_CAPABILITIES.items():
            self.inventory[branch] = set(caps)
            def handler(ctx, branch=branch):
                self.called.append(branch)
                return success(ctx, branch)
            self.handlers[branch] = handler

    def test_five_domain_route_and_execution(self):
        caps = [c for branch in BRANCH_ORDER for c in sorted(BRANCH_CAPABILITIES[branch])[:1]]
        req = request(caps)
        plan = self.brain.plan(req, available_capabilities=self.inventory, workers=self.handlers)
        self.assertEqual(plan["status"], "ROUTABLE")
        self.assertEqual([x["branch_id"] for x in plan["branches"]], list(BRANCH_ORDER))
        result = self.brain.execute(req, available_capabilities=self.inventory,
                                    workers=self.handlers, evidence_verifier=lambda ref: True)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["invoked_branches"], list(BRANCH_ORDER))
        self.assertEqual(self.called, list(BRANCH_ORDER))
        self.assertEqual(len(result["plan_digest"]), 64)

    def test_missing_capability_blocks_before_any_worker_runs(self):
        req = request(["memory.search", "tool.execute"])
        inventory = {"memory_knowledge": {"memory.search"}}
        result = self.brain.execute(req, available_capabilities=inventory,
                                    workers=self.handlers, evidence_verifier=lambda ref: True)
        self.assertEqual(result["status"], "BLOCKED_CAPABILITY_GAP")
        self.assertEqual(result["branch_results"], [])
        self.assertEqual(result["invoked_branches"], [])
        self.assertEqual(self.called, [])

    def test_missing_adapter_does_not_count_as_capability(self):
        req = request(["memory.search"])
        result = self.brain.execute(req, available_capabilities=self.inventory,
                                    workers={}, evidence_verifier=lambda ref: True)
        self.assertEqual(result["status"], "BLOCKED_CAPABILITY_GAP")
        self.assertEqual(result["invoked_branches"], [])

    def test_result_request_mismatch_fails_closed(self):
        req = request(["memory.search"])
        def mismatched(ctx):
            value = success(ctx, "memory_knowledge")
            value["request_id"] = "forged-request"
            return value
        result = self.brain.execute(req, available_capabilities=self.inventory,
            workers={"memory_knowledge": mismatched},
            evidence_verifier=lambda ref: True)
        self.assertEqual(result["status"], "IN_DOUBT")
        self.assertEqual(result["branch_results"][0]["error_code"],
                         "CAPABILITY_RESULT_REQUEST_ID_MISMATCH")

    def test_unverified_evidence_cannot_return_success(self):
        req = request(["memory.search"])
        result = self.brain.execute(req, available_capabilities=self.inventory,
            workers={"memory_knowledge": self.handlers["memory_knowledge"]},
            evidence_verifier=lambda ref: False)
        self.assertEqual(result["status"], "IN_DOUBT")
        self.assertEqual(result["branch_results"][0]["error_code"],
                         "CAPABILITY_EVIDENCE_REFERENCE_UNVERIFIED")

    def test_worker_exception_is_in_doubt_and_stops_following_branches(self):
        req = request(["memory.search", "research.analyze"])
        calls = []
        def uncertain(ctx):
            calls.append(ctx["branch_id"])
            raise TimeoutError("transport timed out after possible side effect")
        handlers = {"memory_knowledge": uncertain,
                    "research_synthesis": self.handlers["research_synthesis"]}
        result = self.brain.execute(req, available_capabilities=self.inventory,
            workers=handlers, evidence_verifier=lambda ref: True)
        self.assertEqual(result["status"], "IN_DOUBT")
        self.assertEqual(calls, ["memory_knowledge"])
        self.assertEqual(result["invoked_branches"], ["memory_knowledge"])

    def test_conflicting_same_claim_digests_are_inconclusive(self):
        self.assertEqual(aggregate_results(
            [{"branch_id": "a", "status": "SUCCESS", "output_digest": "a" * 64},
             {"branch_id": "b", "status": "SUCCESS", "output_digest": "b" * 64}],
            conflict_policy="REQUIRE_IDENTICAL_DIGEST", expected_branches=["a", "b"]), "INCONCLUSIVE")

    def test_different_outputs_are_allowed_without_agreement_policy(self):
        self.assertEqual(aggregate_results(
            [{"branch_id": "a", "status": "SUCCESS", "output_digest": "a" * 64},
             {"branch_id": "b", "status": "SUCCESS", "output_digest": "b" * 64}],
            conflict_policy="INDEPENDENT_OUTPUTS", expected_branches=["a", "b"]), "SUCCESS")

    def test_partial_result_preserves_partial_status(self):
        self.assertEqual(aggregate_results(
            [{"branch_id": "a", "status": "PARTIAL"}],
            expected_branches=["a"]), "PARTIAL")

    def test_empty_expected_domain_set_is_not_success(self):
        self.assertEqual(aggregate_results([], expected_branches=[]), "INCONCLUSIVE")
        self.assertEqual(aggregate_results([None], expected_branches=["a"]), "INCONCLUSIVE")
        self.assertEqual(aggregate_results(None, expected_branches=["a"]), "INCONCLUSIVE")

    def test_max_steps_budget_blocks_before_dispatch(self):
        req = request(["memory.search", "research.analyze"], max_steps=1)
        result = self.brain.execute(req, available_capabilities=self.inventory,
                                    workers=self.handlers, evidence_verifier=lambda ref: True)
        self.assertEqual(result["status"], "BLOCKED_ROUTE_BUDGET")
        self.assertEqual(self.called, [])

    def test_missing_result_cannot_aggregate_to_success(self):
        self.assertEqual(aggregate_results(
            [{"branch_id": "a", "status": "SUCCESS", "output_digest": "a" * 64}],
            expected_branches=["a", "b"]), "BLOCKED")

    def test_duplicate_or_foreign_branch_result_is_inconclusive(self):
        self.assertEqual(aggregate_results(
            [{"branch_id": "a", "status": "SUCCESS"},
             {"branch_id": "a", "status": "SUCCESS"}],
            expected_branches=["a"]), "INCONCLUSIVE")
        self.assertEqual(aggregate_results(
            [{"branch_id": "foreign", "status": "SUCCESS"}],
            expected_branches=["a"]), "INCONCLUSIVE")

    def test_failure_dominates_other_nonfatal_statuses(self):
        self.assertEqual(aggregate_results(
            [{"branch_id": "a", "status": "BLOCKED"},
             {"branch_id": "b", "status": "FAIL"}],
            expected_branches=["a", "b"]), "FAIL")

    def test_deadline_stops_dispatch_before_next_branch(self):
        clock_value = [0.0]
        brain = BrainOrchestrator(clock=lambda: clock_value[0])
        calls = []
        def first(ctx):
            calls.append(ctx["branch_id"])
            clock_value[0] = 2.0
            return success(ctx, "memory_knowledge")
        def second(ctx):
            calls.append(ctx["branch_id"])
            return success(ctx, "research_synthesis")
        req = request(["memory.search", "research.analyze"], deadline_seconds=1.0)
        result = brain.execute(req, available_capabilities=self.inventory,
            workers={"memory_knowledge": first, "research_synthesis": second},
            evidence_verifier=lambda ref: True)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(calls, ["memory_knowledge"])
        self.assertEqual(result["invoked_branches"], ["memory_knowledge"])

    def test_route_branch_budget_blocks(self):
        req = request(["memory.search", "research.analyze", "task.decompose"],
                      max_branches=2)
        result = self.brain.execute(req, available_capabilities=self.inventory,
                                    workers=self.handlers, evidence_verifier=lambda ref: True)
        self.assertEqual(result["status"], "BLOCKED_ROUTE_BUDGET")
        self.assertEqual(self.called, [])

    def test_unknown_capability_and_unsafe_constraints_rejected(self):
        with self.assertRaisesRegex(BrainRoutingError, "UNKNOWN_CAPABILITY"):
            self.brain.plan(request(["shell.exec"]), available_capabilities=self.inventory,
                            workers=self.handlers)
        with self.assertRaisesRegex(BrainRoutingError, "CAPABILITY_INVENTORY_ESCALATION"):
            self.brain.plan(request(["memory.search"]),
                available_capabilities={"memory_knowledge": {"shell.exec"}},
                workers=self.handlers)
        with self.assertRaisesRegex(BrainRoutingError, "UNKNOWN_ROUTING_CONSTRAINT"):
            self.brain.plan(request(["memory.search"], allow_all=True),
                available_capabilities=self.inventory, workers=self.handlers)

    def test_same_request_identity_with_different_goal_has_different_plan_digest(self):
        req_a = request(["memory.search"])
        req_b = request(["memory.search"])
        req_b["goal"] = "different objective"
        plan_a = self.brain.plan(req_a, available_capabilities=self.inventory, workers=self.handlers)
        plan_b = self.brain.plan(req_b, available_capabilities=self.inventory, workers=self.handlers)
        self.assertNotEqual(plan_a["plan_digest"], plan_b["plan_digest"])
        self.assertNotEqual(plan_a["goal_sha256"], plan_b["goal_sha256"])

    def test_non_sha_source_revision_rejected_before_dispatch(self):
        req = request(["memory.search"])
        req["source_revision"] = "not-a-commit-sha"
        with self.assertRaisesRegex(BrainRoutingError, "SOURCE_REVISION_INVALID"):
            self.brain.plan(req, available_capabilities=self.inventory, workers=self.handlers)
        self.assertEqual(self.called, [])

    def test_no_workers_call_when_source_contract_invalid(self):
        req = request(["memory.search"])
        req["source_revision"] = ""
        result_error = None
        try:
            self.brain.plan(req, available_capabilities=self.inventory, workers=self.handlers)
        except BrainRoutingError as exc:
            result_error = exc.code
        self.assertEqual(result_error, "BRAIN_REQUEST_INVALID")
        self.assertEqual(self.called, [])


if __name__ == "__main__":
    unittest.main()
