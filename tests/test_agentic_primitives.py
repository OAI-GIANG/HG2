"""Adversarial unit tests for G2-G6 primitives; no runtime adapter is called."""
from __future__ import annotations

import hashlib
import unittest
from copy import deepcopy

from hg.task_contract import canonical_json
from hg.capabilities import CapabilityError, CapabilityRegistry, route_agent
from hg.evidence import EvidenceError, evidence_digest, validate_evidence_envelope, verify_claim
from hg.transactions import TransactionCoordinatorModel, TransactionError
from hg.provenance_memory import assess_memory, create_memory_record, detect_memory_conflicts, MemoryError
from hg.verification_budget import (
    BudgetError, evaluate_verification_result, plan_verification,
)


def valid_capability():
    record = {
        "capability_id": "local.health", "contract_version": "v1", "provider_id": "provider:phone",
        "actions": ["health.read"], "effect_class": "READ_ONLY",
        "authority_policy_ref": "policy:HG_AUTHORITY_V1",
        "source_ref": "github://OAI-GIANG/HG2/hg/authority.py@9d83a113",
        "source_digest": "a" * 64,
        "valid_from": "2026-10-01T00:00:00Z", "expires_at": "2027-10-01T00:00:00Z",
        "revocation_ref": "registry:revocations",
    }
    return record


def valid_evidence():
    value = {
        "schema_version": "hg.evidence-envelope.v1",
        "evidence_id": "ev:one", "task_id": "task:one", "test_id": "G2-TEST-1",
        "source_uri": "github://OAI-GIANG/HG2", "source_revision": "85d57d4",
        "source_digest": "a" * 64, "runtime_id": "termux-test", "build_id": "local-build",
        "environment": {"python": "3.14.6", "platform": "Android-aarch64"},
        "execution_id": "exec:one", "oracle_id": "oracle:g2", "oracle_version": "v1",
        "observed_status": "PASS", "started_at": "2026-10-17T10:00:00Z",
        "finished_at": "2026-10-17T10:00:01Z", "exit_code": 0,
        "raw_artifact_uri": "local://test.log", "raw_artifact_digest": "b" * 64,
        "parent_evidence_ids": [], "actor_ref": "actor:test-harness",
        "correlation_id": "corr:one", "causation_id": "cause:one",
        "payload_digest": "c" * 64, "trust_state": "UNVERIFIED",
    }
    value["envelope_digest"] = evidence_digest(value)
    return value


class CapabilityTests(unittest.TestCase):
    def test_shape_valid_but_caller_record_remains_unverified(self):
        reg = CapabilityRegistry([valid_capability()])
        result = reg.resolve("local.health", required_version="v1", action="health.read")
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "CAPABILITY_UNVERIFIED")

    def test_unknown_capability_blocked(self):
        reg = CapabilityRegistry([])
        result = reg.resolve("missing", required_version="v1", action="health.read")
        self.assertEqual(result["reason"], "CAPABILITY_UNAVAILABLE")

    def test_duplicate_capability_rejected(self):
        with self.assertRaises(CapabilityError) as ctx:
            CapabilityRegistry([valid_capability(), valid_capability()])
        self.assertEqual(ctx.exception.code, "CAPABILITY_DUPLICATE_ID")

    def test_bad_source_digest_rejected(self):
        record = valid_capability()
        record["source_digest"] = "not-a-hash"
        with self.assertRaises(CapabilityError) as ctx:
            CapabilityRegistry([record])
        self.assertEqual(ctx.exception.code, "CAPABILITY_SCHEMA_INVALID")

    def test_unknown_action_not_accepted_as_capability(self):
        record = valid_capability()
        record["actions"] = ["custom.unlisted.action"]
        with self.assertRaises(CapabilityError) as ctx:
            CapabilityRegistry([record])
        self.assertEqual(ctx.exception.code, "CAPABILITY_ACTION_NOT_ALLOWLISTED")

    def test_router_never_selects_provider(self):
        reg = CapabilityRegistry([valid_capability()])
        result = route_agent(
            {"task_id": "task:one", "required_capabilities": [
                {"capability_id": "local.health", "contract_version": "v1", "required": True}]},
            available_capability_ids={"local.health"}, capability_registry=reg,
        )
        self.assertFalse(result["executable"])
        self.assertIsNone(result["selected_provider"])
        self.assertEqual(result["routing_state"], "BLOCKED")


