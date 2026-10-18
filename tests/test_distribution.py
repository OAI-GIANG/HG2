"""Acceptance tests for the allowlist-built HG2 distribution."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_distribution import DistributionError, build_archive


class DistributionBoundaryTests(unittest.TestCase):
    def test_archive_contains_only_manifest_modules(self):
        with tempfile.TemporaryDirectory(prefix="hg2-dist-test-") as td:
            archive_path = Path(td) / "hg2.zip"
            result = build_archive(archive_path)
            self.assertEqual(result["status"], "PASS")
            self.assertTrue(result["artifact_sha256"])
            with zipfile.ZipFile(archive_path) as archive:
                names = set(archive.namelist())
                manifest = json.loads(archive.read("manifest.json"))
                self.assertIn("README.md", names)
                self.assertIn("manifest.json", names)
                self.assertIn("hg/phone_runtime.py", names)
                self.assertFalse(any(name.startswith(("tests/", "tools/", "docs/", "contract/", "evidence/")) for name in names))
                for module in manifest["modules"] + manifest.get("optional_modules", []):
                    self.assertIn(module.replace(".", "/") + ".py", names)

    def test_archive_is_deterministic(self):
        with tempfile.TemporaryDirectory(prefix="hg2-dist-determinism-") as td:
            first, second = Path(td) / "first.zip", Path(td) / "second.zip"
            a = build_archive(first)
            b = build_archive(second)
            self.assertEqual(a["artifact_sha256"], b["artifact_sha256"])
            self.assertEqual(a["files"], b["files"])

    def test_distributed_package_imports_phone_runtime_without_dev_tools(self):
        with tempfile.TemporaryDirectory(prefix="hg2-dist-import-") as td:
            archive_path = Path(td) / "hg2.zip"
            build_archive(archive_path)
            extracted = Path(td) / "package"
            extracted.mkdir()
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(extracted)
            code = "import hg.phone_runtime; print('RUNTIME_IMPORT_OK')"
            proc = subprocess.run([sys.executable, "-B", "-c", code], cwd=td,
                                  env={"PYTHONPATH": str(extracted), "PYTHONDONTWRITEBYTECODE": "1"},
                                  text=True, capture_output=True, check=False)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("RUNTIME_IMPORT_OK", proc.stdout)
            self.assertFalse((extracted / "tools").exists())

    def test_output_inside_checkout_is_rejected(self):
        with self.assertRaises(DistributionError):
            build_archive(ROOT / "should-not-be-created.zip")

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory(prefix="hg2-dist-existing-") as td:
            output = Path(td) / "existing.zip"
            output.write_bytes(b"preserve-me")
            with self.assertRaises(DistributionError):
                build_archive(output)
            self.assertEqual(output.read_bytes(), b"preserve-me")


if __name__ == "__main__":
    unittest.main()
