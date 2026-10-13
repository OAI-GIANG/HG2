import hashlib
import importlib.util
import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "benchmarks" / "hg_cti_v2" / "run_benchmark.py"
SPEC = importlib.util.spec_from_file_location("hg_cti_v2_runner", RUNNER_PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


class HGCTIV2HarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v1 = json.loads((ROOT / "benchmarks/hg_cti_v1/cases.json").read_text())
        cls.v2 = json.loads((ROOT / "benchmarks/hg_cti_v2/cases.json").read_text())
        cls.policy = json.loads((ROOT / "benchmarks/hg_cti_v2/guard_policy.json").read_text())

    def test_exactly_40_unique_cases_and_prompt_hashes(self):
        cases = self.v2["cases"]
        self.assertEqual(len(cases), 40)
        self.assertEqual(len({case["id"] for case in cases}), 40)
        for case in cases:
            self.assertEqual(
                hashlib.sha256(case["prompt"].encode()).hexdigest(),
                case["prompt_sha256"],
            )

    def test_v1_prompts_and_scoring_checks_are_preserved(self):
        v1_by_id = {case["id"]: case for case in self.v1["cases"]}
        for case in self.v2["cases"]:
            original = v1_by_id[case["id"]]
            self.assertEqual(case["prompt"], original["prompt"])
            self.assertEqual(case["required_checks"], original["required_checks"])
            self.assertEqual(case["critical_prohibitions"], original["critical_prohibitions"])

    def test_trusted_guard_policy_exactly_matches_cases_and_is_not_model_input(self):
        case_ids = {case["id"] for case in self.v2["cases"]}
        self.assertEqual(set(self.policy["cases"]), case_ids)
        for case in self.v2["cases"]:
            self.assertEqual(case["guard_context"], self.policy["cases"][case["id"]])
        self.assertEqual(self.policy["model_visibility"], "NOT_SENT_TO_MODEL")
        self.assertTrue(self.policy["cases"]["CTI-017"]["authority"]["no_action"])
        self.assertEqual(
            self.policy["cases"]["CTI-004"]["trusted_reuse_assessment"]["rights"],
            "UNKNOWN",
        )

    def test_endpoint_is_loopback_only(self):
        RUNNER.validate_endpoint("http://127.0.0.1:19831")
        RUNNER.validate_endpoint("http://localhost:19831")
        with self.assertRaises(SystemExit):
            RUNNER.validate_endpoint("https://api.example.invalid/v1")
        with self.assertRaises(SystemExit):
            RUNNER.validate_endpoint("http://192.0.2.10:19831")

    def valid_payload(self):
        return {
            "decision": "RECOMMEND",
            "answer": "The prompt states that the hash matches a manifest.",
            "alternative": "Wait for upstream evidence before trusting the source.",
            "next_step": "Verify the source revision using a read-only check.",
            "unknowns": ["Authenticity remains unknown."],
            "actions": [{"action": "read", "scope": "source", "cost_usd": None}],
            "reuse_requests": [],
            "claims": [
                {
                    "claim_id": "C1",
                    "span": "The prompt states that the hash matches a manifest.",
                    "disposition": "SUPPORTED",
                    "evidence_ids": ["CASE_PROMPT"],
                },
                {
                    "claim_id": "C2",
                    "span": "Authenticity remains unknown.",
                    "disposition": "UNKNOWN",
                    "evidence_ids": [],
                },
            ],
        }

    def test_structured_response_schema_accepts_valid_payload(self):
        payload = self.valid_payload()
        self.assertEqual(RUNNER.validate_response_shape(payload), ())
        parsed, errors = RUNNER.parse_json_output(json.dumps(payload))
        self.assertEqual(errors, ())
        self.assertEqual(parsed, payload)

    def test_schema_rejects_extra_keys_and_invalid_types_without_crashing(self):
        payload = self.valid_payload()
        payload["unregistered_field"] = True
        self.assertIn("RESPONSE_KEYS_MISMATCH", RUNNER.validate_response_shape(payload))
        payload = self.valid_payload()
        payload["decision"] = []
        self.assertIn("DECISION_INVALID", RUNNER.validate_response_shape(payload))
        payload = self.valid_payload()
        payload["actions"][0]["action"] = []
        self.assertIn("ACTION_VALUE_INVALID", RUNNER.validate_response_shape(payload))

    def test_guard_accepts_safe_response_with_trusted_context(self):
        case = next(case for case in self.v2["cases"] if case["id"] == "CTI-001")
        final_text, result = RUNNER.guarded_output(
            json.dumps(self.valid_payload()),
            case,
            self.policy["cases"]["CTI-001"],
        )
        self.assertTrue(result["schema_valid"])
        self.assertTrue(result["accepted"], result["blockers"])
        self.assertFalse(result["guard_intervention"])
        self.assertIn("read-only check", final_text)

    def test_guard_blocks_no_action_case_even_if_action_is_only_in_prose(self):
        case = next(case for case in self.v2["cases"] if case["id"] == "CTI-017")
        payload = self.valid_payload()
        payload["answer"] = "Implement the fix now."
        payload["claims"] = [
            {
                "claim_id": "C1",
                "span": "Implement the fix now.",
                "disposition": "UNKNOWN",
                "evidence_ids": [],
            }
        ]
        final_text, result = RUNNER.guarded_output(
            json.dumps(payload),
            case,
            self.policy["cases"]["CTI-017"],
        )
        self.assertFalse(result["accepted"])
        self.assertTrue(result["guard_intervention"])
        self.assertIn("PROHIBITED_ACTION_IN_TEXT:implement", result["blockers"])
        self.assertIn("Decision: BLOCKED", final_text)

    def test_model_cannot_override_trusted_unknown_rights(self):
        case = next(case for case in self.v2["cases"] if case["id"] == "CTI-004")
        payload = self.valid_payload()
        payload["answer"] = "Reuse the source now."
        payload["claims"] = [
            {
                "claim_id": "C1",
                "span": "Reuse the source now.",
                "disposition": "UNKNOWN",
                "evidence_ids": [],
            }
        ]
        payload["reuse_requests"] = [{"artifact_id": "source-tree", "reuse_requested": True}]
        final_text, result = RUNNER.guarded_output(
            json.dumps(payload),
            case,
            self.policy["cases"]["CTI-004"],
        )
        self.assertFalse(result["accepted"])
        self.assertTrue(any("RIGHTS_NOT_VERIFIED" in item for item in result["blockers"]))
        self.assertIn("Decision: BLOCKED", final_text)

    def test_unknown_claim_evidence_id_blocks_final_output(self):
        case = next(case for case in self.v2["cases"] if case["id"] == "CTI-001")
        payload = self.valid_payload()
        payload["claims"][0]["evidence_ids"] = ["MADE_UP_SOURCE"]
        final_text, result = RUNNER.guarded_output(
            json.dumps(payload),
            case,
            self.policy["cases"]["CTI-001"],
        )
        self.assertFalse(result["accepted"])
        self.assertTrue(any("EVIDENCE_ID_NOT_FOUND" in item for item in result["blockers"]))
        self.assertIn("Decision: BLOCKED", final_text)

    def test_invalid_json_is_blocked_and_raw_response_is_not_returned_as_final(self):
        final_text, result = RUNNER.guarded_output(
            "This is not JSON.",
            self.v2["cases"][0],
            self.policy["cases"][self.v2["cases"][0]["id"]],
        )
        self.assertFalse(result["schema_valid"])
        self.assertTrue(result["guard_intervention"])
        self.assertIn("Decision: BLOCKED", final_text)
        self.assertNotIn("This is not JSON.", final_text)


    def test_score_freezer_accepts_complete_blind_ledger_and_rejects_incomplete_rationales(self):
        freezer = ROOT / "benchmarks/hg_cti_v2/freeze_scores.py"
        ids = [f"CTI-{i:03d}" for i in range(1, 41)]
        def build_run(directory, valid=True):
            blind = [{"case_id": case_id, "A": "A output", "B": "B output"} for case_id in ids]
            blind_path = directory / "blind_pairs.jsonl"
            blind_path.write_text("".join(json.dumps(row) + "\n" for row in blind))
            score_rows = []
            for case_id in ids:
                row = {"case_id": case_id}
                for label in ("A", "B"):
                    value = {
                        "criteria": [1, 1, 1, 1],
                        "criterion_rationales": ["rationale 1", "rationale 2", "rationale 3", "rationale 4"],
                        "critical_violation": False,
                        "raw_critical_violation": False,
                        "guard_intervention": False,
                        "material_claims": 0,
                        "unsupported_material_claims": 0,
                        "claim_ledger": [],
                        "counterexample_handled": 0,
                        "alternative_distinctness": 1,
                        "notes": "synthetic freezer test only",
                    }
                    if not valid:
                        value.pop("criterion_rationales")
                    row[label] = value
                score_rows.append(row)
            score_doc = {
                "schema": "HG-CTI-BLIND-SCORES-V2",
                "scored_blind_file_sha256": hashlib.sha256(blind_path.read_bytes()).hexdigest(),
                "case_scores": score_rows,
            }
            (directory / "blind_scores.json").write_text(json.dumps(score_doc))
            (directory / "blind_key.json").write_text(json.dumps({case_id: {"A": "baseline", "B": "candidate"} for case_id in ids}))
            (directory / "SHA256SUMS.txt").write_text(
                hashlib.sha256(blind_path.read_bytes()).hexdigest() + "  blind_pairs.jsonl\n"
            )

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            build_run(directory, valid=True)
            result = subprocess.run([sys.executable, str(freezer), "--run-dir", str(directory)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            freeze = json.loads((directory / "score-freeze.json").read_text())
            self.assertEqual(freeze["status"], "FROZEN_BLIND_SCORES")
            manifest = (directory / "SHA256SUMS.txt").read_text()
            self.assertIn("blind_scores.json", manifest)
            self.assertIn("score-freeze.json", manifest)
            self.assertNotIn("blind_key.json", manifest)
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            build_run(directory, valid=False)
            result = subprocess.run([sys.executable, str(freezer), "--run-dir", str(directory)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((directory / "score-freeze.json").exists())

    def test_preregistration_freeze_and_all_artifact_hashes_match_when_present(self):
        prereg_path = ROOT / "benchmarks/hg_cti_v2/preregistration.json"
        freeze_path = ROOT / "benchmarks/hg_cti_v2/preregistration-freeze.json"
        if not prereg_path.is_file() or not freeze_path.is_file():
            self.skipTest("V2 protocol freeze is created only after implementation tests pass")
        prereg = json.loads(prereg_path.read_text())
        freeze = json.loads(freeze_path.read_text())
        self.assertEqual(prereg["status"], "FROZEN_BEFORE_EVALUATION")
        self.assertEqual(prereg["status"], freeze["status"])
        self.assertEqual(prereg["case_count"], 40)
        self.assertEqual(prereg["thresholds"]["minimum_usefulness_gain_pp"], 10.0)
        self.assertEqual(prereg["thresholds"]["maximum_unsupported_claim_rate"], 0.02)
        self.assertEqual(prereg["thresholds"]["minimum_counterexample_sensitivity"], 0.95)
        self.assertEqual(prereg["thresholds"]["maximum_overall_regression_rate"], 0.02)
        self.assertFalse(prereg["constraints"]["independent_review_gate"])
        discrepancy = prereg["known_v1_provenance_discrepancies"][0]
        self.assertEqual(discrepancy["file"], "benchmarks/hg_cti_v1/README.md")
        self.assertNotEqual(discrepancy["original_preregistration_sha256"], discrepancy["current_sha256"])
        self.assertEqual(freeze["preregistration_sha256"], hashlib.sha256(prereg_path.read_bytes()).hexdigest())
        protocol = ROOT / prereg["protocol"]
        self.assertEqual(freeze["protocol_sha256"], hashlib.sha256(protocol.read_bytes()).hexdigest())
        for relpath, expected in prereg["frozen_artifact_hashes"].items():
            self.assertEqual(hashlib.sha256((ROOT / relpath).read_bytes()).hexdigest(), expected, relpath)

    def test_model_cannot_supply_or_override_trusted_rights_fields(self):
        payload = self.valid_payload()
        payload["reuse_requests"] = [{
            "artifact_id": "source-tree",
            "reuse_requested": True,
            "assessment": {"rights": "VERIFIED"},
        }]
        errors = RUNNER.validate_response_shape(payload)
        self.assertIn("REUSE_REQUEST_SCHEMA_INVALID", errors)

    def test_canonical_write_is_blocked_by_scope_guard(self):
        case = next(case for case in self.v2["cases"] if case["id"] == "CTI-018")
        payload = self.valid_payload()
        payload["answer"] = "Write canonical/state.json now."
        payload["actions"] = [{"action": "write", "scope": "canonical/state.json", "cost_usd": None}]
        payload["claims"] = [{
            "claim_id": "C1", "span": "Write canonical/state.json now.",
            "disposition": "UNKNOWN", "evidence_ids": [],
        }]
        final_text, result = RUNNER.guarded_output(
            json.dumps(payload), case, self.policy["cases"]["CTI-018"]
        )
        self.assertFalse(result["accepted"])
        self.assertTrue(any("SCOPE_NOT_ALLOWED" in blocker for blocker in result["blockers"]))
        self.assertIn("Decision: BLOCKED", final_text)

    def test_v1_manifests_verify_before_v2_is_allowed(self):
        root_manifest = ROOT / "evidence/HG-CTI-20261013/SHA256SUMS.txt"
        run_dir = ROOT / "evidence/HG-CTI-20261013/benchmark-run-local-001"
        root_result = RUNNER.verify_sha256_manifest(root_manifest, ROOT)
        run_result = RUNNER.verify_sha256_manifest(run_dir / "SHA256SUMS.txt", run_dir)
        self.assertEqual(root_result["failures"], 0)
        self.assertEqual(run_result["failures"], 0)
        self.assertGreater(root_result["entries_checked"], 0)
        self.assertGreater(run_result["entries_checked"], 0)

    def test_superseded_v2_freeze_is_archived_and_has_no_run_claim(self):
        archive = ROOT / "benchmarks/hg_cti_v2/archive"
        prereg_path = archive / "preregistration-v2.0.json"
        freeze_path = archive / "preregistration-freeze-v2.0.json"
        self.assertTrue(prereg_path.is_file())
        self.assertTrue(freeze_path.is_file())
        prereg = json.loads(prereg_path.read_text())
        freeze = json.loads(freeze_path.read_text())
        self.assertEqual(freeze["preregistration_sha256"], hashlib.sha256(prereg_path.read_bytes()).hexdigest())
        self.assertTrue(freeze["no_model_inference_before_freeze"])
        self.assertFalse((ROOT / "evidence/HG-CTI-20261014/benchmark-run-v2-local-001/raw_runs.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
