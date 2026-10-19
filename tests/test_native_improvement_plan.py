from __future__ import annotations
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "tests/testdata/hg-native-improvement-plan.v1.json"

class NativeImprovementPlanTests(unittest.TestCase):
    def test_plan_is_explicitly_not_run_and_does_not_claim_cp0(self):
        data = json.loads(PLAN.read_text(encoding="utf-8"))
        self.assertEqual(data["execution_status"], "NOT_RUN")
        self.assertEqual(data["cp0_historical_equivalence"], "NOT_CLAIMED")
        self.assertGreaterEqual(len(data["hypotheses"]), 6)
        self.assertTrue(all(x["baseline"] == "NOT_RUN" and x["candidate"] == "NOT_RUN" for x in data["hypotheses"]))

    def test_experiment_ids_unique_and_targets_exist_in_rubric(self):
        from hg.native_criteria import CRITERIA
        data = json.loads(PLAN.read_text(encoding="utf-8"))
        ids = [x["id"] for x in data["hypotheses"]]
        self.assertEqual(len(ids), len(set(ids)))
        criterion_ids = {x["id"] for x in CRITERIA}
        self.assertTrue(all(x["target"] in criterion_ids for x in data["hypotheses"]))

    def test_controls_prevent_posthoc_claims(self):
        data = json.loads(PLAN.read_text(encoding="utf-8"))
        policy = data["experiment_policy"]
        self.assertTrue(policy["baseline_must_be_pinned"])
        self.assertTrue(policy["dataset_and_oracle_predeclared"])
        self.assertTrue(policy["report_negative_results"])
        self.assertTrue(policy["promotion_requires_separate_authorized_gate"])

if __name__ == "__main__":
    unittest.main()
