"""Deterministic tests for HG's bounded evolution evaluation gate."""
import copy
import hashlib
import unittest

from hg.evolution import (
    EVALUATION_V1, PROPOSAL_V1, EvolutionError,
    compare_evaluations as _compare_evaluations,
    propose_offline_variants, seal_evaluation, validate_proposal,
)


def compare_evaluations(spec, baseline, candidate, **kwargs):
    """Test harness stub only; it is not a production evidence verifier."""
    kwargs.setdefault("evidence_verifier_id", "unit-test-stub")
    kwargs.setdefault("evidence_verifier", lambda _ref: True)
    return _compare_evaluations(spec, baseline, candidate, **kwargs)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def proposal(**overrides):
    value = {
        "schema_version": PROPOSAL_V1,
        "proposal_id": "proposal-01",
        "target_kind": "ROUTING_RULE",
        "target_id": "routing-default",
        "hypothesis": "The candidate handles one previously missed required case.",
        "baseline_digest": sha("baseline-artifact"),
        "candidate_digest": sha("candidate-artifact"),
        "suite_digest": sha("frozen-suite-v1"),
        "environment_digest": sha("termux-python-stdlib-v1"),
        "rollback_digest": sha("rollback-artifact"),
        "required_case_ids": ["case-critical", "case-hard", "case-normal"],
        "evidence_refs": ["evidence:proposal.json"],
        "minimum_gain_pp": 20.0,
        "max_runtime_seconds": 10.0,
        "max_memory_bytes": 16_000_000,
        "max_tool_calls": 5,
        "max_model_calls": 3,
        "max_artifact_bytes": 100_000,
        "risk_class": "LOCAL_READ_ONLY",
        "created_at": "2026-10-20T02:00:00+07:00",
    }
    value.update(overrides)
    return value


def evaluation(*, evaluation_id, artifact_digest, statuses, **overrides):
    cases = [
        {"case_id": cid, "status": status, "severity": severity}
        for cid, status, severity in statuses
    ]
    value = {
        "schema_version": EVALUATION_V1,
        "evaluation_id": evaluation_id,
        "target_kind": "ROUTING_RULE",
        "target_id": "routing-default",
        "artifact_digest": artifact_digest,
        "suite_digest": sha("frozen-suite-v1"),
        "environment_digest": sha("termux-python-stdlib-v1"),
        "cases": sorted(cases, key=lambda case: case["case_id"]),
        "metrics": {
            "elapsed_ms": 1000,
            "peak_memory_bytes": 1_000_000,
            "tool_calls": 1,
            "model_calls": 0,
            "artifact_bytes": 2048,
        },
        "evidence_refs": ["evidence:" + evaluation_id + ".json"],
    }
    value.update(overrides)
    return seal_evaluation(value)


def base_and_candidate(candidate_statuses=None, **candidate_overrides):
    spec = proposal()
    baseline = evaluation(
        evaluation_id="baseline-01",
        artifact_digest=spec["baseline_digest"],
        statuses=[
            ("case-critical", "PASS", "C0"),
            ("case-hard", "FAIL", "C1"),
            ("case-normal", "FAIL", "C2"),
        ],
    )
    candidate = evaluation(
        evaluation_id="candidate-01",
        artifact_digest=spec["candidate_digest"],
        statuses=candidate_statuses or [
            ("case-critical", "PASS", "C0"),
            ("case-hard", "PASS", "C1"),
            ("case-normal", "FAIL", "C2"),
        ],
        **candidate_overrides,
    )
    return spec, baseline, candidate


