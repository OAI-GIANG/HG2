import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from hg.evidence_verifier import EvidenceVerificationError, FilesystemEvidenceVerifier


class FilesystemEvidenceVerifierTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "evidence"
        self.root.mkdir(mode=0o700)
        self.payload = self.root / "result.json"
        self.payload.write_text('{"status":"PASS"}\n', encoding="utf-8")
        self.verifier = FilesystemEvidenceVerifier(
            verifier_id="test-verifier-v1",
            trust_root_digest=hashlib.sha256(b"test-trust-root").hexdigest(),
            allowed_roots=[str(self.root)],
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_source_bytes_are_verified_and_bound_to_verifier_and_root(self):
        expected = hashlib.sha256(self.payload.read_bytes()).hexdigest()
        receipt = self.verifier.verify_reference("evidence:result.json", expected)
        self.assertEqual(receipt["result"], "BYTES_MATCHED")
        self.assertEqual(receipt["verifier_id"], "test-verifier-v1")
        self.assertEqual(receipt["sha256"], expected)
        self.assertFalse(receipt["semantic_truth_verified"])
        self.assertEqual(len(receipt["receipt_digest"]), 64)
        self.assertEqual(
            self.verifier.verify_reference_decision(
                "evidence:" + expected + "/result.json"
            )[0],
            True,
        )

    def test_mismatched_digest_fails_closed(self):
        with self.assertRaisesRegex(EvidenceVerificationError, "EVIDENCE_DIGEST_MISMATCH"):
            self.verifier.verify_reference("evidence:result.json", "0" * 64)

    def test_path_traversal_and_absolute_paths_fail(self):
        for ref in ("evidence:../outside.json", "evidence:/etc/passwd", "path:../result.json"):
            with self.subTest(ref=ref):
                with self.assertRaises(EvidenceVerificationError):
                    self.verifier.verify_reference(ref)

    def test_symlink_is_rejected(self):
        outside = Path(self.tmp.name) / "outside.json"
        outside.write_text("secret", encoding="utf-8")
        link = self.root / "link.json"
        link.symlink_to(outside)
        with self.assertRaises(EvidenceVerificationError):
            self.verifier.verify_reference("evidence:link.json")

    def test_missing_and_ambiguous_references_fail_closed(self):
        with self.assertRaisesRegex(EvidenceVerificationError, "EVIDENCE_REFERENCE_NOT_FOUND"):
            self.verifier.verify_reference("evidence:missing.json")
        other = Path(self.tmp.name) / "second"
        other.mkdir()
        (other / "result.json").write_text('{"status":"PASS"}\n', encoding="utf-8")
        ambiguous = FilesystemEvidenceVerifier(
            verifier_id="multi-root",
            trust_root_digest=hashlib.sha256(b"multi-root").hexdigest(),
            allowed_roots=[str(self.root), str(other)],
        )
        with self.assertRaisesRegex(EvidenceVerificationError, "EVIDENCE_REFERENCE_AMBIGUOUS"):
            ambiguous.verify_reference("evidence:result.json")

    def test_oversized_file_is_rejected(self):
        small = FilesystemEvidenceVerifier(
            verifier_id="small-limit",
            trust_root_digest=hashlib.sha256(b"small-limit").hexdigest(),
            allowed_roots=[str(self.root)],
            max_bytes=4,
        )
        with self.assertRaisesRegex(EvidenceVerificationError, "EVIDENCE_SIZE_LIMIT_EXCEEDED"):
            small.verify_reference("evidence:result.json")

    def test_reference_must_use_supported_scheme(self):
        with self.assertRaisesRegex(EvidenceVerificationError, "EVIDENCE_REFERENCE_SCHEME_UNSUPPORTED"):
            self.verifier.verify_reference("https://example.invalid/result.json")

    def test_trusted_callback_requires_embedded_expected_digest(self):
        self.assertEqual(
            self.verifier.verify_reference_decision("evidence:result.json"),
            (False, "EVIDENCE_REFERENCE_EXPECTED_DIGEST_REQUIRED"),
        )
        expected = hashlib.sha256(self.payload.read_bytes()).hexdigest()
        ok, receipt_ref = self.verifier.verify_reference_decision(
            "evidence:" + expected + "/result.json"
        )
        self.assertTrue(ok)
        self.assertTrue(receipt_ref.startswith("receipt:"))
        bad, reason = self.verifier.verify_reference_decision("evidence:" + "0" * 64 + "/result.json")
        self.assertFalse(bad)
        self.assertEqual(reason, "EVIDENCE_DIGEST_MISMATCH")

    def test_configured_root_symlink_is_rejected(self):
        alias = Path(self.tmp.name) / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(EvidenceVerificationError, "EVIDENCE_ALLOWED_ROOT_SYMLINK_BLOCKED"):
            FilesystemEvidenceVerifier(
                verifier_id="symlink-root",
                trust_root_digest=hashlib.sha256(b"root").hexdigest(),
                allowed_roots=[str(alias)],
            )


if __name__ == "__main__":
    unittest.main()
