import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from hg_voice.text_stress import CASES, SCHEMA, create_rows, evaluate


class TextStressTests(unittest.TestCase):
    def test_fixture_has_expected_size_and_unique_ids(self):
        rows = create_rows()
        self.assertEqual(len(rows), len(CASES))
        self.assertEqual(len({row["case_id"] for row in rows}), len(rows))
        self.assertTrue(all(len(row["case_sha256"]) == 64 for row in rows))

    def test_deterministic_generation(self):
        self.assertEqual(create_rows(), create_rows())

    def test_report_is_explicitly_not_asr_acceptance(self):
        report = evaluate(create_rows())
        self.assertEqual(report["schema_version"], SCHEMA)
        self.assertEqual(report["scope"], "synthetic_text_path_only_not_audio_or_asr_quality")
        self.assertEqual(report["status"], "DIAGNOSTIC_ONLY_NOT_ACCEPTANCE")
        self.assertEqual(report["case_count"], len(CASES))
        self.assertIn("tone_mark", report["by_category"])
        self.assertIn("digit_spelling", report["by_category"])
        self.assertGreater(report["overall"]["reference_words"], 0)
        self.assertIsNotNone(report["overall"]["wer"])
        self.assertIsNotNone(report["overall"]["cer"])
        self.assertEqual(report["by_category"]["empty_reference"]["wer"], None)

    def test_write_report_and_jsonl_are_repeatable(self):
        from hg_voice.text_stress import main
        with tempfile.TemporaryDirectory() as temp:
            a = Path(temp) / "a.json"
            b = Path(temp) / "b.json"
            jsonl = Path(temp) / "pairs.jsonl"
            self.assertEqual(main(["--output", str(a), "--jsonl", str(jsonl)]), 0)
            self.assertEqual(main(["--output", str(b)]), 0)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(hashlib.sha256(a.read_bytes()).hexdigest(), hashlib.sha256(b.read_bytes()).hexdigest())
            records = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), len(CASES))
            self.assertTrue(all(set(record) == {"reference", "hypothesis"} for record in records))

    def test_score_aggregation_matches_rows(self):
        rows = create_rows()
        report = evaluate(rows)
        sum_ref_words = sum(v["reference_words"] for v in report["by_category"].values())
        sum_word_errors = sum(v["word_errors"] for v in report["by_category"].values())
        self.assertEqual(report["overall"]["reference_words"], sum_ref_words)
        self.assertEqual(report["overall"]["word_errors"], sum_word_errors)
        self.assertEqual(sum(report["observed_difference_classes"].values()), len(rows))


if __name__ == "__main__":
    unittest.main()
