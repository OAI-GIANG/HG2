import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from hg_voice.audit import audit_record
from hg_voice.errors import ErrorCode
from hg_voice.manifest import ManifestError, load_manifest, sha256_file, verify_artifact
from hg_voice.registry import list_engines
from hg_voice.cli import main

ROOT = Path(__file__).resolve().parents[1]

class ManifestTests(unittest.TestCase):
    def test_example_manifest_valid(self):
        self.assertEqual(len(load_manifest(ROOT / "models.example.json")["engines"]), 4)
    def test_reject_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "m.json"
            p.write_text(json.dumps({"schema_version": 1, "engines": [{"id":"x","processing":"LOCAL"},{"id":"x","processing":"LOCAL"}]}))
            with self.assertRaises(ManifestError): load_manifest(p)
    def test_reject_unknown_processing(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "m.json"
            p.write_text(json.dumps({"schema_version": 1, "engines": [{"id":"x","processing":"MAGIC"}]}))
            with self.assertRaises(ManifestError): load_manifest(p)
    def test_reject_bad_digest(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "m.json"
            p.write_text(json.dumps({"schema_version": 1, "engines": [{"id":"x","processing":"LOCAL","sha256":"nope"}]}))
            with self.assertRaises(ManifestError): load_manifest(p)
    def test_hash_verification(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "artifact.bin"; p.write_bytes(b"voice-tools-test")
            digest = hashlib.sha256(b"voice-tools-test").hexdigest()
            self.assertEqual(sha256_file(p), digest)
            self.assertTrue(verify_artifact(p, digest))
            self.assertFalse(verify_artifact(p, "0" * 64))
    def test_invalid_expected_digest_rejected(self):
        with self.assertRaises(ManifestError): verify_artifact(Path("missing"), "bad")

class RegistryAndAuditTests(unittest.TestCase):
    def test_registry_is_metadata_only(self):
        self.assertEqual({e.id for e in list_engines()}, {"whisper.cpp", "espeak-ng", "vieneu-nano", "termux-system-tts"})
    def test_audit_redacts_content_by_contract(self):
        out = audit_record("op-1", "whisper.cpp", "complete", 10, 20, 5)
        self.assertNotIn("spoken words", out)
        self.assertIn('"input_bytes":20', out)
    def test_audit_rejects_text_like_identifiers(self):
        with self.assertRaises(ValueError): audit_record("private spoken words", "whisper.cpp", "done", 1, 1, 1)

class CliTests(unittest.TestCase):
    def test_doctor_success(self):
        self.assertEqual(main(["doctor"]), 0)
    def test_engines_success(self):
        self.assertEqual(main(["engines"]), 0)

if __name__ == "__main__": unittest.main()
