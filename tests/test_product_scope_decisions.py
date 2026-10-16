import json
import os
import unittest

from hg.identity import PRODUCT_ID

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACT = os.path.join(ROOT, "contract", "PRODUCT_SCOPE_DECISIONS_V1.json")


class ProductScopeDecisionRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(CONTRACT, encoding="utf-8") as fh:
            cls.record = json.load(fh)

    def test_record_is_scope_only_and_fail_closed(self):
        self.assertEqual(self.record["record_type"], "OWNER_SCOPE_DECISIONS_NOT_IMPLEMENTATION_EVIDENCE")
        self.assertEqual(self.record["decision_status"], "RECORDED")
        self.assertIn("EXTERNAL_IMPACT_AND_PRODUCTION_GATES_BLOCKED", self.record["implementation_status"])
        self.assertEqual(self.record["overall_gate"], "BLOCKED_NO_GO")
        self.assertIn("not implementation or runtime certification", self.record["evidence_rule"])

    def test_explicit_owner_choices_are_recorded(self):
        decisions = {item["id"]: item for item in self.record["decisions"]}
        self.assertEqual(decisions["PSD-API-001"]["choice"], "C")
        self.assertEqual(decisions["PSD-API-001"]["disposition"], "INTENTIONAL_REMOVAL_ALLOWED")
        self.assertEqual(decisions["PSD-BRIDGE-001"]["choice"], "C")
        self.assertEqual(decisions["PSD-BRIDGE-001"]["disposition"], "INTENTIONAL_REMOVAL_ALLOWED")
        self.assertEqual(decisions["PSD-ID-001"]["choice"], "A")
        self.assertEqual(decisions["PSD-ID-001"]["disposition"], "KEEP_PRODUCT_ID_HG_WITH_FORMAL_HG2_MAPPING")

    def test_each_decision_has_acceptance_criteria_and_test_cases(self):
        for decision in self.record["decisions"]:
            with self.subTest(decision=decision["id"]):
                self.assertTrue(decision["acceptance_criteria"])
                self.assertTrue(decision["tests"])
                self.assertTrue(all(item["id"] and item["criterion"] for item in decision["acceptance_criteria"]))
                self.assertTrue(all(item["id"] and item["purpose"] and item["expected"] for item in decision["tests"]))
                self.assertTrue(all(item["status"] == "BLOCKED_NOT_RUN" or item["status"] == "BLOCKED_EXTERNAL_CONSUMERS_UNKNOWN" or item["status"].startswith("PASS_ON_SHA_") for item in decision["tests"]))
                if decision["id"] == "PSD-API-001":
                    self.assertEqual(next(item["status"] for item in decision["tests"] if item["id"] == "T-API-02"), "BLOCKED_EXTERNAL_CONSUMERS_UNKNOWN")
                if decision["id"] == "PSD-BRIDGE-001":
                    self.assertEqual(next(item["status"] for item in decision["tests"] if item["id"] == "T-BRIDGE-02"), "BLOCKED_EXTERNAL_CONSUMERS_UNKNOWN")

    def test_identity_choice_preserves_durable_product_id(self):
        mapping = next(item["mapping"] for item in self.record["decisions"] if item["id"] == "PSD-ID-001")
        self.assertEqual(PRODUCT_ID, "HG")
        self.assertEqual(mapping["product_id"], "HG")
        self.assertEqual(mapping["product_name"], "HG2")
        self.assertTrue(next(item["status"] for item in next(d for d in self.record["decisions"] if d["id"] == "PSD-ID-001")["tests"] if item["id"] == "T-ID-01").startswith("PASS_ON_SHA_"))
        self.assertIn("Never silently rewrite historical product_id values", mapping["rule"])
        with open(os.path.join(ROOT, "manifest.json"), encoding="utf-8") as fh:
            manifest = json.load(fh)
        self.assertEqual(manifest["product_id"], "HG")
        self.assertEqual(manifest["product_name"], "HG2")
        self.assertEqual(manifest["name"], "hg2")
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
            readme = fh.read()
        self.assertIn("HG2 is the product/repository label", readme)
        self.assertIn("`PRODUCT_ID=HG` remains the durable event and on-disk identity", readme)

    def test_acceptance_evidence_is_exact_sha_and_no_go_remains(self):
        evidence = self.record["acceptance_evidence"]
        self.assertEqual(evidence["tested_source_sha"], "46e90fb226e0c434158212a69717025745cad337")
        self.assertEqual(evidence["test_suite_status"], "PASS_ON_SHA_46E90FB")
        evidence_file = __import__("pathlib").Path(ROOT) / "evidence" / "HG2_PRODUCT_SCOPE_ACCEPTANCE_EVIDENCE_46E90FB.json"
        self.assertEqual(self.record["acceptance_evidence"]["evidence_file"], "evidence/HG2_PRODUCT_SCOPE_ACCEPTANCE_EVIDENCE_46E90FB.json")
        self.assertTrue(evidence_file.is_file())
        with evidence_file.open(encoding="utf-8") as fh:
            latest = json.load(fh)
        self.assertEqual(latest["source_commit"], evidence["tested_source_sha"])
        self.assertEqual(latest["test_result"], "OK")
        self.assertEqual(latest["tests_run"], 54)
        self.assertEqual(latest["log"]["sha256"], "1b687aeab6800f6d4f5e772793ccf6b1cad4e08d4e31ec63c10bd7ed40cfc1b6")
        self.assertEqual(self.record["overall_gate"], "BLOCKED_NO_GO")
        self.assertTrue(evidence["remaining_blockers"])

    def test_historical_exception_remains_recorded_without_rewriting(self):
        exceptions = self.record["provenance_exceptions"]
        self.assertEqual(len(exceptions), 1)
        self.assertEqual(exceptions[0]["commit"], "b5f49770cba13cd995533cd140b7560d999c441e")
        self.assertEqual(exceptions[0]["status"], "BLOCKED_REQUIRES_RECONCILIATION")
        self.assertIn("Do not rewrite or remove history", exceptions[0]["handling"])

    def test_global_gates_remain_blocked_and_canonical_is_protected(self):
        self.assertEqual(next(gate["status"] for gate in self.record["global_gates"] if gate["id"] == "G-EXACT-SHA"), "PASS_ON_SHA_46E90FB")
        self.assertNotIn("G-INDEPENDENT-REVIEW", {gate["id"] for gate in self.record["global_gates"]})
        self.assertNotIn("G-PROVENANCE", {gate["id"] for gate in self.record["global_gates"]})
        self.assertEqual(next(gate["status"] for gate in self.record["global_gates"] if gate["id"] == "G-HISTORY-TRACEABILITY"), "PASS_HISTORICAL_RECORD_PRESERVED")
        self.assertEqual(next(gate["status"] for gate in self.record["global_gates"] if gate["id"] == "G-PRODUCTION"), "BLOCKED")
        boundaries = self.record["change_boundaries"]
        self.assertEqual(boundaries["canonical_branch_mutation"], "FORBIDDEN")
        self.assertEqual(boundaries["merge"], "FORBIDDEN")
        self.assertEqual(boundaries["deploy"], "FORBIDDEN")
        self.assertEqual(boundaries["history_rewrite"], "FORBIDDEN")


if __name__ == "__main__":
    unittest.main()
