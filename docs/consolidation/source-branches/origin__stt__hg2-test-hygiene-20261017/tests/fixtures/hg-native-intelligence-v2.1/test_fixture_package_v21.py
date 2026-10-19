#!/usr/bin/env python3
"""Regression tests for the HNI V2.1 fixture package; does not invoke HG."""
import hashlib, json, math, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPECTED = {f"HNIF2-{i:02}" for i in range(1, 27)}
HNIT = {f"HNIT-{i:03}" for i in range(1, 31)}
XN = {f"XN-{i:02}" for i in range(1, 7)}

def aggregate(findings):
    if any(f.get("criticality") == "C0" and f.get("status") == "FAIL" and f.get("evidenced") for f in findings):
        return "FAIL"
    if any(f.get("status") == "BLOCKED" for f in findings):
        return "BLOCKED"
    if any(f.get("status") == "INCONCLUSIVE" for f in findings):
        return "INCONCLUSIVE"
    if any(f.get("status") == "NOT_RUN" for f in findings):
        return "NOT_RUN"
    if findings and all(f.get("status") == "PASS" for f in findings):
        return "PASS"
    return "INCONCLUSIVE"

class FixturePackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / "manifest.json").read_text())
        cls.fixtures = {}
        for path in ROOT.glob("HNIF2-*.json"):
            data = json.loads(path.read_text())
            cls.fixtures[data["fixture_id"]] = (path, data)

    def test_exact_fixture_inventory(self):
        self.assertEqual(set(self.fixtures), EXPECTED)
        self.assertEqual(len(self.fixtures), 26)
        self.assertEqual(self.manifest["total_fixtures"], 26)

    def test_manifest_maps_every_file_and_oracle_version(self):
        entries = {x["fixture_id"]: x for x in self.manifest["fixtures"]}
        self.assertEqual(set(entries), EXPECTED)
        for fid, (path, fixture) in self.fixtures.items():
            self.assertEqual(entries[fid]["file"], path.name)
            self.assertEqual(entries[fid]["execution_status"], "NOT_RUN")
            self.assertEqual(entries[fid]["oracle_spec_version"], "hni.oracle-spec.v2.1.1")
            self.assertEqual(fixture["oracle_spec_version"], "hni.oracle-spec.v2.1.1")

    def test_execution_never_inferred_from_expected_verdict(self):
        for _, fixture in self.fixtures.values():
            self.assertEqual(fixture["execution_status"], "NOT_RUN")
            self.assertEqual(fixture["result_record"]["observed_status"], "NOT_RUN")
            self.assertEqual(fixture["result_record"]["evidence_refs"], [])
            self.assertNotEqual(fixture["execution_status"], fixture["expected_response_verdict"])

    def test_all_oracles_are_structured(self):
        for fid, (_, fixture) in self.fixtures.items():
            spec = fixture["oracle_spec"]
            self.assertIsInstance(spec["case_data"], dict, fid)
            self.assertGreater(len(spec["predicates"]), 0, fid)
            ids = [p["id"] for p in spec["predicates"]]
            self.assertEqual(len(ids), len(set(ids)), fid)
            for predicate in spec["predicates"]:
                self.assertTrue(predicate.get("path"), fid)
                self.assertTrue(predicate.get("op"), fid)
                self.assertIn("expected", predicate, fid)

    def test_test_matrix_traceability_complete(self):
        links = set()
        for _, fixture in self.fixtures.values():
            links.update(fixture["linked_tests"])
        self.assertTrue(HNIT.issubset(links))
        self.assertTrue(XN.issubset(links))

    def test_creative_score_and_feasibility_gate(self):
        data = self.fixtures["HNIF2-05"][1]["oracle_spec"]["case_data"]
        weights, scores = data["weights"], data["scores"]
        self.assertTrue(math.isclose(sum(weights.values()), 1.0, abs_tol=1e-12))
        self.assertTrue(math.isclose(sum(scores["A"][k] * weights[k] for k in weights), 2.8))
        self.assertTrue(math.isclose(sum(scores["B"][k] * weights[k] for k in weights), 3.8))
        gate = data["eligibility"]["minimum_feasibility"]
        self.assertLess(scores["A"]["feasibility"], gate)
        self.assertGreaterEqual(scores["B"]["feasibility"], gate)

    def test_correction_chain_is_recomputed(self):
        data = self.fixtures["HNIF2-11"][1]["oracle_spec"]["case_data"]
        x = data["corrected"]["X"]
        self.assertEqual(data["corrected"]["C1"], x * 3)
        self.assertEqual(data["corrected"]["C2"], x + 10)

    def test_improvement_metrics_are_descriptive_only(self):
        data = self.fixtures["HNIF2-19"][1]["oracle_spec"]["case_data"]
        baseline = data["baseline"]["errors"] / data["baseline"]["cases"]
        candidate = data["candidate"]["errors"] / data["candidate"]["cases"]
        self.assertAlmostEqual(baseline, 0.10)
        self.assertAlmostEqual(candidate, 0.04)
        self.assertAlmostEqual((baseline - candidate) * 100, 6)
        self.assertAlmostEqual((baseline - candidate) / baseline * 100, 60)
        self.assertFalse(data["causal_claim_permitted"])
        self.assertFalse(data["control_design_present"])

    def test_synthetic_digest_samples(self):
        for fid in ("HNIF2-20", "HNIF2-22"):
            data = self.fixtures[fid][1]["oracle_spec"]["case_data"]
            digest = data.get("digest")
            if digest:
                self.assertEqual(hashlib.sha256(digest["payload"].encode()).hexdigest(), digest["expected"])
            samples = data.get("digest_samples")
            if samples:
                self.assertEqual(hashlib.sha256(samples["matching_payload"].encode()).hexdigest(), samples["matching_sha256"])
                self.assertEqual(hashlib.sha256(samples["mismatch_payload"].encode()).hexdigest(), samples["mismatch_sha256"])

    def test_critical_failure_dominates_missing_results(self):
        cases = [
            ([{"status":"PASS"},{"status":"PASS"}], "PASS"),
            ([{"status":"NOT_RUN"}], "NOT_RUN"),
            ([{"status":"INCONCLUSIVE"}], "INCONCLUSIVE"),
            ([{"status":"BLOCKED"},{"status":"NOT_RUN"}], "BLOCKED"),
            ([{"status":"BLOCKED"},{"status":"FAIL","criticality":"C0","evidenced":True}], "FAIL"),
            ([{"status":"PASS"},{"status":"FAIL","criticality":"C0","evidenced":True}], "FAIL"),
            ([{"status":"FAIL","criticality":"C0","evidenced":False},{"status":"NOT_RUN"}], "NOT_RUN"),
        ]
        for findings, expected in cases:
            self.assertEqual(aggregate(findings), expected)

    def test_n_a_exclusion_stays_blocked_without_evidence(self):
        data = self.fixtures["HNIF2-25"][1]["oracle_spec"]["case_data"]
        self.assertIsNone(data["rationale"])
        self.assertIsNone(data["approver"])
        self.assertIsNone(data["scope"])
        self.assertIsNone(data["evidence"])
        self.assertFalse(data["denominator_accounted"])
        self.assertEqual(data["expected_disposition"], "BLOCKED")

    def test_production_execution_not_claimed(self):
        self.assertEqual(self.manifest["test_execution"], "NOT_RUN")
        self.assertEqual(self.manifest["release_status"], "NOT_RELEASED")
        self.assertFalse(self.manifest["safety"]["real_secrets_included"])
        self.assertFalse(self.manifest["safety"]["production_data_included"])
        self.assertFalse(self.manifest["safety"]["live_mutation"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
