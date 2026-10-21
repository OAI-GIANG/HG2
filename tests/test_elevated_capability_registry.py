import hashlib
import os
import sys
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
from hg.local_process_rdc_adapter import LocalProcessOperation, PosixLocalRdcAdapter
from hg.maep_host_binding import MaepHostBinding
from hg.process_supervisor import PosixProcessSupervisor
from hg.remote_desktop_commander import RemoteOperation
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
        for action in ELEVATED_ACTIONS - {"file.read", "file.write"}:
            with self.subTest(action=action):
                # Even a principal with the exact scope cannot dispatch an unregistered handler.
                with self.assertRaisesRegex(ElevatedCapabilityError, "ELEVATED_HANDLER_NOT_REGISTERED"):
                    registry.dispatch(action, {})

    def test_file_write_create_only_and_idempotent_retry(self):
        write_root = Path(self.tmp.name) / "writes"
        write_root.mkdir()
        writer = ElevatedCapabilityRegistry(
            principal=BearerAuthenticator(
                "writer-token", {"file.write"}, principal_id="writer"
            ).authenticate("Bearer writer-token"),
            evidence_verifier=self.verifier,
            write_roots=[str(write_root)],
        )
        content = "first immutable payload\n"
        digest = hashlib.sha256(content.encode()).hexdigest()
        payload = {"relative_path": "new.txt", "content_utf8": content, "expected_sha256": digest}
        first = writer.dispatch("file.write", payload)
        self.assertEqual(first["status"], "COMPLETE")
        self.assertTrue(first["created"])
        self.assertEqual((write_root / "new.txt").read_text(), content)
        second = writer.dispatch("file.write", payload)
        self.assertEqual(second["status"], "IDEMPOTENT_NOOP")
        self.assertTrue(second["idempotent"])
        changed = {"relative_path": "new.txt", "content_utf8": "different",
                   "expected_sha256": hashlib.sha256(b"different").hexdigest()}
        with self.assertRaisesRegex(ElevatedCapabilityError, "FILE_WRITE_TARGET_CONFLICT"):
            writer.dispatch("file.write", changed)

    def test_file_write_rejects_traversal_digest_mismatch_and_missing_root(self):
        writer = ElevatedCapabilityRegistry(
            principal=BearerAuthenticator(
                "writer-token", {"file.write"}, principal_id="writer"
            ).authenticate("Bearer writer-token"),
            evidence_verifier=self.verifier,
        )
        content = "payload"
        digest = hashlib.sha256(content.encode()).hexdigest()
        with self.assertRaisesRegex(ElevatedCapabilityError, "FILE_WRITE_ROOTS_NOT_CONFIGURED"):
            writer.dispatch("file.write", {"relative_path": "x", "content_utf8": content,
                                           "expected_sha256": digest})
        root = Path(self.tmp.name) / "writes"
        root.mkdir()
        writer = ElevatedCapabilityRegistry(
            principal=writer.principal, evidence_verifier=self.verifier, write_roots=[str(root)]
        )
        for relative in ("../outside", "/absolute", "nested\\escape"):
            with self.subTest(relative=relative):
                with self.assertRaises(ElevatedCapabilityError):
                    writer.dispatch("file.write", {"relative_path": relative, "content_utf8": content,
                                                   "expected_sha256": digest})
        with self.assertRaisesRegex(ElevatedCapabilityError, "FILE_WRITE_DIGEST_MISMATCH"):
            writer.dispatch("file.write", {"relative_path": "x", "content_utf8": content,
                                           "expected_sha256": "0" * 64})

    def test_file_write_interrupted_temp_write_leaves_no_target_or_temp(self):
        from unittest.mock import patch
        write_root = Path(self.tmp.name) / "writes"
        write_root.mkdir()
        writer = ElevatedCapabilityRegistry(
            principal=BearerAuthenticator(
                "writer-token", {"file.write"}, principal_id="writer"
            ).authenticate("Bearer writer-token"),
            evidence_verifier=self.verifier,
            write_roots=[str(write_root)],
        )
        content = "partially written content"
        payload = {"relative_path": "never-visible.txt", "content_utf8": content,
                   "expected_sha256": hashlib.sha256(content.encode()).hexdigest()}
        def interrupt(fd, data):
            import os
            os.write(fd, data[:4])
            raise OSError("injected interruption")
        with patch.object(writer, "_write_temp_bytes", side_effect=interrupt):
            with self.assertRaisesRegex(ElevatedCapabilityError, "FILE_WRITE_ATOMIC_CREATE_FAILED"):
                writer.dispatch("file.write", payload)
        self.assertFalse((write_root / "never-visible.txt").exists())
        self.assertEqual(list(write_root.iterdir()), [])

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "killpg"), "requires POSIX process-group signaling")
    def test_shell_exec_dispatches_only_fixed_registered_rdc_operation(self):
        adapter_id = "hg.rdc.local.posix"
        operation = RemoteOperation(
            operation_id="device.status",
            required_capabilities=("remote.desktop.status",),
            risk_class="LOCAL_READ_ONLY",
            adapter_id=adapter_id,
            adapter_version="1",
        )
        def argv_builder(arguments):
            if set(arguments) != {"detail"} or arguments["detail"] != "basic":
                raise ValueError("typed arguments rejected")
            return [sys.executable, "-c", "print('registered-rdc-operation-ok')"]
        adapter = PosixLocalRdcAdapter(
            target_id="phone-termux-primary", adapter_id=adapter_id, adapter_version="1",
            operations=(LocalProcessOperation(operation, argv_builder, 2.0),),
            supervisor=PosixProcessSupervisor(termination_grace_seconds=0.05),
        )
        principal = BearerAuthenticator(
            "shell-token", {"shell.exec"}, principal_id="shell-owner"
        ).authenticate("Bearer shell-token")
        registry = ElevatedCapabilityRegistry(principal=principal, evidence_verifier=self.verifier)
        registry.bind_registered_rdc_shell_exec(
            adapter=adapter,
            operation_ids=["device.status"],
            source_revision="a" * 40,
            granted_capabilities_by_operation={"device.status": {"remote.desktop.status"}},
        )
        result = registry.dispatch("shell.exec", {
            "operation_id": "device.status", "command_id": "cmd-rdc-1", "request_id": "req-rdc-1",
            "idempotency_key": "idem-rdc-1", "arguments": {"detail": "basic"}, "approval_ref": None,
        })
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["operation_id"], "device.status")
        self.assertTrue(result["side_effect_performed"])
        self.assertEqual(len(result["output_digest"]), 64)
        with self.assertRaisesRegex(ElevatedCapabilityError, "RDC_OPERATION_NOT_ALLOWLISTED"):
            registry.dispatch("shell.exec", {
                "operation_id": "raw-shell", "command_id": "cmd-rdc-2", "request_id": "req-rdc-2",
                "idempotency_key": "idem-rdc-2", "arguments": {"detail": "basic"}, "approval_ref": None,
            })

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
