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
        self.assertEqual(self.record["implementation_status"], "NOT_PROVEN")
        self.assertEqual(self.record["overall_gate"], "BLOCKED_NO_GO")
        self.assertIn("not implementation/test/review evidence", self.record["evidence_rule"])

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
                self.assertTrue(all(item["status"] in {"BLOCKED_NOT_RUN", "LOCAL_PASS_UNCOMMITTED"} for item in decision["tests"]))
                if decision["id"] != "PSD-ID-001":
                    self.assertTrue(all(item["status"] == "BLOCKED_NOT_RUN" for item in decision["tests"]))

    def test_identity_choice_preserves_durable_product_id(self):
        mapping = next(item["mapping"] for item in self.record["decisions"] if item["id"] == "PSD-ID-001")
        self.assertEqual(PRODUCT_ID, "HG")
        self.assertEqual(mapping["product_id"], "HG")
        self.assertEqual(mapping["product_name"], "HG2")
        self.assertEqual(next(item["status"] for item in next(d for d in self.record["decisions"] if d["id"] == "PSD-ID-001")["tests"] if item["id"] == "T-ID-01"), "LOCAL_PASS_UNCOMMITTED")
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

    def test_global_gates_remain_blocked_and_canonical_is_protected(self):
        self.assertTrue(all(gate["status"] == "BLOCKED" for gate in self.record["global_gates"]))
        boundaries = self.record["change_boundaries"]
        self.assertEqual(boundaries["canonical_branch_mutation"], "FORBIDDEN")
        self.assertEqual(boundaries["merge"], "FORBIDDEN")
        self.assertEqual(boundaries["deploy"], "FORBIDDEN")
        self.assertEqual(boundaries["history_rewrite"], "FORBIDDEN")


if __name__ == "__main__":
    unittest.main()
