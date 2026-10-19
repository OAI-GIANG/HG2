from __future__ import annotations
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path
from hg.native_criteria import (CRITERIA, SCHEMA_VERSION, aggregate_observations,
    criteria_digest, criteria_document, validate_criteria_document)

ROOT = Path(__file__).resolve().parents[1]

class NativeCriteriaTests(unittest.TestCase):
    def test_rubric_is_valid_weighted_and_independent_of_cp0(self):
        doc = criteria_document()
        report = validate_criteria_document(doc)
        self.assertEqual(report["criterion_count"], 16)
        self.assertEqual(report["weights_total"], 100)
        self.assertEqual(doc["historical_cp0_equivalence"], "NOT_CLAIMED")
        self.assertEqual(len({x["id"] for x in CRITERIA}), 16)
        self.assertEqual(len(criteria_digest()), 64)

    def test_document_cannot_claim_historical_equivalence(self):
        doc = criteria_document()
        doc["historical_cp0_equivalence"] = "EQUIVALENT"
        with self.assertRaisesRegex(ValueError, "HISTORICAL_EQUIVALENCE"):
            validate_criteria_document(doc)

    def test_duplicate_criterion_id_fails(self):
        doc = criteria_document()
        doc["criteria"][1]["id"] = doc["criteria"][0]["id"]
        with self.assertRaisesRegex(ValueError, "ID_INVALID"):
            validate_criteria_document(doc)

    def test_weights_must_sum_to_100(self):
        doc = criteria_document()
        doc["criteria"][0]["weight"] += 1
        with self.assertRaisesRegex(ValueError, "WEIGHT_TOTAL"):
            validate_criteria_document(doc)

    def test_empty_observations_block_missing_criteria(self):
        result = aggregate_observations([])
        self.assertEqual(result["evaluation_status"], "BLOCKED")
        self.assertEqual(len(result["missing_or_uncertain_criteria"]), 16)
        self.assertFalse(result["release_authorized"])
        self.assertIsNone(result["observed_weighted_pass_percent"])

    def test_critical_failure_dominates_missing_criteria(self):
        result = aggregate_observations([{"criterion_id":"HNI-12", "status":"FAIL", "evidence_digest":"a"*64, "oracle_version":"oracle.v1"}])
        self.assertEqual(result["evaluation_status"], "FAIL")
        self.assertEqual(result["critical_failures"], ["HNI-12"])
        self.assertEqual(len(result["missing_or_uncertain_criteria"]), 15)

    def test_missing_evidence_cannot_pass(self):
        with self.assertRaisesRegex(ValueError, "PASS_REQUIRES_EVIDENCE"):
            aggregate_observations([{"criterion_id":"HNI-01", "status":"PASS", "evidence_digest":None, "oracle_version":"oracle.v1"}])

    def test_digest_shape_is_checked_but_not_authenticated(self):
        with self.assertRaisesRegex(ValueError, "DIGEST_INVALID"):
            aggregate_observations([{"criterion_id":"HNI-01", "status":"PASS", "evidence_digest":"not-a-digest", "oracle_version":"oracle.v1"}])
        good = aggregate_observations([{"criterion_id":"HNI-01", "status":"PASS", "evidence_digest":"a"*64, "oracle_version":"oracle.v1"}])
        self.assertIn("not authentication", good["trust_note"])

    def test_duplicate_observation_fails(self):
        row = {"criterion_id":"HNI-01", "status":"NOT_RUN", "evidence_digest":None, "oracle_version":"oracle.v1"}
        with self.assertRaisesRegex(ValueError, "UNKNOWN_OR_DUPLICATE"):
            aggregate_observations([row, row])

    def test_no_hidden_na_or_unknown_status(self):
        with self.assertRaisesRegex(ValueError, "STATUS_INVALID"):
            aggregate_observations([{"criterion_id":"HNI-01", "status":"N/A", "evidence_digest":None, "oracle_version":"oracle.v1"}])
        with self.assertRaisesRegex(ValueError, "UNKNOWN_OR_DUPLICATE"):
            aggregate_observations([{"criterion_id":"UNKNOWN", "status":"PASS", "evidence_digest":"a"*64, "oracle_version":"oracle.v1"}])

    def test_complete_pass_never_authorizes_release(self):
        rows = [{"criterion_id":x["id"], "status":"PASS", "evidence_digest":("a" if i % 2 == 0 else "b")*64, "oracle_version":"oracle.v1"} for i,x in enumerate(CRITERIA)]
        result = aggregate_observations(rows)
        self.assertEqual(result["evaluation_status"], "PASS")
        self.assertEqual(result["observed_weighted_pass_percent"], 100.0)
        self.assertFalse(result["release_authorized"])

    def test_cli_emits_valid_rubric(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/hg-native-evaluate"), "--criteria"], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["schema_version"], SCHEMA_VERSION)
        self.assertEqual(validate_criteria_document(data)["criterion_count"], 16)

    def test_existing_historical_fixture_files_are_not_modified_by_design(self):
        package = ROOT / "tests/fixtures/hg-native-intelligence-v2.1"
        self.assertEqual(len(list(package.glob("HNIF2-*.json"))), 26)
        for path in package.glob("HNIF2-*.json"):
            fixture = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(fixture["classification"], "SYNTHETIC_NON_PRODUCTION")
            self.assertEqual(fixture["execution_status"], "NOT_RUN")

if __name__ == "__main__":
    unittest.main()
