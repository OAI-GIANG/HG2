"""Tests for HG's unified harness gates and redacted lifecycle hooks."""
import hashlib
import unittest

from hg.contracts import canonical_digest
from hg.unified_harness import (
    HARNESS_SCHEMA_VERSION, HarnessError, HarnessHook, HookDecision,
    UnifiedHarness,
)

SOURCE = hashlib.sha256(b"hg-unified-harness-source").hexdigest()
PLAN = {
    "schema_version": "HG_BRAIN_PLAN_V1",
    "request_id": "request-1",
    "correlation_id": "correlation-1",
    "source_revision": SOURCE,
    "status": "ROUTABLE",
    "goal_sha256": "0" * 64,
    "constraints_digest": "a" * 64,
    "branches": [
        {"branch_id": "memory_knowledge", "required_capabilities": ["memory.search"]},
        {"branch_id": "research_synthesis", "required_capabilities": ["synthesis.propose"]},
    ],
    "capability_gaps": [],
    "max_steps": 100,
    "deadline_seconds": 60.0,
    "conflict_policy": "INDEPENDENT_OUTPUTS",
}
_PLAN_DIGEST_FIELDS = (
    "request_id", "correlation_id", "source_revision", "goal_sha256",
    "constraints_digest", "branches", "capability_gaps", "max_steps",
    "deadline_seconds", "conflict_policy",
)
PLAN["plan_digest"] = canonical_digest({key: PLAN[key] for key in _PLAN_DIGEST_FIELDS})
REGISTRY = {
    "schema_version": "HG_RUNTIME_CAPABILITY_REGISTRY_V1",
    "source_revision_set_sha256": canonical_digest({"adapter_source_revisions": [SOURCE]}),
    "entries": [
        {"capability_id": "memory.search", "domain_id": "memory_knowledge",
         "ready": True, "lifecycle_state": "TESTED", "source_revision": SOURCE,
         "side_effect_class": "LOCAL_READ_ONLY", "hard_timeout_enforced": True},
        {"capability_id": "synthesis.propose", "domain_id": "research_synthesis",
         "ready": True, "lifecycle_state": "TESTED", "source_revision": SOURCE,
         "side_effect_class": "OUTBOUND_PROVIDER_CALL", "hard_timeout_enforced": False},
    ],
}
REGISTRY["registry_digest"] = canonical_digest({
    key: value for key, value in REGISTRY.items() if key != "registry_digest"
})


def refresh_registry_digest(registry):
    revisions = sorted({
        entry.get("source_revision") for entry in registry["entries"]
        if isinstance(entry.get("source_revision"), str)
    })
    registry["source_revision_set_sha256"] = (
        canonical_digest({"adapter_source_revisions": revisions}) if revisions else "0" * 64
    )
    registry["registry_digest"] = canonical_digest({
        key: value for key, value in registry.items() if key != "registry_digest"
    })
    return registry


def partial_result():
    return {
        "request_id": PLAN["request_id"],
        "correlation_id": PLAN["correlation_id"],
        "source_revision": SOURCE,
        "status": "PARTIAL",
        "plan_digest": PLAN["plan_digest"],
        "invoked_branches": ["memory_knowledge", "research_synthesis"],
        "branch_results": [
            {"branch_id": "memory_knowledge", "status": "SUCCESS",
             "output_digest": "d" * 64, "evidence_refs": ["evidence:sha256:" + "e" * 64]},
            {"branch_id": "research_synthesis", "status": "RESPONSE_ONLY",
             "output_digest": "f" * 64, "error_code": "PROVIDER_RESPONSE_ONLY_NOT_EXECUTION_PROOF"},
        ],
    }


