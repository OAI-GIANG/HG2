"""Acceptance tests for the allowlist-built product distribution."""
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
    def test_archive_contains_only_manifest_modules_and_excludes_legacy_v1(self):
        with tempfile.TemporaryDirectory(prefix="hg2-dist-test-") as td:
            archive_path = Path(td) / "hg2.zip"
            result = build_archive(archive_path)
            self.assertEqual(result["status"], "PASS")
            self.assertTrue(result["legacy_v1_excluded"])
            with zipfile.ZipFile(archive_path) as archive:
                names = set(archive.namelist())
                manifest = json.loads(archive.read("manifest.json"))
                self.assertNotIn("hg/creative_assimilation.py", names)
                self.assertNotIn("hg/v2/creative_assimilation.py", names)
                self.assertIn("hg/phone_runtime.py", names)
                self.assertIn("hg/cti_guards.py", names)  # preserve declared optional module
                self.assertIn("README.md", names)
                self.assertFalse(any(name.startswith(("tests/", "tools/", "docs/", "contract/", "evidence/")) for name in names))
                for module in manifest["modules"] + manifest.get("optional_modules", []):
                    self.assertIn(module.replace(".", "/") + ".py", names)

    def test_distributed_package_cannot_import_legacy_v1_but_runtime_imports(self):
        with tempfile.TemporaryDirectory(prefix="hg2-dist-import-") as td:
            archive_path = Path(td) / "hg2.zip"
            build_archive(archive_path)
            extracted = Path(td) / "package"
            extracted.mkdir()
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(extracted)
            code = "import hg.phone_runtime;\ntry:\n import hg.creative_assimilation\nexcept ModuleNotFoundError:\n print('LEGACY_IMPORT_BLOCKED')\nelse:\n raise SystemExit('legacy import unexpectedly succeeded')"
            proc = subprocess.run([sys.executable, "-B", "-c", code], cwd=td,
                                  env={"PYTHONPATH": str(extracted), "PYTHONDONTWRITEBYTECODE": "1"},
                                  text=True, capture_output=True, check=False)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("LEGACY_IMPORT_BLOCKED", proc.stdout)

    def test_output_inside_checkout_is_rejected(self):
        with self.assertRaises(DistributionError):
            build_archive(ROOT / "should-not-be-created.zip")


if __name__ == "__main__":
    unittest.main()
