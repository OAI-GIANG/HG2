"""Verify active package scope and the current creative-assimilation lifecycle."""
import json
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
class CreativeAssimilationVersioningTests(unittest.TestCase):
    def test_legacy_v1_is_not_shipped_as_an_optional_module(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("hg.creative_assimilation", manifest.get("modules", []))
        self.assertNotIn("hg.creative_assimilation", manifest.get("optional_modules", []))
    def test_v2_has_no_review_state_or_review_gate(self):
        implementation = (ROOT / "hg/v2/creative_assimilation.py").read_text(encoding="utf-8")
        contract = (ROOT / "contract/CREATIVE_ASSIMILATION_V2.md").read_text(encoding="utf-8")
        for source in (implementation, contract):
            for retired in ("REVIEW_REQUIRED", "REVIEW_GATE_BLOCKED", "REVIEW_EVIDENCE_REQUIRED", "ready_for_review", "reviewer identity"):
                with self.subTest(retired=retired): self.assertNotIn(retired, source)
if __name__ == "__main__": unittest.main()