class EvidenceTests(unittest.TestCase):
    def test_unverified_envelope_is_structurally_valid_not_trusted(self):
        e = valid_evidence()
        self.assertEqual(validate_evidence_envelope(e)["trust_state"], "UNVERIFIED")
        claim = verify_claim(
            claim_id="claim:one", criterion_id="crit:one", evidence_ids=["ev:one"],
            evidence_store={"ev:one": e}, expected_source_revision="85d57d4",
            expected_oracle_id="oracle:g2", expected_oracle_version="v1",
        )
        self.assertEqual(claim["status"], "UNVERIFIED")
        self.assertFalse(claim["authenticated_provenance"])

    def test_forced_verified_trust_promotion_rejected(self):
        e = valid_evidence()
        e["trust_state"] = "VERIFIED"
        e["envelope_digest"] = evidence_digest(e)
        with self.assertRaises(EvidenceError) as ctx:
            validate_evidence_envelope(e)
        self.assertEqual(ctx.exception.code, "EVIDENCE_TRUST_PROMOTION_FORBIDDEN")

    def test_digest_tampering_rejected(self):
        e = valid_evidence()
        e["observed_status"] = "FAIL"
        with self.assertRaises(EvidenceError) as ctx:
            validate_evidence_envelope(e)
        self.assertEqual(ctx.exception.code, "EVIDENCE_INTEGRITY_FAILED")

    def test_finish_time_compared_as_instants_across_offsets(self):
        e = valid_evidence()
        e["started_at"] = "2026-10-17T10:00:00+02:00"
        e["finished_at"] = "2026-10-17T08:30:00+01:00"
        e["envelope_digest"] = evidence_digest(e)
        with self.assertRaises(EvidenceError) as ctx:
            validate_evidence_envelope(e)
        self.assertEqual(ctx.exception.code, "EVIDENCE_SCHEMA_INVALID")

    def test_source_oracle_mismatch_stays_unverified(self):
        e = valid_evidence()
        result = verify_claim(
            claim_id="claim:two", criterion_id="crit:two", evidence_ids=["ev:one"],
            evidence_store={"ev:one": e}, expected_source_revision="another-sha",
            expected_oracle_id="oracle:other", expected_oracle_version="v2",
        )
        self.assertEqual(result["status"], "UNVERIFIED")


class TransactionModelTests(unittest.TestCase):
    def test_external_effect_execution_blocked_by_default(self):
        tx = TransactionCoordinatorModel()
        record = tx.begin(transaction_id="tx:1", idempotency_key="key:1",
                          contract_digest="a" * 64, plan_digest="b" * 64,
                          step_ids=["step:1"])
        self.assertEqual(record.state, "BLOCKED")
        self.assertEqual(record.reason, "EXECUTION_ADAPTER_UNVERIFIED")

    def test_idempotent_same_identity_returns_one_record(self):
        tx = TransactionCoordinatorModel()
        first = tx.begin(transaction_id="tx:1", idempotency_key="key:1",
                         contract_digest="a" * 64, plan_digest="b" * 64,
                         step_ids=["step:1"], all_steps_declared_pure=True)
        second = tx.begin(transaction_id="tx:other", idempotency_key="key:1",
                          contract_digest="a" * 64, plan_digest="b" * 64,
                          step_ids=["step:1"], all_steps_declared_pure=True)
        self.assertIs(first, second)
        self.assertEqual(len(tx.events()), 1)

    def test_idempotency_key_conflict_rejected(self):
        tx = TransactionCoordinatorModel()
        tx.begin(transaction_id="tx:1", idempotency_key="key:1",
                 contract_digest="a" * 64, plan_digest="b" * 64,
                 step_ids=["step:1"], all_steps_declared_pure=True)
        with self.assertRaises(TransactionError) as ctx:
            tx.begin(transaction_id="tx:2", idempotency_key="key:1",
                     contract_digest="different", plan_digest="b" * 64,
                     step_ids=["step:1"], all_steps_declared_pure=True)
        self.assertEqual(ctx.exception.code, "IDEMPOTENCY_KEY_CONFLICT")

    def test_crash_recovery_remains_in_doubt(self):
        tx = TransactionCoordinatorModel()
        tx.begin(transaction_id="tx:1", idempotency_key="key:1",
                 contract_digest="a" * 64, plan_digest="b" * 64,
                 step_ids=["step:1"], all_steps_declared_pure=True)
        tx.start("key:1")
        record = tx.recover("key:1")
        self.assertEqual(record.state, "IN_DOUBT")
        self.assertEqual(record.reason, "DURABLE_RECOVERY_NOT_IMPLEMENTED")

    def test_commit_requires_evidence_and_authority(self):
        tx = TransactionCoordinatorModel()
        tx.begin(transaction_id="tx:1", idempotency_key="key:1",
                 contract_digest="a" * 64, plan_digest="b" * 64,
                 step_ids=["step:1"], all_steps_declared_pure=True)
        tx.start("key:1")
        tx.record_step("key:1", "step:1", succeeded=True)
        tx.evidence_pending("key:1", ["ev:one"])
        record = tx.commit("key:1", evidence_verified=False, commit_authorized=True)
        self.assertEqual(record.state, "BLOCKED")
        self.assertFalse(any(e["event_type"] == "COMMITTED" for e in tx.events()))


