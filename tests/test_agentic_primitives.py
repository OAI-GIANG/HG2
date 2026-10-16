"""Adversarial unit tests for G2-G6 primitives; no runtime adapter is called."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from copy import deepcopy
from pathlib import Path

from hg.task_contract import canonical_json, contract_digest
from tests.test_task_contract import make_contract
from hg.capabilities import CapabilityError, CapabilityRegistry, route_agent
from hg.evidence import (EvidenceError, SQLiteEvidenceStore, evidence_digest,
                         validate_evidence_envelope, verify_claim)
from hg.transactions import TransactionCoordinatorModel, TransactionError
from hg.provenance_memory import (SQLiteProvenanceMemoryStore, assess_memory,
                                  create_memory_record, detect_memory_conflicts, MemoryError)
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

    def test_expired_capability_fails_even_if_verifier_reports_pass(self):
        record = valid_capability()
        record["valid_from"] = "2020-01-01T00:00:00Z"
        record["expires_at"] = "2021-01-01T00:00:00Z"
        reg = CapabilityRegistry([record], trust_verifier=lambda item: (True, "TEST_ONLY_TRUST"))
        result = reg.resolve("local.health", required_version="v1", action="health.read")
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "CAPABILITY_EXPIRED")

    def test_unknown_action_not_accepted_as_capability(self):
        record = valid_capability()
        record["actions"] = ["custom.unlisted.action"]
        with self.assertRaises(CapabilityError) as ctx:
            CapabilityRegistry([record])
        self.assertEqual(ctx.exception.code, "CAPABILITY_ACTION_NOT_ALLOWLISTED")

    def test_invalid_timestamp_rejected(self):
        record = valid_capability()
        record["valid_from"] = "not-a-time"
        with self.assertRaises(CapabilityError) as ctx:
            CapabilityRegistry([record])
        self.assertEqual(ctx.exception.code, "CAPABILITY_SCHEMA_INVALID")

    def test_trusted_adapter_routes_proposal_but_never_enables_execution(self):
        reg = CapabilityRegistry([valid_capability()], trust_verifier=lambda record: (True, "TEST_ONLY_TRUST_DECISION"))
        task = make_contract("route:task")
        task["required_capabilities"] = [{
            "capability_id": "local.health", "contract_version": "v1", "required": True,
        }]
        task["contract_digest"] = contract_digest(task)
        result = route_agent(
            task, available_capability_ids={"local.health"}, capability_registry=reg,
        )
        self.assertEqual(result["routing_state"], "ROUTED")
        self.assertEqual(result["routes"][0]["provider_id"], "provider:phone")
        self.assertFalse(result["executable"])
        self.assertIsNone(result["selected_provider"])

    def test_route_blocked_when_task_requires_auth_and_no_auth_verifier(self):
        task = make_contract("route:auth")
        task["authorization_requirement"]["action"] = "session.create"
        task["authorization_requirement"]["authenticated_actor_required"] = True
        task["contract_digest"] = contract_digest(task)
        result = route_agent(task, available_capability_ids=set(), capability_registry=CapabilityRegistry([]))
        self.assertEqual(result["routing_state"], "BLOCKED")
        self.assertIn("TASK_AUTHORIZATION_VERIFIER_UNAVAILABLE", [r["reason"] for r in result["blocked_requirements"]])
        self.assertFalse(result["executable"])

    def test_router_never_selects_provider(self):
        reg = CapabilityRegistry([valid_capability()])
        task = make_contract("route:task")
        task["required_capabilities"] = [{
            "capability_id": "local.health", "contract_version": "v1", "required": True,
        }]
        task["contract_digest"] = contract_digest(task)
        result = route_agent(
            task, available_capability_ids={"local.health"}, capability_registry=reg,
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

    def test_evidence_envelope_resource_limit_enforced(self):
        e = valid_evidence()
        e["environment"] = {"large": "x" * 300_000}
        with self.assertRaises(EvidenceError) as ctx:
            evidence_digest(e)
        self.assertEqual(ctx.exception.code, "EVIDENCE_RESOURCE_LIMIT")

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

    def test_sqlite_evidence_store_persists_unverified_envelope(self):
        with tempfile.TemporaryDirectory(prefix="hg-evidence-test-") as directory:
            path = str(Path(directory) / "evidence.sqlite3")
            envelope = valid_evidence()
            store = SQLiteEvidenceStore(path)
            result = store.put(envelope)
            self.assertTrue(result["stored"])
            self.assertEqual(result["trust_state"], "UNVERIFIED")
            reopened = SQLiteEvidenceStore(path)
            self.assertEqual(reopened.get("ev:one"), envelope)
            self.assertTrue(reopened.verify_event_chain()["ok"])
            self.assertTrue(reopened.verify_store_integrity()["ok"])

    def test_sqlite_evidence_store_idempotency_and_immutable_id(self):
        with tempfile.TemporaryDirectory(prefix="hg-evidence-test-") as directory:
            store = SQLiteEvidenceStore(str(Path(directory) / "evidence.sqlite3"))
            envelope = valid_evidence()
            self.assertFalse(store.put(envelope)["idempotent"])
            self.assertTrue(store.put(envelope)["idempotent"])
            changed = valid_evidence()
            changed["test_id"] = "G2-DIFFERENT"
            changed["envelope_digest"] = evidence_digest(changed)
            with self.assertRaises(EvidenceError) as ctx:
                store.put(changed)
            self.assertEqual(ctx.exception.code, "EVIDENCE_ID_CONFLICT")

    def test_sqlite_evidence_store_malformed_event_json_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="hg-evidence-test-") as directory:
            path = str(Path(directory) / "evidence.sqlite3")
            store = SQLiteEvidenceStore(path)
            store.put(valid_evidence())
            with closing(sqlite3.connect(path)) as db:
                db.execute("UPDATE hg_evidence_event SET detail_json='not-json' WHERE seq=1")
                db.commit()
            result = store.verify_event_chain()
            self.assertFalse(result["ok"])
            self.assertEqual(result["reason"], "EVIDENCE_EVENT_DETAIL_INVALID")

    def test_sqlite_evidence_store_event_tampering_detected(self):
        with tempfile.TemporaryDirectory(prefix="hg-evidence-test-") as directory:
            path = str(Path(directory) / "evidence.sqlite3")
            store = SQLiteEvidenceStore(path)
            store.put(valid_evidence())
            with closing(sqlite3.connect(path)) as db:
                db.execute("UPDATE hg_evidence_event SET detail_json='{}' WHERE seq=1")
                db.commit()
            result = store.verify_event_chain()
            self.assertFalse(result["ok"])
            self.assertEqual(result["reason"], "EVIDENCE_EVENT_CHAIN_DIGEST_MISMATCH")
            self.assertFalse(store.verify_store_integrity()["ok"])

    def test_sqlite_evidence_store_projection_tampering_detected(self):
        with tempfile.TemporaryDirectory(prefix="hg-evidence-test-") as directory:
            path = str(Path(directory) / "evidence.sqlite3")
            store = SQLiteEvidenceStore(path)
            store.put(valid_evidence())
            with closing(sqlite3.connect(path)) as db:
                db.execute("UPDATE hg_evidence SET source_revision='tampered-revision' WHERE evidence_id='ev:one'")
                db.commit()
            result = store.verify_store_integrity()
            self.assertFalse(result["ok"])
            self.assertEqual(result["reason"], "EVIDENCE_EVENT_PROJECTION_MISMATCH")

    def test_claim_verifier_reads_durable_evidence_store(self):
        with tempfile.TemporaryDirectory(prefix="hg-evidence-test-") as directory:
            store = SQLiteEvidenceStore(str(Path(directory) / "evidence.sqlite3"))
            store.put(valid_evidence())
            result = verify_claim(
                claim_id="claim:sqlite", criterion_id="crit:sqlite", evidence_ids=["ev:one"],
                evidence_store=store, expected_source_revision="85d57d4",
                expected_oracle_id="oracle:g2", expected_oracle_version="v1",
                attestation_verifier=lambda envelope: (True, "TEST_ONLY_DURABLE_ATTESTATION"),
            )
            self.assertEqual(result["status"], "UNVERIFIED")
            self.assertFalse(result["authenticated_provenance"])
            self.assertTrue(result["attestation_adapter_reported_pass"])

    def test_trusted_attestation_adapter_can_verify_consistent_claim(self):
        e = valid_evidence()
        result = verify_claim(
            claim_id="claim:trusted-test", criterion_id="crit:trusted-test", evidence_ids=["ev:one"],
            evidence_store={"ev:one": e}, expected_source_revision="85d57d4",
            expected_oracle_id="oracle:g2", expected_oracle_version="v1",
            attestation_verifier=lambda envelope: (True, "TEST_ONLY_ATTESTATION_DECISION"),
        )
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertFalse(result["authenticated_provenance"])
        self.assertTrue(result["attestation_adapter_reported_pass"])
        self.assertEqual(result["reason"], "ATTESTATION_ADAPTER_NOT_BOUND_TO_TRUST_ROOT")
        self.assertIn("TEST_ONLY_ATTESTATION_DECISION", result["attestation_decision_refs"])

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
    def test_invalid_parent_id_type_returns_normalized_memory_error(self):
        with self.assertRaises(MemoryError) as ctx:
            create_memory_record(
                memory_id="memory:bad-parent", statement="claim", source_ref=None, source_digest=None,
                authority_ref=None, observed_at=None, expires_at=None, parent_memory_ids=[["nested"]],
            )
        self.assertEqual(ctx.exception.code, "MEMORY_SCHEMA_INVALID")

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

    def test_configured_provenance_verifier_can_verify_valid_record(self):
        record = create_memory_record(
            memory_id="memory:verified-test", statement="claim", source_ref="source:1", source_digest="a"*64,
            authority_ref="authority:1", observed_at="2026-10-17T00:00:00Z",
            expires_at="2027-10-17T00:00:00Z", memory_key="deployment-state",
        )
        assessment = assess_memory(record, known_authority_refs={"authority:1"},
                                   provenance_verifier=lambda value: (True, "TEST_ONLY_MEMORY_DECISION"))
        self.assertFalse(assessment["trusted"])
        self.assertEqual(assessment["status"], "UNVERIFIED")
        self.assertTrue(assessment["provenance_adapter_reported_pass"])
        self.assertIn("PROVENANCE_ADAPTER_NOT_BOUND_TO_TRUST_ROOT", assessment["reasons"])

    def test_memory_record_digest_tampering_is_detected(self):
        record = create_memory_record(
            memory_id="memory:3", statement="claim", source_ref="source:1", source_digest="a"*64,
            authority_ref="authority:1", observed_at="2026-10-17T00:00:00Z",
            expires_at="2027-10-17T00:00:00Z", memory_key="deployment-state",
        )
        record["statement"] = "tampered"
        assessment = assess_memory(record, known_authority_refs={"authority:1"})
        self.assertFalse(assessment["trusted"])
        self.assertIn("MEMORY_RECORD_DIGEST_MISMATCH", assessment["reasons"])

    def test_memory_record_conflicts_are_derived_from_created_records(self):
        kwargs = dict(source_ref="source:1", source_digest="a"*64, authority_ref="authority:1",
                      observed_at="2026-10-17T00:00:00Z", expires_at="2027-10-17T00:00:00Z",
                      memory_key="deployment-state")
        a = create_memory_record(memory_id="memory:a", statement="old", **kwargs)
        b = create_memory_record(memory_id="memory:b", statement="new", **kwargs)
        conflicts = detect_memory_conflicts([a, b])
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["status"], "CONFLICT_UNRESOLVED")

    def test_sqlite_memory_store_persists_records_and_event_chain(self):
        with tempfile.TemporaryDirectory(prefix="hg-memory-test-") as directory:
            path = str(Path(directory) / "memory.sqlite3")
            record = create_memory_record(
                memory_id="memory:durable", statement="non-sensitive test fact", source_ref="source:1",
                source_digest="a"*64, authority_ref="authority:1",
                observed_at="2026-10-17T00:00:00Z", expires_at="2027-10-17T00:00:00Z",
                memory_key="test-fact", sensitivity="INTERNAL",
            )
            store = SQLiteProvenanceMemoryStore(path)
            result = store.put(record)
            self.assertTrue(result["stored"])
            reopened = SQLiteProvenanceMemoryStore(path)
            self.assertEqual(reopened.get("memory:durable"), record)
            self.assertTrue(reopened.verify_event_chain()["ok"])
            self.assertTrue(reopened.verify_store_integrity()["ok"])
            self.assertEqual(assess_memory(reopened.get("memory:durable"))["status"], "UNVERIFIED")

    def test_sqlite_memory_store_idempotency_and_conflict_reporting(self):
        with tempfile.TemporaryDirectory(prefix="hg-memory-test-") as directory:
            store = SQLiteProvenanceMemoryStore(str(Path(directory) / "memory.sqlite3"))
            common = dict(source_ref="source:1", source_digest="a"*64, authority_ref="authority:1",
                          observed_at="2026-10-17T00:00:00Z", expires_at="2027-10-17T00:00:00Z",
                          memory_key="deployment-state", sensitivity="INTERNAL")
            first = create_memory_record(memory_id="memory:first", statement="old", **common)
            second = create_memory_record(memory_id="memory:second", statement="new", **common)
            self.assertFalse(store.put(first)["idempotent"])
            self.assertTrue(store.put(first)["idempotent"])
            added = store.put(second)
            self.assertTrue(added["conflict"])
            self.assertEqual(len(store.list_conflicts()), 1)
            self.assertEqual(store.list_conflicts()[0]["status"], "CONFLICT_UNRESOLVED")
            self.assertTrue(store.verify_store_integrity()["ok"])

    def test_sqlite_memory_store_refuses_secret_without_encryption_adapter(self):
        with tempfile.TemporaryDirectory(prefix="hg-memory-test-") as directory:
            store = SQLiteProvenanceMemoryStore(str(Path(directory) / "memory.sqlite3"))
            record = create_memory_record(
                memory_id="memory:secret", statement="classified marker", source_ref="source:1",
                source_digest="a"*64, authority_ref="authority:1",
                observed_at="2026-10-17T00:00:00Z", expires_at="2027-10-17T00:00:00Z",
                memory_key="secret-fact", sensitivity="SECRET",
            )
            with self.assertRaises(MemoryError) as ctx:
                store.put(record)
            self.assertEqual(ctx.exception.code, "MEMORY_SENSITIVITY_BLOCKED")

    def test_sqlite_memory_store_malformed_event_json_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="hg-memory-test-") as directory:
            path = str(Path(directory) / "memory.sqlite3")
            store = SQLiteProvenanceMemoryStore(path)
            record = create_memory_record(
                memory_id="memory:bad-json", statement="fact", source_ref="source:1", source_digest="a"*64,
                authority_ref="authority:1", observed_at="2026-10-17T00:00:00Z",
                expires_at="2027-10-17T00:00:00Z", memory_key="fact", sensitivity="PUBLIC",
            )
            store.put(record)
            with closing(sqlite3.connect(path)) as db:
                db.execute("UPDATE hg_memory_event SET detail_json='not-json' WHERE seq=1")
                db.commit()
            result = store.verify_event_chain()
            self.assertFalse(result["ok"])
            self.assertEqual(result["reason"], "MEMORY_EVENT_DETAIL_INVALID")

    def test_sqlite_memory_store_detects_event_tampering(self):
        with tempfile.TemporaryDirectory(prefix="hg-memory-test-") as directory:
            path = str(Path(directory) / "memory.sqlite3")
            store = SQLiteProvenanceMemoryStore(path)
            record = create_memory_record(
                memory_id="memory:tamper", statement="fact", source_ref="source:1", source_digest="a"*64,
                authority_ref="authority:1", observed_at="2026-10-17T00:00:00Z",
                expires_at="2027-10-17T00:00:00Z", memory_key="fact", sensitivity="PUBLIC",
            )
            store.put(record)
            with closing(sqlite3.connect(path)) as db:
                db.execute("UPDATE hg_memory_event SET detail_json='{}' WHERE seq=1")
                db.commit()
            result = store.verify_event_chain()
            self.assertFalse(result["ok"])
            self.assertEqual(result["reason"], "MEMORY_EVENT_CHAIN_DIGEST_MISMATCH")

    def test_conflicting_values_reported_not_silently_chosen(self):
        records = [
            {"source_ref": "source:1", "memory_key": "deployment-state", "value_digest": "a"*64},
            {"source_ref": "source:1", "memory_key": "deployment-state", "value_digest": "b"*64},
        ]
        result = detect_memory_conflicts(records)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "CONFLICT_UNRESOLVED")


class VerificationBudgetTests(unittest.TestCase):
    def test_c0_cannot_be_removed_from_mandatory_floor(self):
        plan = plan_verification(risk_level="LOW", mandatory_checks=("style",),
                                 optional_checks=(), available_units=10)
        self.assertIn("C0", plan.required_checks)
        self.assertGreaterEqual(plan.mandatory_floor, 2)
        result = evaluate_verification_result(plan=plan, results={"style": "PASS"}, critical_checks=())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "CRITICAL_CHECK_NOT_RUN")

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

    def test_missing_critical_check_cannot_be_treated_as_pass(self):
        plan = plan_verification(risk_level="LOW", mandatory_checks=("style",),
                                 optional_checks=(), available_units=10)
        result = evaluate_verification_result(plan=plan, results={"style": "PASS"})
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "CRITICAL_CHECK_NOT_RUN")

    def test_negative_budget_rejected(self):
        with self.assertRaises(BudgetError):
            plan_verification(risk_level="LOW", mandatory_checks=("C0",),
                              optional_checks=(), available_units=-1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
