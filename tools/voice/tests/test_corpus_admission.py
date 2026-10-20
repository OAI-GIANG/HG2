import unittest
from hg_voice.corpus_admission import validate_admission


class CorpusAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "schema_version": "1", "corpus_id": "test-corpus-v1",
            "source_sha256": "a" * 64, "permitted_purpose": "ASR evaluation",
            "audio_rights": "approved", "transcript_rights": "approved",
            "speaker_consent": "approved", "review_status": "approved",
        }

    def test_complete_declarations_are_admissible_not_legal_proof(self):
        result = validate_admission(self.record)
        self.assertEqual(result["status"], "ADMISSIBLE_DECLARATIONS")
        self.assertFalse(result["rights_independently_verified"])

    def test_unknown_audio_rights_fail_closed(self):
        self.record["audio_rights"] = "unknown"
        result = validate_admission(self.record)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("blocked:audio_rights", result["reasons"])

    def test_missing_transcript_rights_fail_closed(self):
        del self.record["transcript_rights"]
        self.assertEqual(validate_admission(self.record)["status"], "BLOCKED")

    def test_bad_digest_is_rejected(self):
        self.record["source_sha256"] = "not-a-hash"
        self.assertIn("invalid:source_sha256", validate_admission(self.record)["reasons"])

    def test_nonapproved_review_is_blocked(self):
        self.record["review_status"] = "pending"
        self.assertEqual(validate_admission(self.record)["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
