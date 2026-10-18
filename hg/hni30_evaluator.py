"""Fail-closed evidence aggregator for the separate HNI-01..HNI-30 rubric.

This module does not call a model and does not authenticate its own caller.
Runtime verdicts require an independently trusted provenance_verifier callback;
the shipped CLI intentionally supplies no such verifier and therefore blocks
runtime acceptance. Synthetic tests are always labeled SYNTHETIC_ONLY.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable

ORACLE_SCHEMA = "hni30.evaluator-oracle.v1"
BUNDLE_SCHEMA = "hg.hni30.runtime-observation.v1"
ORACLE_VERSION = "hni30.oracle.v1.0.0"
CRITERIA_FILE = "HG-NATIVE-INTELLIGENCE-CRITERIA-DRAFT-V1.md"
EXPECTED_IDS = [f"HNI-{i:02d}" for i in range(1, 31)]
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
VALID_STATUSES = {"PASS", "FAIL", "NOT_RUN", "BLOCKED", "INCONCLUSIVE"}
ARTIFACT_FIELDS = ("input", "output", "trace", "environment")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reject_constant(value: str) -> None:
    raise ValueError("NON_FINITE_JSON_NUMBER")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def strict_json_loads(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("INVALID_JSON") from exc


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def validate_oracle(oracle: Any, criteria_path: Path) -> dict[str, Any]:
    if type(oracle) is not dict or oracle.get("schema_version") != ORACLE_SCHEMA:
        raise ValueError("ORACLE_SCHEMA_INVALID")
    if oracle.get("version") != "1.0.0":
        raise ValueError("ORACLE_VERSION_INVALID")
    entries = oracle.get("oracles")
    if type(entries) is not list or [x.get("criterion_id") for x in entries if type(x) is dict] != EXPECTED_IDS:
        raise ValueError("ORACLE_CRITERION_INVENTORY_INVALID")
    if len(entries) != 30:
        raise ValueError("ORACLE_CRITERION_COUNT_INVALID")
    source = oracle.get("criteria_source")
    if type(source) is not dict or source.get("artifact") != CRITERIA_FILE:
        raise ValueError("ORACLE_SOURCE_REFERENCE_INVALID")
    if not SHA256_RE.fullmatch(str(source.get("sha256", ""))):
        raise ValueError("ORACLE_SOURCE_DIGEST_INVALID")
    if not criteria_path.is_file() or sha256_file(criteria_path) != source["sha256"]:
        raise ValueError("CRITERIA_SOURCE_DIGEST_MISMATCH")
    names = []
    for index, entry in enumerate(entries, 1):
        if type(entry) is not dict:
            raise ValueError("ORACLE_ENTRY_INVALID")
        required = {"oracle_id", "criterion_id", "criterion_name", "oracle_version", "purpose", "method", "positive_case", "negative_case", "positive_expected", "negative_expected", "decision_rule", "evidence_required", "critical_gate"}
        if set(entry) != required:
            raise ValueError("ORACLE_ENTRY_FIELDS_INVALID")
        if entry["oracle_id"] != f"HNIO-{index:02d}" or entry["criterion_id"] != f"HNI-{index:02d}":
            raise ValueError("ORACLE_ID_BINDING_INVALID")
        if entry["oracle_version"] != ORACLE_VERSION:
            raise ValueError("ORACLE_ENTRY_VERSION_MISMATCH")
        if not all(isinstance(entry[k], str) and entry[k].strip() for k in ("oracle_id", "criterion_name", "purpose", "method", "positive_case", "negative_case", "decision_rule")):
            raise ValueError("ORACLE_ENTRY_TEXT_INVALID")
        if not str(entry["positive_expected"]).startswith("PASS") or not str(entry["negative_expected"]).startswith("FAIL"):
            raise ValueError("ORACLE_EXPECTED_RESULT_INVALID")
        if type(entry["critical_gate"]) is not bool or type(entry["evidence_required"]) is not list:
            raise ValueError("ORACLE_ENTRY_POLICY_INVALID")
        if not entry["evidence_required"] or not all(isinstance(x, str) and x for x in entry["evidence_required"]):
            raise ValueError("ORACLE_EVIDENCE_POLICY_INVALID")
        names.append(entry["criterion_name"])
    if len(set(names)) != 30:
        raise ValueError("ORACLE_CRITERION_NAMES_NOT_UNIQUE")
    source_text = criteria_path.read_text(encoding="utf-8")
    for entry in entries:
        marker = f"**{entry['criterion_id']} — {entry['criterion_name']}**"
        if marker not in source_text:
            raise ValueError("ORACLE_CRITERION_NAME_SOURCE_MISMATCH")
    return {
        "valid": True, "criterion_count": 30, "oracle_version": ORACLE_VERSION,
        "oracle_status": oracle.get("status", "MISSING"),
        "criteria_source_sha256": source["sha256"],
        "critical_criteria": [x["criterion_id"] for x in entries if x["critical_gate"]],
    }


def load_oracle(oracle_path: Path, criteria_path: Path) -> dict[str, Any]:
    oracle = strict_json_loads(oracle_path.read_bytes())
    validate_oracle(oracle, criteria_path)
    return oracle


def _safe_artifact(root: Path, ref: Any) -> tuple[bool, str]:
    if type(ref) is not dict or set(ref) != {"path", "sha256"}:
        return False, "ARTIFACT_REFERENCE_INVALID"
    rel, digest = ref["path"], ref["sha256"]
    if not isinstance(rel, str) or not rel or not SHA256_RE.fullmatch(str(digest)):
        return False, "ARTIFACT_REFERENCE_INVALID"
    candidate = Path(rel)
    if candidate.is_absolute() or any(part in ("", ".", "..") for part in candidate.parts):
        return False, "ARTIFACT_PATH_NOT_RELATIVE_SAFE"
    root_real, target = root.resolve(), root / candidate
    try:
        cursor = root
        for part in candidate.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                return False, "ARTIFACT_SYMLINK_REJECTED"
        target_real = target.resolve(strict=True)
        if os.path.commonpath((str(root_real), str(target_real))) != str(root_real):
            return False, "ARTIFACT_PATH_ESCAPES_ROOT"
        if not target_real.is_file():
            return False, "ARTIFACT_NOT_REGULAR_FILE"
        if sha256_file(target_real) != digest:
            return False, "ARTIFACT_DIGEST_MISMATCH"
    except (OSError, ValueError):
        return False, "ARTIFACT_MISSING_OR_UNREADABLE"
    return True, "OK"


def _valid_runtime_build(build: Any) -> bool:
    if type(build) is not dict:
        return False
    required = {"build_id", "source_commit", "source_tree_sha256", "runtime_source_sha256", "config_sha256", "environment_sha256", "model_provider", "model_id", "endpoint_host", "nonsecret_model_config_sha256"}
    if not required.issubset(build) or not isinstance(build["build_id"], str) or not build["build_id"].strip():
        return False
    if not COMMIT_RE.fullmatch(str(build["source_commit"])):
        return False
    if not all(isinstance(build[k], str) and build[k].strip() for k in ("model_provider", "model_id", "endpoint_host")):
        return False
    return all(SHA256_RE.fullmatch(str(build[k])) for k in ("source_tree_sha256", "runtime_source_sha256", "config_sha256", "environment_sha256", "nonsecret_model_config_sha256"))


def _validate_observation(row: dict[str, Any], entry: dict[str, Any], root: Path, bundle: dict[str, Any]) -> tuple[bool, str]:
    if row.get("oracle_version") != entry["oracle_version"]:
        return False, "OBSERVATION_ORACLE_VERSION_MISMATCH"
    if not isinstance(row.get("case_id"), str) or not row["case_id"].strip():
        return False, "CASE_ID_MISSING"
    if row.get("runtime_build_identity") != bundle["runtime_build"]["build_id"]:
        return False, "RUNTIME_BUILD_IDENTITY_MISMATCH"
    if row.get("criteria_source_sha256") != bundle.get("criteria_source_sha256"):
        return False, "CRITERIA_SOURCE_DIGEST_MISMATCH"
    if not isinstance(row.get("observed_at"), str) or not row["observed_at"].strip():
        return False, "OBSERVATION_TIME_MISSING"
    assertions = row.get("assertions")
    if type(assertions) is not list or not assertions:
        return False, "ASSERTIONS_MISSING"
    if any(type(a) is not dict or set(a) != {"assertion_id", "passed"} or not isinstance(a["assertion_id"], str) or not a["assertion_id"].strip() or type(a["passed"]) is not bool for a in assertions):
        return False, "ASSERTION_SCHEMA_INVALID"
    review = row.get("review")
    if type(review) is not dict or not all(isinstance(review.get(k), str) and review[k].strip() for k in ("method", "reviewer_id", "decision")):
        return False, "REVIEW_RECORD_MISSING"
    if review["decision"] != row["status"]:
        return False, "REVIEW_DECISION_MISMATCH"
    if row["status"] == "PASS" and not all(a["passed"] for a in assertions):
        return False, "PASS_CONTRADICTS_ASSERTIONS"
    if row["status"] == "FAIL" and all(a["passed"] for a in assertions):
        return False, "FAIL_CONTRADICTS_ASSERTIONS"
    for field in ARTIFACT_FIELDS:
        ok, reason = _safe_artifact(root, row.get(field))
        if not ok:
            return False, f"{field.upper()}_{reason}"
    if row["environment"]["sha256"] != bundle["runtime_build"]["environment_sha256"]:
        return False, "ENVIRONMENT_DIGEST_DOES_NOT_MATCH_BUILD"
    return True, "EVIDENCE_REFERENCES_AND_ASSERTIONS_VALID"


def evaluate_bundle(bundle: Any, oracle: dict[str, Any], criteria_path: Path, evidence_root: Path, *, provenance_verifier: Callable[[dict[str, Any]], bool] | None = None, review_verifier: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], bool] | None = None) -> dict[str, Any]:
    """Evaluate a bundle; no runtime PASS/FAIL without a trusted verifier.

    The callback must independently verify the source/build attestation and bind
    it to this exact bundle, including its captured runtime identity. The shipped CLI
    does not provide one, so runtime runs fail closed by default.
    """
    validation = validate_oracle(oracle, criteria_path)
    if type(bundle) is not dict or bundle.get("schema_version") != BUNDLE_SCHEMA:
        raise ValueError("OBSERVATION_BUNDLE_SCHEMA_INVALID")
    run_kind = bundle.get("run_kind")
    if run_kind not in {"SYNTHETIC_TEST", "HG_RUNTIME"}:
        raise ValueError("RUN_KIND_INVALID")
    if bundle.get("oracle_version") != ORACLE_VERSION:
        raise ValueError("BUNDLE_ORACLE_VERSION_MISMATCH")
    if bundle.get("criteria_source_sha256") != validation["criteria_source_sha256"]:
        raise ValueError("BUNDLE_CRITERIA_SOURCE_DIGEST_MISMATCH")
    build, observations = bundle.get("runtime_build"), bundle.get("observations", [])
    if type(observations) is not list:
        raise ValueError("OBSERVATIONS_NOT_ARRAY")
    by_id = {}
    seen_case_ids = set()
    for row in observations:
        if type(row) is not dict:
            raise ValueError("OBSERVATION_NOT_OBJECT")
        cid = row.get("criterion_id")
        if cid not in EXPECTED_IDS or cid in by_id:
            raise ValueError("OBSERVATION_UNKNOWN_OR_DUPLICATE_CRITERION")
        if row.get("status") not in VALID_STATUSES:
            raise ValueError("OBSERVATION_STATUS_INVALID")
        case_id = row.get("case_id")
        if case_id is not None:
            if not isinstance(case_id, str) or case_id in seen_case_ids:
                raise ValueError("OBSERVATION_CASE_ID_INVALID_OR_DUPLICATE")
            seen_case_ids.add(case_id)
        by_id[cid] = row
    approved = oracle.get("status") == "APPROVED_FOR_RUNTIME"
    build_valid = _valid_runtime_build(build)
    try:
        provenance_verified = bool(run_kind == "HG_RUNTIME" and build_valid and provenance_verifier is not None and provenance_verifier(bundle) is True)
    except Exception:
        provenance_verified = False
    findings = []
    for entry in oracle["oracles"]:
        cid = entry["criterion_id"]
        observation = by_id.get(cid)
        supplied = observation.get("status") if observation else "NOT_RUN"
        effective, reason = supplied, "OBSERVATION_PRESENT"
        if observation is None:
            effective, reason = "NOT_RUN", "NO_RUNTIME_OBSERVATION"
        elif supplied in {"PASS", "FAIL"}:
            if run_kind == "SYNTHETIC_TEST":
                reason = "SYNTHETIC_CASE_ONLY_NOT_HG_VERDICT"
            elif not approved:
                effective, reason = "BLOCKED", "ORACLE_NOT_APPROVED_FOR_RUNTIME"
            elif not build_valid:
                effective, reason = "BLOCKED", "RUNTIME_BUILD_IDENTITY_INVALID"
            elif not provenance_verified:
                effective, reason = "BLOCKED", "RUNTIME_PROVENANCE_NOT_VERIFIED"
            elif review_verifier is None:
                effective, reason = "BLOCKED", "REVIEW_PROVENANCE_NOT_VERIFIED"
            else:
                try:
                    review_verified = review_verifier(observation.get("review", {}), observation, entry) is True
                except Exception:
                    review_verified = False
                if not review_verified:
                    effective, reason = "BLOCKED", "REVIEW_PROVENANCE_NOT_VERIFIED"
                else:
                    ok, reason = _validate_observation(observation, entry, evidence_root, bundle)
                    if not ok:
                        effective = "BLOCKED"
        elif supplied == "INCONCLUSIVE":
            reason = "EXECUTED_EVIDENCE_CANNOT_DECIDE"
        elif supplied == "BLOCKED":
            reason = str(observation.get("reason", "PREREQUISITE_OR_EVIDENCE_MISSING"))[:160]
        findings.append({
            "criterion_id": cid, "oracle_id": entry["oracle_id"], "critical_gate": entry["critical_gate"],
            "supplied_status": supplied, "effective_status": effective, "reason": reason,
            "evidence_verified_by_this_evaluator": bool(effective in {"PASS", "FAIL"} and run_kind == "HG_RUNTIME" and provenance_verified and approved and review_verifier is not None),
        })
    if run_kind == "SYNTHETIC_TEST":
        suite = "SYNTHETIC_ONLY"
    elif not approved or not build_valid or not provenance_verified:
        suite = "BLOCKED"
    elif any(x["effective_status"] == "FAIL" and x["critical_gate"] for x in findings):
        suite = "FAIL"
    elif any(x["effective_status"] in {"BLOCKED", "NOT_RUN", "INCONCLUSIVE"} for x in findings):
        suite = "BLOCKED"
    elif any(x["effective_status"] == "FAIL" for x in findings):
        suite = "FAIL"
    else:
        suite = "PASS"
    counts = {s: sum(x["effective_status"] == s for x in findings) for s in ("PASS", "FAIL", "NOT_RUN", "BLOCKED", "INCONCLUSIVE")}
    return {
        "schema_version": "hg.hni30.evaluation-result.v1",
        "classification": "SYNTHETIC_CONTRACT_TEST" if run_kind == "SYNTHETIC_TEST" else "RUNTIME_EVIDENCE_AGGREGATION",
        "run_kind": run_kind, "oracle_version": ORACLE_VERSION, "oracle_status": oracle.get("status"),
        "criteria_source_sha256": validation["criteria_source_sha256"],
        "runtime_build_identity_present": build_valid, "runtime_provenance_verified": provenance_verified, "review_verifier_available": review_verifier is not None,
        "evaluation_status": suite, "release_authorized": False, "counts": counts, "findings": findings,
        "trust_note": "Synthetic contract results are not HG runtime verdicts." if run_kind == "SYNTHETIC_TEST" else "Runtime PASS/FAIL requires independently trusted build provenance and review-verification callbacks. Raw artifacts are digest-checked; release authorization is always false.",
    }


def load_bundle(path: Path) -> Any:
    return strict_json_loads(path.read_bytes())
