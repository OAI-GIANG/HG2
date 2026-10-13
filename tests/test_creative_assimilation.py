import unittest
from dataclasses import replace
from hg.creative_assimilation import CreativePrinciple, SourceEvidence, SynthesisCandidate, TrustAssessment, evaluate_candidate, transition, validate_source

SHA_A, SHA_B = "a" * 64, "b" * 64
COMMIT_A, COMMIT_B = "1" * 40, "2" * 40

def source(source_id="a", sha=SHA_A, revision=COMMIT_A):
    return SourceEvidence(source_id, sha, "https://github.com/example/" + source_id, revision,
                          "VERIFIED", "PASS", "PASS", ("README.md",), ("archive snapshot only",), ("manifest:archive:" + source_id,))

def candidate(**changes):
    base = SynthesisCandidate(
        "ca-001", ("p-a", "p-b"), ("a", "b"),
        "Combining retrieval provenance with scoped admission reduces unsupported reuse.",
        "Fewer untraceable retained lessons.", "Offline candidate evaluation only.",
        "Compare fixed baseline and candidate on a versioned case set.",
        ("No authority bypass.", "At least one measurable quality gain."),
        ("False rejection.", "Stale source revision."), ("archive:a", "archive:b"),
        trust=TrustAssessment("PASS", "PASS", "VERIFIED", "PASS", "PASS"))
    return replace(base, **changes)

class SourceEvidenceTests(unittest.TestCase):
    def test_verified_source_has_no_blockers(self): self.assertEqual(validate_source(source()), ())
    def test_digest_not_source_authenticity(self):
        issues = validate_source(replace(source(), source_revision="", source_authenticity="UNKNOWN"))
        self.assertIn("UPSTREAM_REVISION_UNVERIFIED", issues)
        self.assertIn("SOURCE_AUTHENTICITY_NOT_VERIFIED", issues)
    def test_missing_license_fails_closed(self):
        self.assertIn("LICENSE_NOT_VERIFIED", validate_source(replace(source(), license_status="UNKNOWN")))
    def test_http_upstream_rejected(self):
        self.assertIn("UPSTREAM_URL_UNVERIFIED", validate_source(replace(source(), upstream_url="http://example.com")))
    def test_missing_inspected_path_blocks(self):
        self.assertIn("INSPECTED_PATHS_MISSING", validate_source(replace(source(), inspected_paths=())))
    def test_missing_source_evidence_ref_blocks(self):
        self.assertIn("SOURCE_EVIDENCE_REFS_MISSING", validate_source(replace(source(), evidence_refs=())))

def principles():
    return {
        "p-a": CreativePrinciple("p-a", "a", "retrieval provenance", "retained knowledge", ("stale references",), ("archive:a:README",)),
        "p-b": CreativePrinciple("p-b", "b", "scoped admission", "candidate intake", ("false rejection",), ("archive:b:README",)),
    }

class CandidateEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.sources = {"a": source(), "b": source("b", SHA_B, COMMIT_B)}
        self.principles = principles()
    def test_valid_cross_source_candidate_ready(self): self.assertTrue(evaluate_candidate(candidate(), self.sources, self.principles).ready_for_review)
    def test_same_source_not_cross_source_synthesis(self):
        self.assertIn("CROSS_SOURCE_SYNTHESIS_REQUIRED", evaluate_candidate(candidate(source_ids=("a", "a")), self.sources, self.principles).blockers)
    def test_missing_source_blocks(self):
        self.assertIn("SOURCE_NOT_FOUND:missing", evaluate_candidate(candidate(source_ids=("a", "missing")), self.sources, self.principles).blockers)
    def test_principle_source_binding_mismatch_blocks(self):
        ps = dict(self.principles)
        ps["p-b"] = replace(ps["p-b"], source_id="a")
        self.assertIn("PRINCIPLE_SOURCE_BINDING_MISMATCH", evaluate_candidate(candidate(), self.sources, ps).blockers)
    def test_missing_principle_record_blocks(self):
        self.assertIn("PRINCIPLE_NOT_FOUND:p-b", evaluate_candidate(candidate(), self.sources, {"p-a": self.principles["p-a"]}).blockers)
    def test_source_identity_key_mismatch_blocks(self):
        sources = dict(self.sources); sources["a"] = replace(sources["a"], source_id="wrong")
        self.assertIn("SOURCE_ID_BINDING_MISMATCH:a", evaluate_candidate(candidate(), sources, self.principles).blockers)
    def test_unknown_revision_blocks(self):
        sources = dict(self.sources); sources["b"] = replace(sources["b"], source_revision="")
        self.assertIn("b:UPSTREAM_REVISION_UNVERIFIED", evaluate_candidate(candidate(), sources, self.principles).blockers)
    def test_license_unknown_blocks(self):
        sources = dict(self.sources); sources["a"] = replace(sources["a"], license_status="UNKNOWN")
        self.assertIn("a:LICENSE_NOT_VERIFIED", evaluate_candidate(candidate(), sources, self.principles).blockers)
    def test_unverified_semantics_blocks(self):
        c = replace(candidate(), trust=replace(candidate().trust, semantic_validity="UNKNOWN"))
        self.assertIn("SEMANTIC_VALIDITY_NOT_VERIFIED", evaluate_candidate(c, self.sources, self.principles).blockers)
    def test_missing_experiment_blocks(self):
        self.assertIn("EXPERIMENT_MISSING", evaluate_candidate(candidate(experiment=" "), self.sources, self.principles).blockers)
    def test_missing_evidence_blocks(self):
        self.assertIn("EVIDENCE_REFS_MISSING", evaluate_candidate(candidate(evidence_refs=()), self.sources, self.principles).blockers)
    def test_missing_failure_modes_blocks(self):
        self.assertIn("FAILURE_MODES_MISSING", evaluate_candidate(candidate(failure_modes=()), self.sources, self.principles).blockers)

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.sources = {"a": source(), "b": source("b", SHA_B, COMMIT_B)}
        self.principles = principles()
    def test_draft_to_candidate_structurally_complete(self):
        c = candidate(trust=TrustAssessment())
        out = transition(c, "CANDIDATE", actor_id="author", sources=self.sources, principles=self.principles)
        self.assertEqual(out.lifecycle_status, "CANDIDATE"); self.assertEqual(out.revision, 2)
    def test_cannot_skip_review(self):
        with self.assertRaisesRegex(ValueError, "TRANSITION_NOT_ALLOWED"):
            transition(candidate(), "ACCEPTED", actor_id="author", reviewer_id="reviewer", sources=self.sources, principles=self.principles, evidence_refs=("review:1",))
    def test_review_gate_requires_trust(self):
        c = candidate(lifecycle_status="CANDIDATE", trust=TrustAssessment())
        with self.assertRaisesRegex(ValueError, "REVIEW_GATE_BLOCKED"):
            transition(c, "REVIEW_REQUIRED", actor_id="author", sources=self.sources, principles=self.principles, evidence_refs=("test:1",))
    def test_author_cannot_self_review(self):
        c = candidate(lifecycle_status="REVIEW_REQUIRED")
        with self.assertRaisesRegex(ValueError, "INDEPENDENT_REVIEWER_REQUIRED"):
            transition(c, "ACCEPTED", actor_id="author", reviewer_id="author", sources=self.sources, principles=self.principles, evidence_refs=("review:1",))
    def test_revoke_requires_evidence(self):
        with self.assertRaisesRegex(ValueError, "DECISION_EVIDENCE_REQUIRED"):
            transition(candidate(lifecycle_status="ACCEPTED"), "REVOKED", actor_id="governance", sources=self.sources, principles=self.principles)
    def test_rejected_record_cannot_reopen(self):
        with self.assertRaisesRegex(ValueError, "TRANSITION_NOT_ALLOWED"):
            transition(candidate(lifecycle_status="REJECTED"), "CANDIDATE", actor_id="author", sources=self.sources, principles=self.principles)

if __name__ == "__main__": unittest.main()
