import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from hg.runner_receipt import RunnerReceiptError, _canonical, verify_receipt


class SignedSemanticRunnerReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hg2-runner-receipt-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.repo = self.base / "repo"
        self.bundle = self.base / "bundle"
        self.trust = self.base / "trust"
        self.repo.mkdir(mode=0o700)
        self.bundle.mkdir(mode=0o700)
        self.trust.mkdir(mode=0o700)
        self.private = self.base / "runner_ed25519"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "hg2-test-runner",
             "-f", str(self.private)],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
        )
        pub = Path(str(self.private) + ".pub").read_text(encoding="utf-8").split()
        self.signer = "hg2-test-runner"
        self.allowed = self.trust / "allowed_signers"
        self.allowed.write_text(f"{self.signer} {pub[0]} {pub[1]} test-only\n", encoding="utf-8")
        os.chmod(self.allowed, 0o600)
        self.receipt_path = self.bundle / "receipt.json"
        self.signature_path = self.bundle / "receipt.json.sig"
        logs = self.bundle / "logs"
        logs.mkdir(mode=0o700)
        (logs / "stdout.log").write_bytes(b"Ran 1 test in 0.01s\nOK\n")
        (logs / "stderr.log").write_bytes(b"")
        self.environment = {"os": "Android", "architecture": "aarch64", "python": "3.14.6"}
        self.expected = {
            "repository_root": self.repo,
            "expected_repository": "OAI-GIANG/HG2",
            "expected_commit": "a" * 40,
            "expected_tree": "b" * 40,
            "expected_suite_id": "p2-critical-regression-v1",
            "expected_suite_command": ["python3", "-W", "error::ResourceWarning", "-m", "unittest", "discover", "-s", "tests"],
            "expected_suite_sha256": "c" * 64,
            "expected_environment": self.environment,
            "expected_runner_image_digest": hashlib.sha256(b"pinned-runner-image").hexdigest(),
            "expected_trust_root_sha256": hashlib.sha256(self.allowed.read_bytes()).hexdigest(),
            "expected_runner_id": "circleci/hg2/p2-critical-regression",
        }

    @staticmethod
    def log_ref(path):
        raw = path.read_bytes()
        return {"path": "logs/" + path.name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

    def receipt(self, **overrides):
        stdout = self.bundle / "logs" / "stdout.log"
        stderr = self.bundle / "logs" / "stderr.log"
        receipt = {
            "schema_version": "HG2_SEMANTIC_RUNNER_RECEIPT_V1",
            "repository": "OAI-GIANG/HG2",
            "runner": {
                "id": "circleci/hg2/p2-critical-regression",
                "signer": self.signer,
                "image_digest": hashlib.sha256(b"pinned-runner-image").hexdigest(),
            },
            "source": {"commit": "a" * 40, "tree": "b" * 40, "working_tree_clean": True},
            "suite": {
                "id": "p2-critical-regression-v1",
                "command": ["python3", "-W", "error::ResourceWarning", "-m", "unittest", "discover", "-s", "tests"],
                "suite_sha256": "c" * 64,
            },
            "environment": dict(self.environment),
            "execution": {
                "started_at": "2026-10-20T03:00:00Z",
                "finished_at": "2026-10-20T03:00:02Z",
                "exit_code": 0,
                "stdout": self.log_ref(stdout),
                "stderr": self.log_ref(stderr),
                "test_summary": {"total": 1, "failures": 0, "errors": 0},
            },
        }
        for dotted, value in overrides.items():
            target = receipt
            parts = dotted.split(".")
            for name in parts[:-1]:
                target = target[name]
            target[parts[-1]] = value
        return receipt

    def sign(self, receipt):
        self.receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        payload_file = self.bundle / "signed-payload.json"
        payload_file.write_bytes(_canonical(receipt))
        subprocess.run(
            ["ssh-keygen", "-Y", "sign", "-f", str(self.private), "-n", "hg2-runner-receipt",
             str(payload_file)],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
        )
        generated = Path(str(payload_file) + ".sig")
        generated.replace(self.signature_path)

    def verify(self, *, trusted_signers_path=None, **overrides):
        return verify_receipt(
            self.receipt_path, self.signature_path,
            trusted_signers_path or self.allowed,
            **(self.expected | overrides),
        )

    def test_valid_signed_receipt_binds_commit_suite_environment_and_logs(self):
        receipt = self.receipt()
        self.sign(receipt)
        result = self.verify()
        self.assertEqual(result["status"], "VERIFIED")
        self.assertTrue(result["runner_claim_verified"])
        self.assertTrue(result["test_summary_semantically_consistent"])
        self.assertFalse(result["semantic_truth_verified"])
        self.assertEqual(result["commit"], "a" * 40)
        self.assertTrue(result["trust_root_external_to_repository"])

    def test_payload_change_after_signing_is_rejected(self):
        self.sign(self.receipt())
        parsed = json.loads(self.receipt_path.read_text(encoding="utf-8"))
        parsed["execution"]["exit_code"] = 1
        self.receipt_path.write_text(json.dumps(parsed), encoding="utf-8")
        with self.assertRaisesRegex(RunnerReceiptError, "RUNNER_EXIT_CODE_NOT_ZERO"):
            self.verify()
        parsed["execution"]["exit_code"] = 0
        parsed["runner"]["id"] = "attacker-controlled"
        self.receipt_path.write_text(json.dumps(parsed), encoding="utf-8")
        with self.assertRaisesRegex(RunnerReceiptError, "RECEIPT_RUNNER_ID_MISMATCH"):
            self.verify()

    def test_modified_log_is_rejected_before_signature_acceptance(self):
        self.sign(self.receipt())
        (self.bundle / "logs" / "stdout.log").write_bytes(b"forged pass\n")
        with self.assertRaisesRegex(RunnerReceiptError, "RECEIPT_LOG_BINDING_MISMATCH_STDOUT"):
            self.verify()

    def test_receipt_cannot_claim_dirty_source_or_wrong_commit_or_suite(self):
        for overrides, pattern in (
            ({"source.working_tree_clean": False}, "RECEIPT_SOURCE_IDENTITY_OR_CLEANLINESS_INVALID"),
            ({"source.commit": "d" * 40}, "RECEIPT_SOURCE_IDENTITY_OR_CLEANLINESS_INVALID"),
            ({"suite.id": "different-suite"}, "RECEIPT_SUITE_ID_COMMAND_OR_DIGEST_INVALID"),
        ):
            with self.subTest(pattern=pattern):
                receipt = self.receipt(**overrides)
                self.sign(receipt)
                with self.assertRaisesRegex(RunnerReceiptError, pattern):
                    self.verify()

    def test_exit_zero_and_exact_environment_are_mandatory(self):
        receipt = self.receipt(**{"execution.exit_code": 2})
        self.sign(receipt)
        with self.assertRaisesRegex(RunnerReceiptError, "RUNNER_EXIT_CODE_NOT_ZERO"):
            self.verify()
        receipt = self.receipt()
        self.sign(receipt)
        with self.assertRaisesRegex(RunnerReceiptError, "RECEIPT_ENVIRONMENT_MISMATCH"):
            self.verify(expected_environment={"os": "Linux", "architecture": "aarch64", "python": "3.14.6"})

    def test_runner_image_and_external_trust_root_pin_must_match(self):
        receipt = self.receipt()
        self.sign(receipt)
        with self.assertRaisesRegex(RunnerReceiptError, "RECEIPT_RUNNER_IMAGE_MISMATCH"):
            self.verify(expected_runner_image_digest="d" * 64)
        with self.assertRaisesRegex(RunnerReceiptError, "TRUST_ROOT_DIGEST_MISMATCH"):
            self.verify(expected_trust_root_sha256="e" * 64)

    def test_zero_test_run_or_forged_unittest_summary_is_not_accepted(self):
        receipt = self.receipt(**{"execution.test_summary.total": 0})
        self.sign(receipt)
        with self.assertRaisesRegex(RunnerReceiptError, "SEMANTIC_TEST_COUNT_MUST_BE_POSITIVE"):
            self.verify()
        (self.bundle / "logs" / "stdout.log").write_bytes(b"Ran 0 tests in 0.00s\\nOK\\n")
        receipt = self.receipt()
        self.sign(receipt)
        with self.assertRaisesRegex(RunnerReceiptError, "SEMANTIC_UNITTEST_SUMMARY_MISMATCH"):
            self.verify()

    def test_trust_root_must_be_external_and_not_group_or_world_writable(self):
        self.sign(self.receipt())
        inside = self.repo / "allowed_signers"
        inside.write_bytes(self.allowed.read_bytes())
        os.chmod(inside, 0o600)
        with self.assertRaisesRegex(RunnerReceiptError, "TRUST_ROOT_MUST_BE_OUTSIDE_REPOSITORY"):
            self.verify(trusted_signers_path=inside)
        with self.assertRaisesRegex(RunnerReceiptError, "TRUST_ROOT_NOT_PROVISIONED"):
            self.verify(trusted_signers_path=self.trust / "missing")
        os.chmod(self.allowed, 0o622)
        with self.assertRaisesRegex(RunnerReceiptError, "TRUST_ROOT_WRITABLE_BY_GROUP_OR_OTHER"):
            self.verify()

    def test_missing_or_untrusted_signature_fails_closed(self):
        self.signature_path.write_bytes(b"not a valid SSH signature")
        self.receipt_path.write_text(json.dumps(self.receipt()), encoding="utf-8")
        with self.assertRaisesRegex(RunnerReceiptError, "RUNNER_SIGNATURE_INVALID_OR_UNTRUSTED"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
