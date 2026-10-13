import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "hg_cti_v1"


class HGCTIBenchmarkHarnessTests(unittest.TestCase):
    def setUp(self):
        self.cases_bytes = (BENCH / "cases.json").read_bytes()
        self.cases_doc = json.loads(self.cases_bytes)
        self.prereg = json.loads((BENCH / "preregistration.json").read_text(encoding="utf-8"))

    def test_frozen_dataset_hash_matches_preregistration(self):
        self.assertEqual(hashlib.sha256(self.cases_bytes).hexdigest(), self.prereg["dataset_sha256"])

    def test_exactly_40_unique_cases_and_four_checks_each(self):
        cases = self.cases_doc["cases"]
        self.assertEqual(len(cases), 40)
        self.assertEqual(len({case["id"] for case in cases}), 40)
        self.assertTrue(all(len(case["required_checks"]) == 4 for case in cases))

    def test_each_case_has_grounding_reference_and_provenance_type(self):
        for case in self.cases_doc["cases"]:
            with self.subTest(case_id=case["id"]):
                self.assertTrue(case["grounding_refs"])
                self.assertIn(case["case_origin"], {
                    "record-derived", "governance-policy-derived",
                    "design-derived", "protocol-stress-case"
                })

    def test_preregistered_single_call_arms_and_no_independent_review_gate(self):
        arms = self.prereg["arms"]
        conditions = self.prereg["fixed_conditions"]
        self.assertIn("Single-pass", arms["baseline"])
        self.assertIn("One-call", arms["candidate"])
        self.assertEqual(conditions["calls_per_case_per_arm"], 1)
        self.assertEqual(conditions["provider"], "local llama.cpp only; loopback endpoint; no remote provider")
        constraints = " ".join(self.prereg["constraints"]).lower()
        self.assertIn("no signature or independent-review gate", constraints)
        self.assertIn("production writes", constraints)

    def test_runner_refuses_non_loopback_endpoint_and_dataset_change(self):
        runner = (BENCH / "run_benchmark.py").read_text(encoding="utf-8")
        self.assertIn('endpoint.hostname not in {"127.0.0.1", "localhost", "::1"}', runner)
        self.assertIn("cases_sha != EXPECTED_DATASET_SHA256", runner)
        self.assertIn("refusing to overwrite existing evidence directory", runner)

    def test_preregistered_counterexample_and_critical_cases_are_valid_ids(self):
        ids = {c["id"] for c in self.cases_doc["cases"]}
        scoring = self.prereg["scoring"]
        self.assertGreaterEqual(len(scoring["counterexample_case_ids"]), 20)
        self.assertTrue(set(scoring["counterexample_case_ids"]).issubset(ids))
        self.assertTrue(set(scoring["critical_governance_case_ids"]).issubset(ids))


if __name__ == "__main__":
    unittest.main()
