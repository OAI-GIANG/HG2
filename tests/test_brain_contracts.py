"""Negative and contract tests for HG's unified Brain request/result envelopes."""
import unittest
from hg.contracts import (
    BRAIN_REQUEST_V1, BRAIN_REQUEST_AUDIT_V1, CAPABILITY_RESULT_V1, ContractError,
    canonical_digest, validate_brain_request, validate_brain_request_audit, validate_capability_result,
)


class BrainContractTests(unittest.TestCase):
    def request(self, **updates):
        value = {
            "schema_version": BRAIN_REQUEST_V1,
            "request_id": "req-1",
            "correlation_id": "corr-1",
            "goal": "test goal",
            "constraints": {},
            "source_revision": "f" * 40,
        }
        value.update(updates)
        return value

    def result(self, **updates):
        value = {
            "schema_version": CAPABILITY_RESULT_V1,
            "request_id": "req-1",
            "correlation_id": "corr-1",
            "status": "SUCCESS",
            "output_digest": canonical_digest({"answer": "ok"}),
            "error_code": None,
            "evidence_refs": ["evidence:sha256:" + "a" * 64],
            "source_revision": "f" * 40,
        }
        value.update(updates)
        return value

    def test_request_v1_validates(self):
        self.assertEqual(validate_brain_request(self.request())["request_id"], "req-1")

    def test_request_unknown_version_missing_field_and_wrong_schema_fail_closed(self):
        with self.assertRaisesRegex(ContractError, "UNSUPPORTED_BRAIN_REQUEST_VERSION"):
            validate_brain_request(self.request(schema_version="HG_BRAIN_REQUEST_V99"))
        with self.assertRaisesRegex(ContractError, "BRAIN_REQUEST_SCHEMA_INVALID"):
            validate_brain_request({k: v for k, v in self.request().items() if k != "correlation_id"})
        with self.assertRaisesRegex(ContractError, "BRAIN_REQUEST_CONSTRAINTS_INVALID"):
            validate_brain_request(self.request(constraints=[]))

    def test_redacted_brain_request_audit_contract_is_versioned_and_strict(self):
        audit = {
            "schema_version": BRAIN_REQUEST_AUDIT_V1,
            "request_id": "req-1",
            "correlation_id": "corr-1",
            "goal_sha256": canonical_digest({"goal": "test goal"}),
            "constraints_sha256": canonical_digest({}),
            "source_revision": "RUNTIME_REVISION_UNATTESTED",
            "status": "ACCEPTED",
        }
        self.assertEqual(validate_brain_request_audit(audit)["status"], "ACCEPTED")
        bad = dict(audit, schema_version="HG_BRAIN_REQUEST_V1")
        with self.assertRaisesRegex(ContractError, "UNSUPPORTED_BRAIN_REQUEST_AUDIT_VERSION"):
            validate_brain_request_audit(bad)
        bad = dict(audit, goal_sha256="not-a-digest")
        with self.assertRaisesRegex(ContractError, "BRAIN_REQUEST_AUDIT_DIGEST_INVALID"):
            validate_brain_request_audit(bad)

    def test_result_success_requires_digest_and_source_evidence(self):
        self.assertEqual(validate_capability_result(self.result(), evidence_verifier=lambda _ref: True)["status"], "SUCCESS")
        for override, code in (
            ({"output_digest": None}, "CAPABILITY_SUCCESS_PROVENANCE_REQUIRED"),
            ({"evidence_refs": []}, "CAPABILITY_SUCCESS_PROVENANCE_REQUIRED"),
            ({"error_code": "CONFLICT"}, "CAPABILITY_SUCCESS_PROVENANCE_REQUIRED"),
        ):
            with self.subTest(override=override), self.assertRaisesRegex(ContractError, code):
                validate_capability_result(self.result(**override))

    def test_response_only_status_cannot_claim_verified_execution(self):
        valid = self.result(
            status="RESPONSE_ONLY", error_code="PROVIDER_RESPONSE_ONLY_NOT_EXECUTION_PROOF",
            evidence_refs=[],
        )
        self.assertEqual(validate_capability_result(valid)["status"], "RESPONSE_ONLY")
        for overrides in (
            {"error_code": None},
            {"evidence_refs": ["evidence:sha256:" + "a" * 64]},
            {"output_digest": None},
        ):
            candidate = dict(valid)
            candidate.update(overrides)
            with self.subTest(overrides=overrides), self.assertRaisesRegex(ContractError, "CAPABILITY_RESPONSE_ONLY_CONTRACT_INVALID"):
                validate_capability_result(candidate)

    def test_result_must_match_expected_request_correlation_and_revision(self):
        base = self.result(status="NOT_RUN", error_code="NOT_EXECUTED", evidence_refs=[])
        with self.assertRaisesRegex(ContractError, "CAPABILITY_RESULT_REQUEST_ID_MISMATCH"):
            validate_capability_result(base, expected_request_id="other")
        with self.assertRaisesRegex(ContractError, "CAPABILITY_RESULT_CORRELATION_ID_MISMATCH"):
            validate_capability_result(base, expected_correlation_id="other")
        with self.assertRaisesRegex(ContractError, "CAPABILITY_RESULT_SOURCE_REVISION_MISMATCH"):
            validate_capability_result(base, expected_source_revision="other")

    def test_success_cannot_use_an_unattested_runtime_revision(self):
        with self.assertRaisesRegex(ContractError, "CAPABILITY_SUCCESS_SOURCE_REVISION_UNATTESTED"):
            validate_capability_result(
                self.result(source_revision="RUNTIME_REVISION_UNATTESTED"),
                evidence_verifier=lambda _ref: True,
            )

    def test_result_rejects_forged_status_unknown_fields_and_missing_failure_reason(self):
        with self.assertRaisesRegex(ContractError, "CAPABILITY_RESULT_STATUS_INVALID"):
            validate_capability_result(self.result(status="LOOKS_GOOD"))
        with self.assertRaisesRegex(ContractError, "CAPABILITY_RESULT_SCHEMA_INVALID"):
            validate_capability_result(self.result(extra="forged"))
        with self.assertRaisesRegex(ContractError, "CAPABILITY_FAILURE_REASON_REQUIRED"):
            validate_capability_result(self.result(status="BLOCKED", output_digest=None, evidence_refs=[], error_code=None))

    def test_success_fails_closed_without_a_trusted_evidence_verifier(self):
        with self.assertRaisesRegex(ContractError, "CAPABILITY_EVIDENCE_VERIFIER_REQUIRED"):
            validate_capability_result(self.result())
        with self.assertRaisesRegex(ContractError, "CAPABILITY_EVIDENCE_REFERENCE_UNVERIFIED"):
            validate_capability_result(self.result(), evidence_verifier=lambda _ref: False)
        with self.assertRaisesRegex(ContractError, "CAPABILITY_EVIDENCE_REFERENCE_UNVERIFIED"):
            validate_capability_result(self.result(), evidence_verifier=lambda _ref: (_ for _ in ()).throw(RuntimeError("unavailable")))

    def test_result_rejects_forged_success_evidence_locator(self):
        with self.assertRaisesRegex(ContractError, "CAPABILITY_SUCCESS_EVIDENCE_REFERENCE_INVALID"):
            validate_capability_result(self.result(evidence_refs=["provider-says-it-is-verified"]))
        with self.assertRaisesRegex(ContractError, "CAPABILITY_SUCCESS_TEST_ARTIFACT_NOT_RUNTIME_PROOF"):
            validate_capability_result(self.result(evidence_refs=["test-artifact:sha256:" + "b" * 64]))

    def test_result_rejects_bad_correlation_revision_and_evidence(self):
        with self.assertRaisesRegex(ContractError, "CORRELATION_ID_REQUIRED"):
            validate_capability_result(self.result(correlation_id=" "))
        with self.assertRaisesRegex(ContractError, "CAPABILITY_RESULT_EVIDENCE_INVALID"):
            validate_capability_result(self.result(evidence_refs=[" "]))
        with self.assertRaisesRegex(ContractError, "CAPABILITY_RESULT_DIGEST_INVALID"):
            validate_capability_result(self.result(output_digest="not-a-digest"))


if __name__ == "__main__":
    unittest.main()