class ProvenanceMemoryTests(unittest.TestCase):
    def test_missing_provenance_remains_unverified(self):
        record = create_memory_record(
            memory_id="memory:1", statement="claim", source_ref=None, source_digest=None,
            authority_ref=None, observed_at=None, expires_at=None,
        )
        assessment = assess_memory(record, known_authority_refs=set())
        self.assertFalse(assessment["trusted"])
        self.assertEqual(assessment["status"], "UNVERIFIED")
        self.assertIn("SOURCE_MISSING", record["blockers"])

    def test_caller_cannot_promote_memory_to_verified(self):
        record = create_memory_record(
            memory_id="memory:2", statement="claim", source_ref="source:1", source_digest="a"*64,
            authority_ref="authority:1", observed_at="2026-10-17T00:00:00Z",
            expires_at="2027-10-17T00:00:00Z", supplied_trust_level="VERIFIED",
        )
        self.assertEqual(record["trust_level"], "UNVERIFIED")
        self.assertFalse(assess_memory(record, known_authority_refs={"authority:1"})["trusted"])

    def test_conflicting_values_reported_not_silently_chosen(self):
        records = [
            {"source_ref": "source:1", "memory_key": "deployment-state", "value_digest": "a"*64},
            {"source_ref": "source:1", "memory_key": "deployment-state", "value_digest": "b"*64},
        ]
        result = detect_memory_conflicts(records)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "CONFLICT_UNRESOLVED")


class VerificationBudgetTests(unittest.TestCase):
    def test_low_budget_cannot_skip_mandatory_checks(self):
        plan = plan_verification(risk_level="CRITICAL", mandatory_checks=("C0", "P0"),
                                 optional_checks=("style",), available_units=1)
        self.assertEqual(plan.state, "BLOCKED")
        result = evaluate_verification_result(plan=plan, results={"C0": "PASS"})
        self.assertEqual(result["status"], "BLOCKED")

    def test_critical_failure_overrides_aggregate_success(self):
        plan = plan_verification(risk_level="LOW", mandatory_checks=("C0",),
                                 optional_checks=("style",), available_units=10)
        result = evaluate_verification_result(plan=plan, results={"C0": "FAIL", "style": "PASS"})
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["reason"], "CRITICAL_CHECK_FAILED")

    def test_budget_degraded_is_not_pass(self):
        plan = plan_verification(risk_level="CRITICAL", mandatory_checks=("C0",),
                                 optional_checks=("style", "integration"), available_units=2)
        result = evaluate_verification_result(plan=plan, results={"C0": "PASS"})
        self.assertNotEqual(result["status"], "PASS")

    def test_negative_budget_rejected(self):
        with self.assertRaises(BudgetError):
            plan_verification(risk_level="LOW", mandatory_checks=("C0",),
                              optional_checks=(), available_units=-1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
