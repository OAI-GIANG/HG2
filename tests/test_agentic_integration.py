"""Cross-component integration test with test-only trust callbacks.

This validates wiring and fail-closed defaults; callbacks here are synthetic fixtures,
not authenticated production trust roots.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hg.capabilities import CapabilityRegistry, route_agent
from hg.durable_transactions import DurableTransactionStore
from hg.evidence import SQLiteEvidenceStore, evidence_digest, verify_claim
from hg.provenance_memory import SQLiteProvenanceMemoryStore, assess_memory, create_memory_record
from hg.task_compiler import compile_contract
from hg.task_contract import contract_digest
from hg.verification_budget import evaluate_verification_result, plan_verification
from tests.test_agentic_primitives import valid_capability, valid_evidence
from tests.test_task_contract import make_contract


class AgenticPipelineIntegrationTests(unittest.TestCase):
    def test_declaration_to_evidence_pipeline_with_test_only_verifiers(self):
        contract = make_contract("task:integration")
        contract["required_capabilities"] = [{
            "capability_id": "local.health", "contract_version": "v1", "required": True,
        }]
        contract["contract_digest"] = contract_digest(contract)

        plan = compile_contract(contract)
        self.assertEqual(plan["state"], "VALIDATED")
        self.assertFalse(plan["executable"])
        self.assertIn("capability_registry", plan["unresolved_prerequisites"])

        capability_registry = CapabilityRegistry(
            [valid_capability()],
            trust_verifier=lambda record: (True, "TEST_ONLY_CAPABILITY_TRUST"),
        )
        route = route_agent(contract, available_capability_ids={"local.health"},
                            capability_registry=capability_registry)
        self.assertEqual(route["routing_state"], "ROUTED")
        self.assertFalse(route["executable"])
        self.assertIsNone(route["selected_provider"])

        with tempfile.TemporaryDirectory(prefix="hg-agentic-pipeline-") as directory:
            evidence_store = SQLiteEvidenceStore(str(Path(directory) / "evidence.sqlite3"))
            envelope = valid_evidence()
            envelope["task_id"] = contract["task_id"]
            envelope["source_revision"] = "test-revision-1"
            envelope["oracle_id"] = "oracle:g1-contract-schema-v1"
            envelope["oracle_version"] = "v1"
            envelope["envelope_digest"] = evidence_digest(envelope)
            evidence_store.put(envelope)

            claim = verify_claim(
                claim_id="claim:integration",
                criterion_id=contract["acceptance_criteria"][0]["criterion_id"],
                evidence_ids=[envelope["evidence_id"]],
                evidence_store=evidence_store,
                expected_source_revision="test-revision-1",
                expected_oracle_id="oracle:g1-contract-schema-v1",
                expected_oracle_version="v1",
                attestation_verifier=lambda item: (True, "TEST_ONLY_ATTESTATION_DECISION"),
            )
            self.assertEqual(claim["status"], "UNVERIFIED")
            self.assertFalse(claim["authenticated_provenance"])
            self.assertTrue(claim["attestation_adapter_reported_pass"])

            memory_store = SQLiteProvenanceMemoryStore(str(Path(directory) / "memory.sqlite3"))
            memory = create_memory_record(
                memory_id="memory:integration",
                memory_key="task:integration:acceptance",
                statement="Test-only integration claim passed under test adapter.",
                source_ref="test://integration-suite",
                source_digest=plan["plan_digest"],
                authority_ref="authority:test-only",
                observed_at="2026-10-17T10:00:00Z",
                expires_at="2027-10-17T10:00:00Z",
                sensitivity="INTERNAL",
                parent_memory_ids=[envelope["evidence_id"]],
            )
            memory_store.put(memory)
            self.assertEqual(memory_store.get("memory:integration")["trust_level"], "UNVERIFIED")
            self.assertTrue(memory_store.verify_store_integrity()["ok"])
            memory_assessment = assess_memory(
                memory,
                known_authority_refs={"authority:test-only"},
                provenance_verifier=lambda item: (True, "TEST_ONLY_MEMORY_PROVENANCE"),
            )
            self.assertFalse(memory_assessment["trusted"])
            self.assertEqual(memory_assessment["status"], "UNVERIFIED")
            self.assertTrue(memory_assessment["provenance_adapter_reported_pass"])

            tx_store = DurableTransactionStore(
                str(Path(directory) / "transactions.sqlite3"),
                prepare_authorizer=lambda request: (True, "TEST_ONLY_PREPARE_AUTH"),
                evidence_verifier=lambda ids: (ids == [envelope["evidence_id"]] and claim["attestation_adapter_reported_pass"],
                                               "TEST_ONLY_EVIDENCE_VERIFIER_NOT_PRODUCTION_TRUST"),
                commit_authorizer=lambda record: (record["contract_digest"] == contract["contract_digest"],
                                                  "TEST_ONLY_COMMIT_AUTH"),
            )
            tx = tx_store.begin(
                transaction_id="tx:integration",
                idempotency_key="idempotency:integration",
                contract_digest=contract["contract_digest"],
                plan_digest=plan["plan_digest"],
                step_ids=["contract-validated", "evidence-collected"],
            )
            self.assertEqual(tx["state"], "PREPARED")
            tx_store.start("idempotency:integration")
            tx_store.record_step("idempotency:integration", "contract-validated", succeeded=True)
            tx_store.record_step("idempotency:integration", "evidence-collected", succeeded=True)
            tx_store.evidence_pending("idempotency:integration", [envelope["evidence_id"]])
            committed = tx_store.commit("idempotency:integration")
            self.assertEqual(committed["state"], "COMMITTED")
            self.assertTrue(tx_store.verify_event_chain()["ok"])
            self.assertTrue(tx_store.verify_state_integrity()["ok"])
            self.assertFalse(any(e["detail"].get("side_effect_performed") is True
                                 for e in tx_store.events()))

        budget = plan_verification(
            risk_level="HIGH", mandatory_checks=("C0", "P0"),
            optional_checks=("integration",), available_units=10,
        )
        result = evaluate_verification_result(
            plan=budget, results={"C0": "PASS", "P0": "PASS", "integration": "PASS"},
        )
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["executable"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
