from __future__ import annotations
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from hg.hni30_evaluator import EXPECTED_IDS, ORACLE_VERSION, BUNDLE_SCHEMA, evaluate_bundle, load_oracle, validate_oracle

ROOT = Path(__file__).resolve().parents[1]
ORACLE_PATH = ROOT / "docs/HNI30-EVALUATOR-ORACLE-V1.json"
CRITERIA_PATH = ROOT / "docs/HG-NATIVE-INTELLIGENCE-CRITERIA-DRAFT-V1.md"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class HNI30EvaluatorContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle = load_oracle(ORACLE_PATH, CRITERIA_PATH)

    def _bundle(self, root: Path, run_kind="SYNTHETIC_TEST", statuses=None):
        artifacts = root / "artifacts"
        artifacts.mkdir(exist_ok=True)
        contents = {
            "input.json": b'{"synthetic":true,"kind":"input"}',
            "output.json": b'{"synthetic":true,"kind":"output"}',
            "trace.jsonl": b'{"synthetic":true,"kind":"trace"}\n',
            "environment.json": b'{"synthetic":true,"kind":"environment"}',
        }
        refs = {}
        for name, content in contents.items():
            (artifacts / name).write_bytes(content)
            refs[name] = {"path": f"artifacts/{name}", "sha256": digest(content)}
        build = {
            "build_id": "synthetic-build-for-contract-tests", "source_commit": "a" * 40,
            "source_tree_sha256": "b" * 64, "runtime_source_sha256": "c" * 64,
            "config_sha256": "d" * 64, "environment_sha256": refs["environment.json"]["sha256"],
            "model_provider": "synthetic-test-provider", "model_id": "synthetic-test-model",
            "endpoint_host": "synthetic.invalid", "nonsecret_model_config_sha256": "e" * 64,
        }
        observations = []
        for i, cid in enumerate(EXPECTED_IDS, 1):
            status = (statuses or {}).get(cid, "PASS")
            observations.append({
                "criterion_id": cid, "oracle_version": ORACLE_VERSION, "status": status,
                "case_id": f"SYN-{i:02d}-{'POS' if status == 'PASS' else 'NEG'}",
                "runtime_build_identity": build["build_id"],
                "criteria_source_sha256": self.oracle["criteria_source"]["sha256"],
                "observed_at": "synthetic-test-clock-not-attested",
                "input": refs["input.json"], "output": refs["output.json"],
                "trace": refs["trace.jsonl"], "environment": refs["environment.json"],
                "assertions": [{"assertion_id": "synthetic-contract-assertion", "passed": status == "PASS"}],
                "review": {"method": "synthetic_contract_test", "reviewer_id": "test-harness", "decision": status},
            })
        return {"schema_version": BUNDLE_SCHEMA, "run_kind": run_kind, "oracle_version": ORACLE_VERSION,
                "criteria_source_sha256": self.oracle["criteria_source"]["sha256"], "runtime_build": build,
                "observations": observations}

    def test_oracle_covers_exactly_30_source_bound_criteria(self):
        result = validate_oracle(self.oracle, CRITERIA_PATH)
        self.assertTrue(result["valid"])
        self.assertEqual(result["criterion_count"], 30)
        self.assertEqual([x["criterion_id"] for x in self.oracle["oracles"]], EXPECTED_IDS)

    def test_each_of_30_positive_contract_cases_stays_synthetic_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = evaluate_bundle(self._bundle(root), self.oracle, CRITERIA_PATH, root)
        self.assertEqual(result["evaluation_status"], "SYNTHETIC_ONLY")
        self.assertEqual(result["counts"]["PASS"], 30)
        self.assertFalse(result["release_authorized"])
        self.assertTrue(all(x["reason"] == "SYNTHETIC_CASE_ONLY_NOT_HG_VERDICT" for x in result["findings"]))

    def test_each_of_30_negative_contract_cases_stays_synthetic_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = evaluate_bundle(self._bundle(root, statuses={cid: "FAIL" for cid in EXPECTED_IDS}), self.oracle, CRITERIA_PATH, root)
        self.assertEqual(result["evaluation_status"], "SYNTHETIC_ONLY")
        self.assertEqual(result["counts"]["FAIL"], 30)
        self.assertFalse(result["release_authorized"])

    def test_missing_observations_are_not_run_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = self._bundle(root)
            bundle["observations"] = []
            result = evaluate_bundle(bundle, self.oracle, CRITERIA_PATH, root)
        self.assertEqual(result["counts"]["NOT_RUN"], 30)
        self.assertEqual(result["evaluation_status"], "SYNTHETIC_ONLY")

    def test_runtime_build_requires_model_and_provider_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = self._bundle(root, run_kind="HG_RUNTIME")
            bundle["runtime_build"].pop("model_id")
            approved = copy.deepcopy(self.oracle)
            approved["status"] = "APPROVED_FOR_RUNTIME"
            result = evaluate_bundle(bundle, approved, CRITERIA_PATH, root,
                provenance_verifier=lambda _: True,
                review_verifier=lambda review, row, entry: review["decision"] == row["status"])
        self.assertEqual(result["evaluation_status"], "BLOCKED")
        self.assertEqual(result["counts"]["BLOCKED"], 30)
        self.assertFalse(result["runtime_build_identity_present"])

    def test_runtime_mode_blocks_unapproved_oracle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = self._bundle(root, run_kind="HG_RUNTIME")
            result = evaluate_bundle(bundle, self.oracle, CRITERIA_PATH, root, provenance_verifier=lambda _: True,
                                         review_verifier=lambda review, row, entry: review["decision"] == row["status"])
        self.assertEqual(result["evaluation_status"], "BLOCKED")
        self.assertEqual(result["counts"]["BLOCKED"], 30)
        self.assertFalse(result["release_authorized"])

    def test_runtime_mode_blocks_without_independent_provenance_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = self._bundle(root, run_kind="HG_RUNTIME")
            approved = copy.deepcopy(self.oracle)
            approved["status"] = "APPROVED_FOR_RUNTIME"
            result = evaluate_bundle(bundle, approved, CRITERIA_PATH, root)
        self.assertEqual(result["evaluation_status"], "BLOCKED")
        self.assertEqual(result["counts"]["BLOCKED"], 30)
        self.assertFalse(result["runtime_provenance_verified"])

    def test_runtime_path_requires_approved_oracle_and_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = self._bundle(root, run_kind="HG_RUNTIME")
            approved = copy.deepcopy(self.oracle)
            approved["status"] = "APPROVED_FOR_RUNTIME"
            result = evaluate_bundle(bundle, approved, CRITERIA_PATH, root, provenance_verifier=lambda bundle: bundle["runtime_build"]["build_id"] == "synthetic-build-for-contract-tests",
                                         review_verifier=lambda review, row, entry: review["decision"] == row["status"])
        self.assertEqual(result["evaluation_status"], "PASS")
        self.assertEqual(result["counts"]["PASS"], 30)
        self.assertFalse(result["release_authorized"])

    def test_verifier_exceptions_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = self._bundle(root, run_kind="HG_RUNTIME")
            approved = copy.deepcopy(self.oracle)
            approved["status"] = "APPROVED_FOR_RUNTIME"
            def broken_provenance(_):
                raise RuntimeError("must not escape")
            result = evaluate_bundle(bundle, approved, CRITERIA_PATH, root, provenance_verifier=broken_provenance,
                review_verifier=lambda review, row, entry: review["decision"] == row["status"])
        self.assertEqual(result["evaluation_status"], "BLOCKED")
        self.assertEqual(result["counts"]["BLOCKED"], 30)

    def test_critical_failure_dominates_average(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = self._bundle(root, run_kind="HG_RUNTIME", statuses={"HNI-23": "FAIL"})
            approved = copy.deepcopy(self.oracle)
            approved["status"] = "APPROVED_FOR_RUNTIME"
            result = evaluate_bundle(bundle, approved, CRITERIA_PATH, root, provenance_verifier=lambda _: True,
                                         review_verifier=lambda review, row, entry: review["decision"] == row["status"])
        self.assertEqual(result["evaluation_status"], "FAIL")
        self.assertEqual(result["counts"]["FAIL"], 1)

    def test_tampered_evidence_blocks_instead_of_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = self._bundle(root, run_kind="HG_RUNTIME")
            approved = copy.deepcopy(self.oracle)
            approved["status"] = "APPROVED_FOR_RUNTIME"
            (root / "artifacts/output.json").write_bytes(b"tampered")
            result = evaluate_bundle(bundle, approved, CRITERIA_PATH, root, provenance_verifier=lambda _: True,
                                         review_verifier=lambda review, row, entry: review["decision"] == row["status"])
        self.assertEqual(result["evaluation_status"], "BLOCKED")
        self.assertEqual(result["counts"]["BLOCKED"], 30)

    def test_runtime_mode_blocks_without_review_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = self._bundle(root, run_kind="HG_RUNTIME")
            approved = copy.deepcopy(self.oracle)
            approved["status"] = "APPROVED_FOR_RUNTIME"
            result = evaluate_bundle(bundle, approved, CRITERIA_PATH, root, provenance_verifier=lambda _: True)
        self.assertEqual(result["evaluation_status"], "BLOCKED")
        self.assertEqual(result["counts"]["BLOCKED"], 30)

    def test_path_traversal_in_evidence_reference_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = self._bundle(root, run_kind="HG_RUNTIME")
            bundle["observations"][0]["input"] = {"path": "../outside", "sha256": "a" * 64}
            approved = copy.deepcopy(self.oracle)
            approved["status"] = "APPROVED_FOR_RUNTIME"
            result = evaluate_bundle(bundle, approved, CRITERIA_PATH, root,
                provenance_verifier=lambda _: True,
                review_verifier=lambda review, row, entry: review["decision"] == row["status"])
        self.assertEqual(result["evaluation_status"], "BLOCKED")
        self.assertEqual(result["findings"][0]["effective_status"], "BLOCKED")
        self.assertIn("PATH_NOT_RELATIVE_SAFE", result["findings"][0]["reason"])

    def test_duplicate_criterion_observation_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = self._bundle(root)
            bundle["observations"].append(copy.deepcopy(bundle["observations"][0]))
            with self.assertRaisesRegex(ValueError, "UNKNOWN_OR_DUPLICATE"):
                evaluate_bundle(bundle, self.oracle, CRITERIA_PATH, root)

    def test_oracle_source_digest_mismatch_rejected(self):
        bad = copy.deepcopy(self.oracle)
        bad["criteria_source"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "CRITERIA_SOURCE_DIGEST_MISMATCH"):
            validate_oracle(bad, CRITERIA_PATH)

    def test_critical_gate_policy_is_explicit(self):
        critical = [x["criterion_id"] for x in self.oracle["oracles"] if x["critical_gate"]]
        self.assertEqual(critical, ["HNI-20", "HNI-22", "HNI-23", "HNI-24", "HNI-26", "HNI-27", "HNI-29"])


if __name__ == "__main__":
    unittest.main()
