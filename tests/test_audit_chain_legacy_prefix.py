import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integration"))
from hg_tool_plane_verifier_contract import verify_audit


class AuditChainLegacyPrefixTests(unittest.TestCase):
    def record(self, data, prev):
        record = dict(data)
        record["prev"] = prev
        record["h"] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
        return record

    def test_legacy_prefix_and_valid_chain_are_distinguished(self):
        legacy = {"tool": "legacy", "ok": True}
        first = self.record({"tool": "new1", "ok": True}, "GENESIS")
        second = self.record({"tool": "new2", "ok": True}, first["h"])
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "audit.jsonl"
            path.write_text("\n".join(json.dumps(x, sort_keys=True) for x in (legacy, first, second)) + "\n")
            result = verify_audit(path)
        self.assertFalse(result["ok"])
        self.assertTrue(result["chain_ok"])
        self.assertEqual(result["legacy_prefix_records"], 1)
        self.assertEqual(result["chained_records"], 2)
        self.assertEqual(result["chain_start_line"], 2)
        self.assertEqual(result["bad"], [])

    def test_corrupt_hash_is_detected(self):
        first = self.record({"tool": "new1", "ok": True}, "GENESIS")
        second = self.record({"tool": "new2", "ok": True}, first["h"])
        second["ok"] = False
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "audit.jsonl"
            path.write_text("\n".join(json.dumps(x, sort_keys=True) for x in (first, second)) + "\n")
            result = verify_audit(path)
        self.assertFalse(result["ok"])
        self.assertFalse(result["chain_ok"])
        self.assertIn("hash mismatch", {x["reason"] for x in result["bad"]})

    def test_broken_previous_hash_is_detected(self):
        first = self.record({"tool": "new1", "ok": True}, "GENESIS")
        second = self.record({"tool": "new2", "ok": True}, "not-the-real-previous-hash")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "audit.jsonl"
            path.write_text("\n".join(json.dumps(x, sort_keys=True) for x in (first, second)) + "\n")
            result = verify_audit(path)
        self.assertFalse(result["ok"])
        self.assertFalse(result["chain_ok"])
        self.assertIn("prev mismatch", {x["reason"] for x in result["bad"]})

    def test_missing_hash_after_chain_start_is_detected(self):
        first = self.record({"tool": "new1", "ok": True}, "GENESIS")
        stray = {"tool": "stray", "ok": True}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "audit.jsonl"
            path.write_text("\n".join(json.dumps(x, sort_keys=True) for x in (first, stray)) + "\n")
            result = verify_audit(path)
        self.assertFalse(result["chain_ok"])
        self.assertIn("missing chain hash after chain start", {x["reason"] for x in result["bad"]})


if __name__ == "__main__":
    unittest.main(verbosity=2)