class UnifiedHarnessTests(unittest.TestCase):
    def test_standard_profile_accepts_ready_same_revision_adapters(self):
        receipt = UnifiedHarness().before_dispatch(
            plan=PLAN, registry_snapshot=REGISTRY, source_revision=SOURCE)
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["schema_version"], HARNESS_SCHEMA_VERSION)
        self.assertEqual(receipt["reason_code"], "HARNESS_DISPATCH_ALLOWED")
        self.assertIn("HARNESS_HARD_TIMEOUT_NOT_PROVEN:synthesis.propose", receipt["warnings"])
        self.assertEqual(len(receipt["receipt_digest"]), 64)

    def test_malformed_digest_fields_fail_closed_without_serialization_errors(self):
        registry = {**REGISTRY, "registry_digest": object()}
        receipt = UnifiedHarness().before_dispatch(
            plan=PLAN, registry_snapshot=registry, source_revision=SOURCE)
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["reason_code"], "HARNESS_REGISTRY_DIGEST_INVALID")
        plan = dict(PLAN)
        plan["plan_digest"] = object()
        receipt = UnifiedHarness().before_dispatch(
            plan=plan, registry_snapshot=REGISTRY, source_revision=SOURCE)
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["reason_code"], "HARNESS_PLAN_DIGEST_INVALID")
        self.assertEqual(len(receipt["receipt_digest"]), 64)

    def test_registry_digest_detects_tampered_capability_metadata(self):
        registry = {**REGISTRY, "entries": [dict(x) for x in REGISTRY["entries"]]}
        registry["entries"][0]["side_effect_class"] = "DESTRUCTIVE"
        receipt = UnifiedHarness().before_dispatch(
            plan=PLAN, registry_snapshot=registry, source_revision=SOURCE)
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["reason_code"], "HARNESS_REGISTRY_DIGEST_MISMATCH")

    def test_plan_digest_detects_tampered_route_before_dispatch(self):
        plan = dict(PLAN)
        plan["branches"] = [dict(item) for item in PLAN["branches"]]
        plan["branches"][0]["required_capabilities"] = ["tool.execute"]
        receipt = UnifiedHarness().before_dispatch(
            plan=plan, registry_snapshot=REGISTRY, source_revision=SOURCE)
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["reason_code"], "HARNESS_PLAN_DIGEST_MISMATCH")

    def test_source_revision_mismatch_blocks_before_dispatch(self):
        registry = {**REGISTRY, "entries": [dict(x) for x in REGISTRY["entries"]]}
        registry["entries"][0]["source_revision"] = "a" * 64
        refresh_registry_digest(registry)
        receipt = UnifiedHarness().before_dispatch(
            plan=PLAN, registry_snapshot=registry, source_revision=SOURCE)
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["reason_code"], "HARNESS_CAPABILITY_SOURCE_REVISION_MISMATCH")

    def test_unbound_capability_blocks(self):
        registry = {**REGISTRY, "entries": [REGISTRY["entries"][1]]}
        refresh_registry_digest(registry)
        receipt = UnifiedHarness().before_dispatch(
            plan=PLAN, registry_snapshot=registry, source_revision=SOURCE)
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["reason_code"], "HARNESS_PLANNED_CAPABILITY_UNREGISTERED")

    def test_strict_profile_fails_closed_for_external_call_without_hard_timeout(self):
        receipt = UnifiedHarness("strict").before_dispatch(
            plan=PLAN, registry_snapshot=REGISTRY, source_revision=SOURCE)
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["reason_code"], "HARNESS_STRICT_TIMEOUT_GATE_BLOCKED")

    def test_guard_hook_can_block_and_does_not_receive_prompt(self):
        observed = []
        def guard(context):
            observed.append(dict(context))
            self.assertNotIn("goal", context)
            self.assertNotIn("access_token", context)
            return HookDecision.deny("POLICY_REVIEW_REQUIRED")
        harness = UnifiedHarness(hooks=(
            HarnessHook("deny-before-dispatch", "before_dispatch", "GUARD", guard, priority=1),
        ))
        receipt = harness.before_dispatch(
            plan=PLAN, registry_snapshot=REGISTRY, source_revision=SOURCE)
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["reason_code"], "POLICY_REVIEW_REQUIRED")
        self.assertEqual(len(observed), 1)

    def test_guard_exception_blocks_without_leaking_exception(self):
        def broken(_context):
            raise RuntimeError("must not be serialized")
        harness = UnifiedHarness(hooks=(
            HarnessHook("broken-guard", "before_dispatch", "GUARD", broken),
        ))
        receipt = harness.before_dispatch(
            plan=PLAN, registry_snapshot=REGISTRY, source_revision=SOURCE)
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["reason_code"], "HARNESS_GUARD_EXCEPTION")
        self.assertNotIn("must not be serialized", str(receipt))

    def test_invalid_hook_and_post_execution_guard_are_rejected(self):
        with self.assertRaisesRegex(HarnessError, "HARNESS_POST_EXECUTION_GUARD_FORBIDDEN"):
            UnifiedHarness(hooks=(
                HarnessHook("late-guard", "after_result", "GUARD",
                            lambda _ctx: HookDecision.allow_execution()),
            ))
        with self.assertRaisesRegex(HarnessError, "HARNESS_PROFILE_INVALID"):
            UnifiedHarness("permissive")

    def test_hook_context_is_read_only_and_filters_unrecognized_fields(self):
        captured = []
        def observer(context):
            captured.append(context)
            self.assertNotIn("goal", context)
            self.assertNotIn("raw_path", context)
            with self.assertRaises(TypeError):
                context["status"] = "SUCCESS"
        from hg.unified_harness import HarnessHookRunner
        runner = HarnessHookRunner((
            HarnessHook("audit-observer", "before_dispatch", "OBSERVER", observer),
        ))
        outcome = runner.run("before_dispatch", {
            "request_id": "request-1", "goal": "secret prompt",
            "raw_path": "/private/path", "status": "ROUTABLE",
        })
        self.assertTrue(outcome["ok"])
        self.assertEqual(captured[0]["request_id"], "request-1")
        self.assertEqual(captured[0]["status"], "ROUTABLE")

    def test_partial_response_only_is_preserved_as_partial(self):
        receipt = UnifiedHarness().verify_outcome(
            plan=PLAN, result=partial_result(), source_revision=SOURCE)
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["result_status"], "PARTIAL")
        self.assertEqual(receipt["reason_code"], "HARNESS_OUTCOME_VERIFIED")

    def test_success_cannot_hide_a_partial_branch(self):
        result = partial_result()
        result["status"] = "SUCCESS"
        receipt = UnifiedHarness().verify_outcome(
            plan=PLAN, result=result, source_revision=SOURCE)
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["reason_code"], "HARNESS_SUCCESS_NOT_PROVEN")

    def test_unknown_or_duplicate_branch_result_is_rejected(self):
        result = partial_result()
        result["branch_results"].append(dict(result["branch_results"][0]))
        receipt = UnifiedHarness().verify_outcome(
            plan=PLAN, result=result, source_revision=SOURCE)
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["reason_code"], "HARNESS_BRANCH_RESULT_INVALID")

    def test_in_doubt_must_be_explicitly_represented(self):
        result = partial_result()
        result["status"] = "IN_DOUBT"
        receipt = UnifiedHarness().verify_outcome(
            plan=PLAN, result=result, source_revision=SOURCE)
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["reason_code"], "HARNESS_IN_DOUBT_WITHOUT_UNCERTAIN_BRANCH")

    def test_result_identity_and_plan_digest_are_bound(self):
        result = partial_result()
        result["request_id"] = "other-request"
        receipt = UnifiedHarness().verify_outcome(
            plan=PLAN, result=result, source_revision=SOURCE)
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["reason_code"], "HARNESS_OUTCOME_IDENTITY_MISMATCH")


if __name__ == "__main__":
    unittest.main()
