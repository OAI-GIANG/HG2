import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hg.provenance import runtime_manifest, validate_build


class ProvenanceTests(unittest.TestCase):
    def test_manifest_is_deterministic_and_covers_runtime_source(self):
        root = Path(__file__).resolve().parents[1]
        first = runtime_manifest(root)
        second = runtime_manifest(root)
        self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])
        names = {entry["path"] for entry in first["files"]}
        self.assertIn("hg/provenance.py", names)
        self.assertIn("hg/server.py", names)
        self.assertIn("hg/replica.py", names)
        self.assertIn("ui/index.html", names)
        self.assertTrue(all(len(entry["sha256"]) == 64 for entry in first["files"]))

    def test_build_accepts_matching_commit_and_manifest(self):
        root = Path(__file__).resolve().parents[1]
        manifest = runtime_manifest(root)
        with patch.dict(os.environ, {
            "HG_REQUIRE_BUILD_ID": "1",
            "HG_BUILD_COMMIT": "a" * 40,
            "HG_EXPECTED_SOURCE_MANIFEST_SHA256": manifest["manifest_sha256"],
        }, clear=False):
            result = validate_build(root)
        self.assertTrue(result["ok"])
        self.assertEqual(result["git_commit"], "a" * 40)

    def test_build_rejects_missing_or_mismatching_identity(self):
        root = Path(__file__).resolve().parents[1]
        manifest = runtime_manifest(root)
        with patch.dict(os.environ, {
            "HG_REQUIRE_BUILD_ID": "1",
            "HG_BUILD_COMMIT": "unknown",
            "HG_EXPECTED_SOURCE_MANIFEST_SHA256": manifest["manifest_sha256"],
        }, clear=False):
            with self.assertRaisesRegex(RuntimeError, "HG_BUILD_COMMIT"):
                validate_build(root)
        with patch.dict(os.environ, {
            "HG_REQUIRE_BUILD_ID": "1",
            "HG_BUILD_COMMIT": "a" * 40,
            "HG_EXPECTED_SOURCE_MANIFEST_SHA256": "0" * 64,
        }, clear=False):
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                validate_build(root)


if __name__ == "__main__":
    unittest.main()
