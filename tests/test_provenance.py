"""Adversarial tests for HG2 provenance identity and evidence linkage."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import hg.history  # make the second required identity module present in this test process
from hg.provenance import (
    ProvenanceError,
    canonical_json,
    loaded_module_identity,
    run_test_command,
    sha256_bytes,
    snapshot_candidate,
    verify_manifest,
    verify_test_run,
)


def make_git_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "HG Provenance Tests"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "tests@example.invalid"], check=True)
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "baseline"], check=True)
    return root


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hg2-provenance-test-")
        self.root = Path(self.temp.name)
        self.repo = make_git_repo(self.root / "repo")
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def save_manifest(self, manifest, name="manifest.json"):
        path = self.evidence / name
        path.write_bytes(canonical_json(manifest))
        return path

    def test_candidate_snapshot_is_deterministic_and_binds_working_tree(self):
        (self.repo / "tracked.txt").write_text("tracked\n", encoding="utf-8")
        (self.repo / "untracked.txt").write_text("untracked\n", encoding="utf-8")
        first = snapshot_candidate(self.repo, repository_identity="fixture/repo")
        second = snapshot_candidate(self.repo, repository_identity="fixture/repo")
        self.assertEqual(first["candidate_id"], second["candidate_id"])
        self.assertEqual(first["manifest_id"], second["manifest_id"])
        self.assertFalse(first["working_tree_clean"])
        paths = {item["path"] for item in first["inventory"]}
        self.assertIn("tracked.txt", paths)
        self.assertIn("untracked.txt", paths)

    def test_manifest_verifies_then_rejects_source_change(self):
        (self.repo / "source.py").write_text("value = 1\n", encoding="utf-8")
        manifest = snapshot_candidate(self.repo, repository_identity="fixture/repo")
        self.assertEqual(verify_manifest(self.repo, manifest)["status"], "PASS")
        (self.repo / "source.py").write_text("value = 2\n", encoding="utf-8")
        with self.assertRaisesRegex(ProvenanceError, "PROV_MISMATCH"):
            verify_manifest(self.repo, manifest)

    def test_manifest_self_binding_detects_tampering(self):
        manifest = snapshot_candidate(self.repo, repository_identity="fixture/repo")
        tampered = dict(manifest)
        tampered["commit_sha"] = "f" * 40
        with self.assertRaisesRegex(ProvenanceError, "PROV_MISMATCH"):
            verify_manifest(self.repo, tampered)

    def test_inventory_digest_mismatch_is_blocked(self):
        manifest = snapshot_candidate(self.repo, repository_identity="fixture/repo")
        tampered = dict(manifest)
        tampered["inventory"] = list(manifest["inventory"]) + [{"path": "ghost", "size": 0,
                                                                "executable": False, "sha256": "0" * 64}]
        with self.assertRaisesRegex(ProvenanceError, "PROV_MISMATCH"):
            verify_manifest(self.repo, tampered)

    def test_generated_cache_is_excluded_with_reason(self):
        cache = self.repo / "__pycache__"
        cache.mkdir()
        (cache / "module.pyc").write_bytes(b"generated")
        manifest = snapshot_candidate(self.repo, repository_identity="fixture/repo")
        self.assertNotIn("__pycache__/module.pyc", {x["path"] for x in manifest["inventory"]})
        self.assertIn({"path": "__pycache__", "reason": "Generated Python bytecode cache, never a source input"},
                      manifest["excluded_entries"])

    def test_candidate_symlink_fails_closed(self):
        target = self.repo / "target.txt"
        target.write_text("target", encoding="utf-8")
        link = self.repo / "alias.txt"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable on this filesystem")
        with self.assertRaisesRegex(ProvenanceError, "PROV_UNVERIFIABLE"):
            snapshot_candidate(self.repo, repository_identity="fixture/repo")

    def test_invalid_json_values_cannot_be_canonicalized(self):
        with self.assertRaisesRegex(ProvenanceError, "PROV_CANONICALIZATION_INVALID"):
            canonical_json({"not_json": float("nan")})

    def test_test_run_binds_candidate_logs_exit_and_artifacts(self):
        manifest = snapshot_candidate(self.repo, repository_identity="fixture/repo")
        manifest_path = self.save_manifest(manifest)
        out = self.evidence / "run-success"
        result = run_test_command(
            self.repo, manifest_path, out,
            [sys.executable, "-c", "print('provenance-ok')"],
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["return_code"], 0)
        self.assertEqual(result["candidate_before_sha256"], result["candidate_after_sha256"])
        raw = (out / "test-run.json").read_bytes()
        run_doc = json.loads(raw)
        self.assertEqual(run_doc["manifest_id"], manifest["manifest_id"])
        self.assertEqual(run_doc["stdout"]["sha256"], sha256_bytes((out / "stdout.log").read_bytes()))
        self.assertEqual(run_doc["stderr"]["sha256"], sha256_bytes((out / "stderr.log").read_bytes()))
        self.assertTrue((out / "test-run.json.sha256").is_file())
        self.assertEqual(run_doc["evidence_scope"], "LOCAL_ONLY")
        verified = verify_test_run(out / "test-run.json", manifest_path=manifest_path)
        self.assertEqual(verified["evidence_integrity_status"], "PASS")
        self.assertEqual(verified["candidate_binding_status"], "PASS")
        self.assertEqual(verified["test_outcome"], "PASS")

    def test_candidate_change_during_test_run_blocks_even_if_command_exits_zero(self):
        manifest = snapshot_candidate(self.repo, repository_identity="fixture/repo")
        manifest_path = self.save_manifest(manifest)
        out = self.evidence / "run-mutates-source"
        result = run_test_command(
            self.repo, manifest_path, out,
            [sys.executable, "-c", "from pathlib import Path; Path('injected.txt').write_text('changed')"],
        )
        self.assertEqual(result["return_code"], 0)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["source_identity_status"], "BLOCKED")
        (self.repo / "injected.txt").unlink()

    def test_artifact_tampering_is_detected_by_saved_run_verifier(self):
        manifest = snapshot_candidate(self.repo, repository_identity="fixture/repo")
        manifest_path = self.save_manifest(manifest)
        out = self.evidence / "run-artifact-tamper"
        run_test_command(self.repo, manifest_path, out,
                         [sys.executable, "-c", "print('immutable-artifact')"])
        with (out / "stderr.log").open("ab") as stream:
            stream.write(b"tamper")
        with self.assertRaisesRegex(ProvenanceError, "PROV_ARTIFACT_HASH_MISMATCH"):
            verify_test_run(out / "test-run.json", manifest_path=manifest_path)

    def test_run_sidecar_tampering_is_detected(self):
        manifest = snapshot_candidate(self.repo, repository_identity="fixture/repo")
        manifest_path = self.save_manifest(manifest)
        out = self.evidence / "run-sidecar-tamper"
        run_test_command(self.repo, manifest_path, out,
                         [sys.executable, "-c", "print('valid')"])
        (out / "test-run.json.sha256").write_text("0" * 64 + "  test-run.json\\n", encoding="ascii")
        with self.assertRaisesRegex(ProvenanceError, "PROV_ARTIFACT_HASH_MISMATCH"):
            verify_test_run(out / "test-run.json", manifest_path=manifest_path)

    def test_failed_command_is_not_reported_as_pass(self):
        manifest = snapshot_candidate(self.repo, repository_identity="fixture/repo")
        manifest_path = self.save_manifest(manifest)
        result = run_test_command(
            self.repo, manifest_path, self.evidence / "run-fails",
            [sys.executable, "-c", "raise SystemExit(7)"],
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["return_code"], 7)

    def test_evidence_output_inside_candidate_is_rejected(self):
        manifest = snapshot_candidate(self.repo, repository_identity="fixture/repo")
        manifest_path = self.save_manifest(manifest)
        with self.assertRaisesRegex(ProvenanceError, "PROV_POLICY_INVALID"):
            run_test_command(
                self.repo, manifest_path, self.repo / "evidence",
                [sys.executable, "-c", "pass"],
            )

    def test_symlink_manifest_is_rejected(self):
        manifest = snapshot_candidate(self.repo, repository_identity="fixture/repo")
        actual = self.save_manifest(manifest, "manifest-actual.json")
        alias = self.evidence / "manifest-alias.json"
        try:
            alias.symlink_to(actual)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable on this filesystem")
        with self.assertRaisesRegex(ProvenanceError, "PROV_UNVERIFIABLE"):
            run_test_command(self.repo, alias, self.evidence / "run-symlink-manifest",
                             [sys.executable, "-c", "pass"])

    def test_symlink_output_path_is_rejected(self):
        manifest = snapshot_candidate(self.repo, repository_identity="fixture/repo")
        manifest_path = self.save_manifest(manifest)
        actual = self.evidence / "actual-output"
        actual.mkdir()
        alias = self.evidence / "output-alias"
        try:
            alias.symlink_to(actual, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable on this filesystem")
        with self.assertRaisesRegex(ProvenanceError, "PROV_UNVERIFIABLE"):
            run_test_command(self.repo, manifest_path, alias,
                             [sys.executable, "-c", "pass"])

    def test_loaded_module_identity_separates_disk_and_loaded_code_hashes(self):
        result = loaded_module_identity(("hg.provenance", "hg.history"))
        self.assertEqual(result["status"], "OBSERVED_UNMATCHED")
        self.assertEqual(result["source_comparison_status"], "NOT_RUN_NO_EXPECTED_CODE_FINGERPRINT")
        self.assertEqual(result["evidence_scope"], "PROCESS_LOCAL_OBSERVATION")
        for module in result["modules"]:
            self.assertRegex(module["disk_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(module["loaded_code_inventory_sha256"], r"^[0-9a-f]{64}$")
        self.assertNotEqual(result["module_identity_sha256"], result["modules"][0]["disk_sha256"])

    def test_phone_runtime_health_reports_loaded_module_identity(self):
        from hg.phone_runtime import PhoneRuntime
        with tempfile.TemporaryDirectory(prefix="hg2-runtime-identity-") as td:
            health = PhoneRuntime(state_dir=str(Path(td) / "state")).health()
        identity = health["runtime_identity"]
        self.assertEqual(identity["status"], "OBSERVED_UNMATCHED")
        self.assertEqual(identity["pid"], os.getpid())
        self.assertEqual(identity["evidence_scope"], "PROCESS_LOCAL_OBSERVATION")
        self.assertFalse(identity["missing_modules"])
        self.assertTrue(all(row["disk_sha256"] for row in identity["modules"]))

    def test_missing_loaded_module_is_blocked_not_guessed(self):
        result = loaded_module_identity(("definitely.not.loaded.hg2.module",))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["missing_modules"], ["definitely.not.loaded.hg2.module"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
