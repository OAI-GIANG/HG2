import hashlib
import tempfile
import unittest
from pathlib import Path

from hg.auth import BearerAuthenticator
from hg.capability_registry import RuntimeCapabilityRegistry
from hg.contracts import BRAIN_WORKER_CONTEXT_V1
from hg.elevated_capability_registry import (
    ELEVATED_ACTIONS, ElevatedCapabilityError, ElevatedCapabilityRegistry,
)
from hg.evidence_verifier import FilesystemEvidenceVerifier
from hg.maep_host_binding import MaepHostBinding
from hg.sqlite_state import SQLiteStateStore
from hg.workflow_store_adapter import CanonicalWorkflowAdapter


class ElevatedCapabilityRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "evidence"
        self.root.mkdir()
        self.fixture = self.root / "fixture.txt"
        self.fixture.write_text("HG2 scoped read integration fixture\n", encoding="utf-8")
        self.digest = hashlib.sha256(self.fixture.read_bytes()).hexdigest()
        self.ref = "evidence:" + self.digest + "/fixture.txt"
        self.verifier = FilesystemEvidenceVerifier(
            verifier_id="hg2-elevated-integration-v1",
            trust_root_digest=hashlib.sha256(b"isolated-fixture-trust-root").hexdigest(),
            allowed_roots=[str(self.root)],
        )
        self.principal = BearerAuthenticator(
            "owner-delegated-token", {"file.read", "audit.append"}, principal_id="owner-delegated"
        ).authenticate("Bearer owner-delegated-token")
        self.registry = ElevatedCapabilityRegistry(principal=self.principal, evidence_verifier=self.verifier)

    def tearDown(self):
        self.tmp.cleanup()

    def test_file_read_dispatch_reads_allowlisted_bytes_and_checks_digest(self):
        result = self.registry.dispatch("file.read", {
            "reference": "evidence:fixture.txt", "expected_sha256": self.digest,
        })
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["content_utf8"], "HG2 scoped read integration fixture\n")
        self.assertEqual(result["sha256"], self.digest)
        self.assertEqual(result["principal_id"], "owner-delegated")
        self.assertFalse(result["semantic_truth_verified"])

    def test_digest_mismatch_and_path_traversal_are_denied(self):
        with self.assertRaisesRegex(ElevatedCapabilityError, "FILE_READ_DIGEST_MISMATCH"):
            self.registry.dispatch("file.read", {"reference": "evidence:fixture.txt", "expected_sha256": "0" * 64})
        with self.assertRaises(ElevatedCapabilityError):
            self.registry.dispatch("file.read", {"reference": "evidence:../outside", "expected_sha256": self.digest})

    def test_every_unimplemented_elevated_action_fails_closed(self):
        all_scopes = BearerAuthenticator(
            "all-scopes-token", set(ELEVATED_ACTIONS) | {"audit.append"}, principal_id="owner-delegated"
        ).authenticate("Bearer all-scopes-token")
        registry = ElevatedCapabilityRegistry(principal=all_scopes, evidence_verifier=self.verifier)
        for action in ELEVATED_ACTIONS - {"file.read"}:
            with self.subTest(action=action):
                # Even a principal with the exact scope cannot dispatch an unregistered handler.
                with self.assertRaisesRegex(ElevatedCapabilityError, "ELEVATED_HANDLER_NOT_REGISTERED"):
                    registry.dispatch(action, {})

    def test_wrong_principal_scope_is_denied_before_handler(self):
        wrong = BearerAuthenticator("read-only-token", {"audit.append"}, principal_id="read-only").authenticate(
            "Bearer read-only-token"
        )
        registry = ElevatedCapabilityRegistry(principal=wrong, evidence_verifier=self.verifier)
        with self.assertRaisesRegex(ElevatedCapabilityError, "ELEVATED_AUTHORIZATION_DENIED"):
            registry.dispatch("file.read", {"reference": "evidence:fixture.txt", "expected_sha256": self.digest})

    def test_existing_runtime_capability_registry_dispatches_real_evidence_read(self):
        source = hashlib.sha256(b"hg2-elevated-runtime-source").hexdigest()
        runtime_registry = RuntimeCapabilityRegistry()
        runtime_registry.register(self.registry.runtime_domain_binding(source_revision=source))
        resolved = runtime_registry.resolve()
        self.assertEqual(resolved["available_capabilities"], {"security_verification": {"evidence.verify"}})
        worker = resolved["workers"]["security_verification"]
        context = {
            "schema_version": BRAIN_WORKER_CONTEXT_V1,
            "request_id": "elevated-runtime-req",
            "correlation_id": "elevated-runtime-corr",
            "source_revision": source,
            "required_capabilities": ["evidence.verify"],
            "elevated_payload": {"reference": "evidence:fixture.txt", "expected_sha256": self.digest},
        }
        result = worker(context)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["source_revision"], source)
        self.assertEqual(len(result["output_digest"]), 64)
        self.assertTrue(result["evidence_refs"][0].startswith("receipt:"))

    def test_real_maep_s0_end_to_end_uses_sqlite_and_filesystem_verifier(self):
        store = SQLiteStateStore(str(Path(self.tmp.name) / "state"), clock=lambda: 100.0)
        try:
            adapter = CanonicalWorkflowAdapter(
                store, principal=self.principal, actor_id="owner-delegated", clock=lambda: 100.0
            )
            binding = MaepHostBinding(
                adapter,
                phase_actions={"S0": "file.read"},
                handler_registry={"file.read": self.registry.maep_handler_registry({"S0": "file.read"})["S0"]},
                action_scopes={"file.read": "file.read"},
                authorizer=self.registry.authorize_maep_action,
                evidence_verifier=self.registry.verify_evidence,
            )
            engine = binding.build_orchestrator()
            task = {
                "task_id": "elevated-read-e2e",
                "OBJECTIVE": "Verify scoped evidence read integration",
                "SCOPE": {"include": ["fixture"], "exclude": ["production"]},
                "INPUT": {"fixture": self.ref},
                "OUTPUT": {"receipt": "sha256"},
                "ACCEPTANCE_CRITERIA": [{"id": "bytes", "description": "Fixture bytes verified",
                                         "required": True, "verification": "filesystem verifier"}],
                "EVIDENCE": [self.ref],
                "RISKS": [{"id": "production", "severity": "HIGH"}],
                "STOP_CONDITION": "Stop on digest mismatch or missing authorization",
                "NEXT_ACTION": "Continue only after read verification",
                "CLOSURE_CONDITIONS": ["fixture bytes match"],
                "REPOSITORY": "OAI-GIANG/HG2", "BRANCH": "isolated-test", "HEAD": "test-head",
                "WORKING_TREE": "isolated fixture only",
            }
            created = engine.create_task(task)
            self.assertEqual(created["CURRENT_STATE"], "S0")
            result = engine.run_next("elevated-read-e2e")
            self.assertEqual(result["CURRENT_STATE"], "S1")
            self.assertEqual(result["status"], "IN_PROGRESS")
            self.assertEqual(result["stage_results"]["S0"]["status"], "COMPLETE")
            self.assertIn("evidence-receipts:", result["stage_results"]["S0"]["evidence_verification_ref"])
            self.assertTrue(adapter.verify_contract()["ok"])
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