class EvolutionGateTests(unittest.TestCase):
    def test_candidate_with_measured_gain_is_eligible_not_auto_promoted(self):
        result = compare_evaluations(*base_and_candidate())
        self.assertEqual(result["status"], "PROMOTION_ELIGIBLE")
        self.assertAlmostEqual(result["gain_pp"], 100 / 3, places=4)
        self.assertFalse(result["promotion_is_automatic"])
        self.assertEqual(len(result["decision_digest"]), 64)

    def test_protected_target_is_never_evolvable_by_this_gate(self):
        with self.assertRaisesRegex(EvolutionError, "EVOLUTION_TARGET_PROTECTED"):
            validate_proposal(proposal(target_kind="SECURITY_POLICY"))

    def test_unlisted_target_is_rejected(self):
        with self.assertRaisesRegex(EvolutionError, "EVOLUTION_TARGET_KIND_NOT_ALLOWLISTED"):
            validate_proposal(proposal(target_kind="EXECUTABLE_PLUGIN"))

    def test_destructive_risk_class_is_not_eligible(self):
        with self.assertRaisesRegex(EvolutionError, "EVOLUTION_RISK_CLASS_NOT_ELIGIBLE"):
            validate_proposal(proposal(risk_class="DESTRUCTIVE"))

    def test_candidate_c0_failure_overrides_gain(self):
        spec, baseline, candidate = base_and_candidate([
            ("case-critical", "FAIL", "C0"),
            ("case-hard", "PASS", "C1"),
            ("case-normal", "PASS", "C2"),
        ])
        result = compare_evaluations(spec, baseline, candidate)
        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(result["reason_code"], "CANDIDATE_C0_FAILURE")

    def test_baseline_c0_failure_makes_comparison_inconclusive(self):
        spec, baseline, candidate = base_and_candidate()
        broken = evaluation(
            evaluation_id="unsafe-baseline",
            artifact_digest=spec["baseline_digest"],
            statuses=[
                ("case-critical", "FAIL", "C0"),
                ("case-hard", "FAIL", "C1"),
                ("case-normal", "FAIL", "C2"),
            ],
        )
        result = compare_evaluations(spec, broken, candidate)
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertEqual(result["reason_code"], "BASELINE_C0_NOT_CLEAN")

    def test_any_previous_pass_regression_rejects_candidate(self):
        spec = proposal()
        baseline = evaluation(
            evaluation_id="regression-baseline",
            artifact_digest=spec["baseline_digest"],
            statuses=[
                ("case-critical", "PASS", "C0"),
                ("case-hard", "PASS", "C1"),
                ("case-normal", "FAIL", "C2"),
            ],
        )
        candidate = evaluation(
            evaluation_id="regressed-candidate",
            artifact_digest=spec["candidate_digest"],
            statuses=[
                ("case-critical", "PASS", "C0"),
                ("case-hard", "FAIL", "C1"),
                ("case-normal", "PASS", "C2"),
            ],
        )
        result = compare_evaluations(spec, baseline, candidate)
        self.assertEqual(result["reason_code"], "BASELINE_PASS_REGRESSION")
        self.assertEqual(result["regression_case_ids"], ["case-hard"])

    def test_missing_or_blocked_case_cannot_promote(self):
        spec, baseline, _ = base_and_candidate()
        candidate = evaluation(
            evaluation_id="blocked-candidate",
            artifact_digest=spec["candidate_digest"],
            statuses=[
                ("case-critical", "PASS", "C0"),
                ("case-hard", "BLOCKED", "C1"),
                ("case-normal", "PASS", "C2"),
            ],
        )
        result = compare_evaluations(spec, baseline, candidate)
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertEqual(result["reason_code"], "CANDIDATE_INCOMPLETE")

    def test_missing_case_id_set_is_rejected(self):
        spec, baseline, _ = base_and_candidate()
        candidate = evaluation(
            evaluation_id="wrong-case-set",
            artifact_digest=spec["candidate_digest"],
            statuses=[
                ("case-critical", "PASS", "C0"),
                ("case-hard", "PASS", "C1"),
            ],
        )
        with self.assertRaisesRegex(EvolutionError, "EVOLUTION_CASE_SET_MISMATCH"):
            compare_evaluations(spec, baseline, candidate)

    def test_suite_mismatch_is_rejected(self):
        spec, baseline, candidate = base_and_candidate()
        candidate = copy.deepcopy(candidate)
        candidate["suite_digest"] = sha("another-suite")
        # Seal the altered context to prove the mismatch is checked independently of its digest.
        candidate.pop("evaluation_digest")
        from hg.evolution import seal_evaluation
        candidate = seal_evaluation(candidate)
        with self.assertRaisesRegex(EvolutionError, "EVOLUTION_SUITE_DIGEST_MISMATCH"):
            compare_evaluations(spec, baseline, candidate)

    def test_no_gain_keeps_baseline(self):
        spec = proposal(minimum_gain_pp=10.0)
        baseline = evaluation(
            evaluation_id="baseline-no-gain",
            artifact_digest=spec["baseline_digest"],
            statuses=[
                ("case-critical", "PASS", "C0"),
                ("case-hard", "FAIL", "C1"),
                ("case-normal", "PASS", "C2"),
            ],
        )
        candidate = evaluation(
            evaluation_id="candidate-no-gain",
            artifact_digest=spec["candidate_digest"],
            statuses=[
                ("case-critical", "PASS", "C0"),
                ("case-hard", "FAIL", "C1"),
                ("case-normal", "PASS", "C2"),
            ],
        )
        result = compare_evaluations(spec, baseline, candidate)
        self.assertEqual(result["status"], "KEEP_BASELINE")
        self.assertEqual(result["reason_code"], "NO_REQUIRED_GAIN")

    def test_resource_budget_violation_rejects_candidate(self):
        spec, baseline, _ = base_and_candidate()
        candidate = evaluation(
            evaluation_id="slow-candidate",
            artifact_digest=spec["candidate_digest"],
            statuses=[
                ("case-critical", "PASS", "C0"),
                ("case-hard", "PASS", "C1"),
                ("case-normal", "FAIL", "C2"),
            ],
            metrics={
                "elapsed_ms": 20_000, "peak_memory_bytes": 1_000_000,
                "tool_calls": 1, "model_calls": 0, "artifact_bytes": 2048,
            },
        )
        result = compare_evaluations(spec, baseline, candidate)
        self.assertEqual(result["reason_code"], "RUNTIME_BUDGET_EXCEEDED")

    def test_changed_evaluation_bytes_fail_digest_check(self):
        spec, baseline, candidate = base_and_candidate()
        changed = copy.deepcopy(candidate)
        changed["cases"][2]["status"] = "PASS"
        with self.assertRaisesRegex(EvolutionError, "EVOLUTION_EVALUATION_DIGEST_MISMATCH"):
            compare_evaluations(spec, baseline, changed)

    def test_proposal_must_pin_timezone_and_minimum_gain(self):
        with self.assertRaisesRegex(EvolutionError, "EVOLUTION_CREATED_AT_TIMEZONE_REQUIRED"):
            validate_proposal(proposal(created_at="2026-10-20T02:00:00"))
        with self.assertRaisesRegex(EvolutionError, "EVOLUTION_MINIMUM_GAIN_INVALID"):
            validate_proposal(proposal(minimum_gain_pp=0))

    def test_candidate_digest_must_match_proposal(self):
        spec, baseline, candidate = base_and_candidate()
        wrong = evaluation(
            evaluation_id="wrong-digest",
            artifact_digest=sha("different artifact"),
            statuses=[
                ("case-critical", "PASS", "C0"),
                ("case-hard", "PASS", "C1"),
                ("case-normal", "FAIL", "C2"),
            ],
        )
        with self.assertRaisesRegex(EvolutionError, "EVOLUTION_CANDIDATE_DIGEST_MISMATCH"):
            compare_evaluations(spec, baseline, wrong)

    def test_missing_or_failing_evidence_verifier_never_eligible(self):
        spec, baseline, candidate = base_and_candidate()
        missing = _compare_evaluations(spec, baseline, candidate)
        self.assertEqual(missing["status"], "INCONCLUSIVE")
        self.assertEqual(missing["reason_code"], "EVIDENCE_VERIFIER_REQUIRED")
        rejected = _compare_evaluations(
            spec, baseline, candidate, evidence_verifier_id="test-false-verifier",
            evidence_verifier=lambda _ref: False
        )
        self.assertEqual(rejected["status"], "INCONCLUSIVE")
        self.assertEqual(rejected["reason_code"], "EVIDENCE_REFERENCE_UNVERIFIED")

    def test_unhashable_target_and_case_status_fail_closed(self):
        with self.assertRaisesRegex(EvolutionError, "EVOLUTION_TARGET_KIND_INVALID"):
            validate_proposal(proposal(target_kind=[]))
        report = {
            "schema_version": EVALUATION_V1,
            "evaluation_id": "malformed",
            "target_kind": "ROUTING_RULE",
            "target_id": "routing-default",
            "artifact_digest": sha("candidate"),
            "suite_digest": sha("suite"),
            "environment_digest": sha("environment"),
            "cases": [{"case_id": "case-01", "status": [], "severity": "C0"}],
            "metrics": {
                "elapsed_ms": 1, "peak_memory_bytes": 1, "tool_calls": 0,
                "model_calls": 0, "artifact_bytes": 1,
            },
            "evidence_refs": ["evidence:malformed.json"],
        }
        with self.assertRaisesRegex(EvolutionError, "EVOLUTION_CASE_STATUS_INVALID"):
            seal_evaluation(report)


