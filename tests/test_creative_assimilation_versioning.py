"""Version-boundary tests for immutable HG Creative Assimilation V1."""
import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V1_MANIFEST = ROOT / "evidence/HG-CTI-20261013/SHA256SUMS.txt"
FROZEN_PATHS = (
    "hg/creative_assimilation.py",
    "tests/test_creative_assimilation.py",
    "contract/CREATIVE_ASSIMILATION_V1.md",
)

class CreativeAssimilationVersioningTests(unittest.TestCase):
    def test_v1_frozen_artifact_hashes_match_manifest(self):
        records = {}
        for line in V1_MANIFEST.read_text(encoding="utf-8").splitlines():
            digest, path = line.split("  ", 1)
            records[path] = digest
        for relpath in FROZEN_PATHS:
            with self.subTest(path=relpath):
                actual = hashlib.sha256((ROOT / relpath).read_bytes()).hexdigest()
                self.assertEqual(records[relpath], actual)

    def test_v2_lifecycle_has_no_review_intermediate_state_or_gate(self):
        implementation = (ROOT / "hg/v2/creative_assimilation.py").read_text(encoding="utf-8")
        contract = (ROOT / "contract/CREATIVE_ASSIMILATION_V2.md").read_text(encoding="utf-8")
        tests = (ROOT / "tests/test_creative_assimilation_v2.py").read_text(encoding="utf-8")
        for source in (implementation, contract, tests):
            for retired in ("REVIEW_REQUIRED", "REVIEW_GATE_BLOCKED", "REVIEW_EVIDENCE_REQUIRED", "ready_for_review", "independent review", "independent verification", "independent approval", "reviewer identity"):
                with self.subTest(retired=retired):
                    self.assertNotIn(retired, source)

if __name__ == "__main__":
    unittest.main()