class OfflineMutationTests(unittest.TestCase):
    def test_candidate_is_deterministic_evidence_linked_and_never_activated(self):
        baseline = "HG prompt v1: preserve constraints and show evidence."
        baseline_digest = sha(baseline)
        signals = [
            {"code": "EVIDENCE_GAP", "evidence_refs": ["evidence:case-01.json"]},
            {"code": "CONSTRAINT_DRIFT", "evidence_refs": ["evidence:case-02.json"]},
        ]
        first = propose_offline_variants(
            target_kind="PROMPT_TEMPLATE", target_id="hg-answer-v1",
            baseline_text=baseline, baseline_digest=baseline_digest,
            failure_signals=signals, max_variants=4,
        )
        second = propose_offline_variants(
            target_kind="PROMPT_TEMPLATE", target_id="hg-answer-v1",
            baseline_text=baseline, baseline_digest=baseline_digest,
            failure_signals=signals, max_variants=4,
        )
        self.assertEqual(first, second)
        self.assertEqual(len(first), 2)
        self.assertEqual(baseline, "HG prompt v1: preserve constraints and show evidence.")
        for candidate in first:
            self.assertEqual(candidate["activation_state"], "PROPOSED_NOT_ACTIVE")
            self.assertFalse(candidate["automatic_activation"])
            self.assertTrue(candidate["requires_evaluation"])
            self.assertEqual(candidate["baseline_digest"], baseline_digest)
            self.assertEqual(candidate["candidate_digest"], sha(candidate["candidate_text"]))
            self.assertEqual(len(candidate["evidence_refs"]), 1)

    def test_existing_operator_is_not_added_twice(self):
        marker = "[HG-EVOLUTION:PROMPT_TEMPLATE:EVIDENCE_GAP:V1]"
        baseline = "base\n\n" + marker + "\nprior directive"
        result = propose_offline_variants(
            target_kind="PROMPT_TEMPLATE", target_id="hg-answer-v1",
            baseline_text=baseline, baseline_digest=sha(baseline),
            failure_signals=[{"code": "EVIDENCE_GAP", "evidence_refs": ["evidence:case.json"]}],
        )
        self.assertEqual(result, [])

    def test_mutator_rejects_stale_baseline_digest_and_protected_targets(self):
        with self.assertRaisesRegex(EvolutionError, "EVOLUTION_BASELINE_TEXT_DIGEST_MISMATCH"):
            propose_offline_variants(
                target_kind="PROMPT_TEMPLATE", target_id="hg-answer-v1",
                baseline_text="changed text", baseline_digest=sha("old text"),
                failure_signals=[{"code": "EVIDENCE_GAP", "evidence_refs": ["evidence:case.json"]}],
            )
        with self.assertRaisesRegex(EvolutionError, "EVOLUTION_OFFLINE_TARGET_UNSUPPORTED"):
            propose_offline_variants(
                target_kind="SECURITY_POLICY", target_id="core-policy",
                baseline_text="immutable", baseline_digest=sha("immutable"),
                failure_signals=[{"code": "EVIDENCE_GAP", "evidence_refs": ["evidence:case.json"]}],
            )

    def test_mutator_rejects_unknown_signals_and_missing_evidence(self):
        with self.assertRaisesRegex(EvolutionError, "EVOLUTION_FAILURE_CODE_UNSUPPORTED"):
            propose_offline_variants(
                target_kind="PROMPT_TEMPLATE", target_id="hg-answer-v1",
                baseline_text="base", baseline_digest=sha("base"),
                failure_signals=[{"code": "INVENTED_SIGNAL", "evidence_refs": ["evidence:case.json"]}],
            )
        with self.assertRaisesRegex(EvolutionError, "EVOLUTION_FAILURE_EVIDENCE_INVALID"):
            propose_offline_variants(
                target_kind="PROMPT_TEMPLATE", target_id="hg-answer-v1",
                baseline_text="base", baseline_digest=sha("base"),
                failure_signals=[{"code": "EVIDENCE_GAP", "evidence_refs": []}],
            )

    def test_offline_generator_respects_candidate_count_cap(self):
        baseline = "HG strategy v1"
        signals = [
            {"code": code, "evidence_refs": ["evidence:" + code + ".json"]}
            for code in ("EVIDENCE_GAP", "CONSTRAINT_DRIFT", "UNVERIFIED_TOOL_OUTPUT")
        ]
        result = propose_offline_variants(
            target_kind="PROMPT_TEMPLATE", target_id="hg-answer-v1",
            baseline_text=baseline, baseline_digest=sha(baseline),
            failure_signals=signals, max_variants=2,
        )
        self.assertEqual(len(result), 2)
        self.assertEqual([x["diagnostic_code"] for x in result],
                         ["CONSTRAINT_DRIFT", "EVIDENCE_GAP"])


if __name__ == "__main__":
    unittest.main()
