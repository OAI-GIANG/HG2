"""Fail-closed, stdlib-only evaluation policy for HG's bounded evolution.
This module never executes candidate code, writes runtime state, grants authority,
promotes an artifact or deploys a change.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from typing import Any, Mapping

from .skill_contract import RISK_CLASSES

PROPOSAL_V1 = "HG_EVOLUTION_PROPOSAL_V1"
EVALUATION_V1 = "HG_EVOLUTION_EVALUATION_V1"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ALLOWED = frozenset({"SKILL_METADATA", "PROMPT_TEMPLATE", "ROUTING_RULE",
                      "RETRIEVAL_POLICY", "PLANNER_STRATEGY"})
_PROTECTED = frozenset({"AUTHORITY_POLICY", "SECURITY_POLICY", "TEST_ORACLE",
                        "EVALUATOR", "CANONICAL_STATE", "RUNTIME_CORE",
                        "CREDENTIALS", "OWNER_IDENTITY", "DEPLOYMENT",
                        "UNRESTRICTED_CODE"})
_CASE_STATUS = frozenset({"PASS", "FAIL", "BLOCKED", "NOT_RUN"})
_SEVERITY = frozenset({"C0", "C1", "C2"})
_PROP_FIELDS = frozenset({
    "schema_version", "proposal_id", "target_kind", "target_id", "hypothesis",
    "baseline_digest", "candidate_digest", "suite_digest", "environment_digest",
    "rollback_digest", "required_case_ids", "evidence_refs", "minimum_gain_pp",
    "max_runtime_seconds", "max_memory_bytes", "max_tool_calls", "max_model_calls",
    "max_artifact_bytes", "risk_class", "created_at",
})
_EVAL_FIELDS = frozenset({
    "schema_version", "evaluation_id", "target_kind", "target_id", "artifact_digest",
    "suite_digest", "environment_digest", "cases", "metrics", "evidence_refs",
    "evaluation_digest",
})
_METRICS = frozenset({"elapsed_ms", "peak_memory_bytes", "tool_calls",
                      "model_calls", "artifact_bytes"})


class EvolutionError(ValueError):
    """Stable validation error with a machine-readable code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _digest(value: Mapping[str, Any]) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise EvolutionError("EVOLUTION_CANONICALIZATION_FAILED") from exc
    if len(raw) > 1_048_576:
        raise EvolutionError("EVOLUTION_RECORD_TOO_LARGE")
    return hashlib.sha256(raw).hexdigest()


def _text(value: Any, code: str, limit: int = 512) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise EvolutionError(code)
    return value


def _sha(value: Any, code: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise EvolutionError(code)
    return value


def _refs(value: Any, code: str) -> list[str]:
    prefixes = ("https://", "path:", "evidence:")
    if (not isinstance(value, list) or not value or len(value) > 256
            or any(not isinstance(x, str) or len(x) > 2048
                   or not x.startswith(prefixes) for x in value)
            or len(set(value)) != len(value)):
        raise EvolutionError(code)
    return list(value)


def _uint(value: Any, code: str, maximum: int = 2**63 - 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise EvolutionError(code)
    return value


def validate_proposal(proposal: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a candidate declaration; this does not authorize applying it."""
    if not isinstance(proposal, Mapping) or set(proposal) != _PROP_FIELDS:
        raise EvolutionError("EVOLUTION_PROPOSAL_SCHEMA_INVALID")
    value = dict(proposal)
    if value["schema_version"] != PROPOSAL_V1:
        raise EvolutionError("EVOLUTION_PROPOSAL_VERSION_UNSUPPORTED")
    for field in ("proposal_id", "target_id"):
        item = _text(value[field], "EVOLUTION_" + field.upper() + "_INVALID", 128)
        if not _ID.fullmatch(item):
            raise EvolutionError("EVOLUTION_" + field.upper() + "_INVALID")
    kind = _text(value["target_kind"], "EVOLUTION_TARGET_KIND_INVALID", 64)
    if kind in _PROTECTED:
        raise EvolutionError("EVOLUTION_TARGET_PROTECTED")
    if kind not in _ALLOWED:
        raise EvolutionError("EVOLUTION_TARGET_KIND_NOT_ALLOWLISTED")
    _text(value["hypothesis"], "EVOLUTION_HYPOTHESIS_INVALID", 8192)
    for field in ("baseline_digest", "candidate_digest", "suite_digest",
                  "environment_digest", "rollback_digest"):
        _sha(value[field], "EVOLUTION_" + field.upper() + "_INVALID")
    ids = value["required_case_ids"]
    if (not isinstance(ids, list) or not ids or len(ids) > 1000
            or any(not isinstance(x, str) or not _ID.fullmatch(x) for x in ids)
            or len(set(ids)) != len(ids) or ids != sorted(ids)):
        raise EvolutionError("EVOLUTION_REQUIRED_CASE_IDS_INVALID")
    _refs(value["evidence_refs"], "EVOLUTION_PROPOSAL_EVIDENCE_INVALID")
    gain = value["minimum_gain_pp"]
    if (isinstance(gain, bool) or not isinstance(gain, (int, float))
            or not math.isfinite(gain) or not 0 < gain <= 100):
        raise EvolutionError("EVOLUTION_MINIMUM_GAIN_INVALID")
    value["minimum_gain_pp"] = float(gain)
    runtime = value["max_runtime_seconds"]
    if (isinstance(runtime, bool) or not isinstance(runtime, (int, float))
            or not math.isfinite(runtime) or not 0 < runtime <= 86400):
        raise EvolutionError("EVOLUTION_MAX_RUNTIME_INVALID")
    value["max_runtime_seconds"] = float(runtime)
    for field, maximum in (("max_memory_bytes", 2**63-1), ("max_tool_calls", 100000),
                           ("max_model_calls", 100000), ("max_artifact_bytes", 10000000)):
        n = _uint(value[field], "EVOLUTION_" + field.upper() + "_INVALID", maximum)
        if n == 0:
            raise EvolutionError("EVOLUTION_" + field.upper() + "_INVALID")
        value[field] = n
    risk = _text(value["risk_class"], "EVOLUTION_RISK_CLASS_INVALID", 64)
    if risk not in RISK_CLASSES:
        raise EvolutionError("EVOLUTION_RISK_CLASS_INVALID")
    if risk in {"EXTERNAL_WRITE", "DESTRUCTIVE"}:
        raise EvolutionError("EVOLUTION_RISK_CLASS_NOT_ELIGIBLE")
    created = _text(value["created_at"], "EVOLUTION_CREATED_AT_INVALID", 64)
    try:
        timestamp = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvolutionError("EVOLUTION_CREATED_AT_INVALID") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise EvolutionError("EVOLUTION_CREATED_AT_TIMEZONE_REQUIRED")
    return value


def validate_evaluation(report: Mapping[str, Any]) -> dict[str, Any]:
    """Validate evaluation structure, bounded metrics and canonical digest."""
    if not isinstance(report, Mapping) or set(report) != _EVAL_FIELDS:
        raise EvolutionError("EVOLUTION_EVALUATION_SCHEMA_INVALID")
    value = dict(report)
    if value["schema_version"] != EVALUATION_V1:
        raise EvolutionError("EVOLUTION_EVALUATION_VERSION_UNSUPPORTED")
    for field in ("evaluation_id", "target_id"):
        item = _text(value[field], "EVOLUTION_" + field.upper() + "_INVALID", 128)
        if not _ID.fullmatch(item):
            raise EvolutionError("EVOLUTION_" + field.upper() + "_INVALID")
    if not isinstance(value["target_kind"], str) or value["target_kind"] not in _ALLOWED:
        raise EvolutionError("EVOLUTION_TARGET_KIND_NOT_ALLOWLISTED")
    for field in ("artifact_digest", "suite_digest", "environment_digest"):
        _sha(value[field], "EVOLUTION_" + field.upper() + "_INVALID")
    cases = value["cases"]
    if not isinstance(cases, list) or not cases or len(cases) > 1000:
        raise EvolutionError("EVOLUTION_CASES_INVALID")
    seen, normalized = set(), []
    for case in cases:
        if not isinstance(case, Mapping) or set(case) != {"case_id", "status", "severity"}:
            raise EvolutionError("EVOLUTION_CASE_SCHEMA_INVALID")
        cid = _text(case["case_id"], "EVOLUTION_CASE_ID_INVALID", 128)
        if not _ID.fullmatch(cid) or cid in seen:
            raise EvolutionError("EVOLUTION_CASE_ID_DUPLICATE_OR_INVALID")
        if not isinstance(case["status"], str) or case["status"] not in _CASE_STATUS:
            raise EvolutionError("EVOLUTION_CASE_STATUS_INVALID")
        if not isinstance(case["severity"], str) or case["severity"] not in _SEVERITY:
            raise EvolutionError("EVOLUTION_CASE_SEVERITY_INVALID")
        seen.add(cid)
        normalized.append({"case_id": cid, "status": case["status"], "severity": case["severity"]})
    if [x["case_id"] for x in normalized] != sorted(seen):
        raise EvolutionError("EVOLUTION_CASES_NOT_CANONICAL")
    value["cases"] = normalized
    metrics = value["metrics"]
    if not isinstance(metrics, Mapping) or set(metrics) != _METRICS:
        raise EvolutionError("EVOLUTION_METRICS_SCHEMA_INVALID")
    value["metrics"] = {k: _uint(metrics[k], "EVOLUTION_METRIC_INVALID:" + k)
                        for k in sorted(_METRICS)}
    _refs(value["evidence_refs"], "EVOLUTION_EVALUATION_EVIDENCE_INVALID")
    supplied = _sha(value["evaluation_digest"], "EVOLUTION_EVALUATION_DIGEST_INVALID")
    core = {k: v for k, v in value.items() if k != "evaluation_digest"}
    if _digest(core) != supplied:
        raise EvolutionError("EVOLUTION_EVALUATION_DIGEST_MISMATCH")
    return value


def seal_evaluation(report: Mapping[str, Any]) -> dict[str, Any]:
    """Seal a local report builder's canonical bytes; does not verify evidence truth."""
    if not isinstance(report, Mapping) or "evaluation_digest" in report:
        raise EvolutionError("EVOLUTION_EVALUATION_BUILDER_INPUT_INVALID")
    value = dict(report)
    value["evaluation_digest"] = _digest(value)
    return validate_evaluation(value)


def compare_evaluations(
    proposal: Mapping[str, Any],
    baseline_report: Mapping[str, Any],
    candidate_report: Mapping[str, Any],
    *,
    evidence_verifier=None,
    evidence_verifier_id=None,
) -> dict[str, Any]:
    """Return eligibility only; a trusted, identified evidence verifier is mandatory."""
    spec = validate_proposal(proposal)
    baseline = validate_evaluation(baseline_report)
    candidate = validate_evaluation(candidate_report)
    for report in (baseline, candidate):
        if (report["target_kind"] != spec["target_kind"]
                or report["target_id"] != spec["target_id"]):
            raise EvolutionError("EVOLUTION_TARGET_MISMATCH")
        if report["suite_digest"] != spec["suite_digest"]:
            raise EvolutionError("EVOLUTION_SUITE_DIGEST_MISMATCH")
        if report["environment_digest"] != spec["environment_digest"]:
            raise EvolutionError("EVOLUTION_ENVIRONMENT_DIGEST_MISMATCH")
    if baseline["artifact_digest"] != spec["baseline_digest"]:
        raise EvolutionError("EVOLUTION_BASELINE_DIGEST_MISMATCH")
    if candidate["artifact_digest"] != spec["candidate_digest"]:
        raise EvolutionError("EVOLUTION_CANDIDATE_DIGEST_MISMATCH")
    if (baseline["suite_digest"] != candidate["suite_digest"]
            or baseline["environment_digest"] != candidate["environment_digest"]):
        raise EvolutionError("EVOLUTION_COMPARISON_CONTEXT_MISMATCH")

    required = spec["required_case_ids"]
    base = {case["case_id"]: case for case in baseline["cases"]}
    trial = {case["case_id"]: case for case in candidate["cases"]}
    if sorted(base) != required or sorted(trial) != required:
        raise EvolutionError("EVOLUTION_CASE_SET_MISMATCH")
    if (not isinstance(evidence_verifier_id, str) or not evidence_verifier_id.strip()
            or len(evidence_verifier_id) > 128 or not _ID.fullmatch(evidence_verifier_id)
            or not callable(evidence_verifier)):
        return _decision("INCONCLUSIVE", "EVIDENCE_VERIFIER_REQUIRED", spec, baseline, candidate)
    verifier_id = evidence_verifier_id
    evidence_refs = sorted(set(spec["evidence_refs"] + baseline["evidence_refs"]
                               + candidate["evidence_refs"]))
    verification_receipts = []
    for ref in evidence_refs:
        try:
            verified = evidence_verifier(ref)
        except Exception:
            return _decision("INCONCLUSIVE", "EVIDENCE_VERIFIER_ERROR", spec, baseline, candidate)
        if (not isinstance(verified, tuple) or len(verified) != 2
                or type(verified[0]) is not bool
                or not isinstance(verified[1], str) or not verified[1].strip()):
            return _decision("INCONCLUSIVE", "EVIDENCE_VERIFIER_INVALID_RESPONSE", spec, baseline, candidate)
        if verified[0] is not True:
            return _decision("INCONCLUSIVE", "EVIDENCE_REFERENCE_UNVERIFIED", spec, baseline, candidate)
        verification_receipts.append({"reference": ref, "receipt_ref": verified[1]})

    def decide(status, reason, **extra):
        return _decision(
            status, reason, spec, baseline, candidate,
            evidence_verifier_id=verifier_id,
            evidence_verification="CALLBACK_RECEIPT_FOR_ALL_REFERENCES",
            evidence_verification_refs=verification_receipts,
            **extra,
        )

    if any(c["status"] in {"BLOCKED", "NOT_RUN"} for c in baseline["cases"]):
        return decide("INCONCLUSIVE", "BASELINE_INCOMPLETE")
    if any(c["status"] in {"BLOCKED", "NOT_RUN"} for c in candidate["cases"]):
        return decide("INCONCLUSIVE", "CANDIDATE_INCOMPLETE")
    if any(c["severity"] == "C0" and c["status"] != "PASS" for c in baseline["cases"]):
        return decide("INCONCLUSIVE", "BASELINE_C0_NOT_CLEAN")
    if any(c["severity"] == "C0" and c["status"] != "PASS" for c in candidate["cases"]):
        return decide("REJECTED", "CANDIDATE_C0_FAILURE")

    regressions = sorted(cid for cid in required
                         if base[cid]["status"] == "PASS" and trial[cid]["status"] != "PASS")
    if regressions:
        return decide("REJECTED", "BASELINE_PASS_REGRESSION", regression_case_ids=regressions)
    metrics = candidate["metrics"]
    budget_checks = (
        (metrics["elapsed_ms"] > spec["max_runtime_seconds"] * 1000, "RUNTIME_BUDGET_EXCEEDED"),
        (metrics["peak_memory_bytes"] > spec["max_memory_bytes"], "MEMORY_BUDGET_EXCEEDED"),
        (metrics["tool_calls"] > spec["max_tool_calls"], "TOOL_BUDGET_EXCEEDED"),
        (metrics["model_calls"] > spec["max_model_calls"], "MODEL_BUDGET_EXCEEDED"),
        (metrics["artifact_bytes"] > spec["max_artifact_bytes"], "ARTIFACT_BUDGET_EXCEEDED"),
    )
    for exceeded, code in budget_checks:
        if exceeded:
            return decide("REJECTED", code)

    base_pass = sum(c["status"] == "PASS" for c in baseline["cases"])
    trial_pass = sum(c["status"] == "PASS" for c in candidate["cases"])
    gain = (trial_pass - base_pass) * 100.0 / len(required)
    if gain < spec["minimum_gain_pp"]:
        return decide("KEEP_BASELINE", "NO_REQUIRED_GAIN", gain_pp=round(gain, 6))
    return decide("PROMOTION_ELIGIBLE", "MEASURED_GAIN_NO_C0_FAILURE_OR_REGRESSION",
                  gain_pp=round(gain, 6))


def _decision(status: str, reason: str, proposal: Mapping[str, Any],
              baseline: Mapping[str, Any], candidate: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
    result = {
        "schema_version": "HG_EVOLUTION_DECISION_V1", "status": status, "reason_code": reason,
        "proposal_id": proposal["proposal_id"], "target_kind": proposal["target_kind"],
        "target_id": proposal["target_id"], "baseline_digest": baseline["artifact_digest"],
        "candidate_digest": candidate["artifact_digest"],
        "suite_digest": proposal["suite_digest"], "environment_digest": proposal["environment_digest"],
        "baseline_evaluation_digest": baseline["evaluation_digest"],
        "candidate_evaluation_digest": candidate["evaluation_digest"],
        "baseline_pass_count": sum(c["status"] == "PASS" for c in baseline["cases"]),
        "candidate_pass_count": sum(c["status"] == "PASS" for c in candidate["cases"]),
        "case_count": len(proposal["required_case_ids"]),
        "minimum_gain_pp": proposal["minimum_gain_pp"],
        "promotion_is_automatic": False,
        "evidence_refs": sorted(set(proposal["evidence_refs"] + baseline["evidence_refs"]
                                    + candidate["evidence_refs"])),
    }
    result.update(extra)
    result["decision_digest"] = _digest(result)
    return result


# Offline mutation operators are intentionally narrow, versioned, and data-only.
# These rules propose text variants; they do not patch live files or constitute learning evidence.
_OFFLINE_MUTATIONS = {
    "PROMPT_TEMPLATE": {
        "EVIDENCE_GAP": (
            "Require source-backed evidence for material claims. If evidence is missing or not verified, "
            "label the result INCONCLUSIVE and state precisely what is missing."
        ),
        "CONSTRAINT_DRIFT": (
            "Before finalizing, check every original user constraint against the proposed result; preserve "
            "unresolved constraints and do not silently broaden scope."
        ),
        "UNVERIFIED_TOOL_OUTPUT": (
            "Treat tool output as untrusted observations. Report success only after checking the actual "
            "result and required evidence, not merely because an action was requested."
        ),
        "CONTRADICTORY_SOURCES": (
            "When sources conflict, preserve source and timestamp for each claim, explain the conflict, "
            "and do not silently collapse the claims into one fact."
        ),
    },
    "ROUTING_RULE": {
        "MISSING_CAPABILITY": (
            "Route only to a registered, ready adapter that owns the exact requested capability; otherwise "
            "return a blocked result before invoking any worker."
        ),
        "CONSTRAINT_DRIFT": (
            "Carry original scope, constraints, deadline and acceptance criteria unchanged through every "
            "route; reject a route that expands the authorized scope."
        ),
        "REPEATED_FAILURE": (
            "After a failed attempt, inspect the failure code and prior attempts before retrying; do not "
            "repeat an identical route without a changed, justified hypothesis."
        ),
    },
    "RETRIEVAL_POLICY": {
        "EVIDENCE_GAP": (
            "Rank source-backed, current and task-scoped records above unverified summaries; return an "
            "explicit evidence gap when no qualifying record supports a required claim."
        ),
        "CONTRADICTORY_SOURCES": (
            "Return conflicting claims as separate provenance-bearing candidates; prefer neither solely "
            "because it was retrieved first or appears more often."
        ),
        "STALE_MEMORY": (
            "Check source freshness and supersession before using a volatile fact; if current authority "
            "cannot be read, mark the fact stale or unknown rather than treating memory as current."
        ),
    },
    "PLANNER_STRATEGY": {
        "CONSTRAINT_DRIFT": (
            "Represent goal, constraints, prerequisites, deadline, budget and acceptance checks explicitly; "
            "validate each step against them before dispatch."
        ),
        "REPEATED_FAILURE": (
            "On failure, isolate one likely cause, state a falsifiable hypothesis, change one variable, and "
            "re-evaluate before selecting another strategy."
        ),
        "MISSING_CAPABILITY": (
            "Check capability existence, owner, readiness and permission before planning dependent actions; "
            "replace impossible steps with a declared blocked state or a feasible alternative."
        ),
        "UNVERIFIED_TOOL_OUTPUT": (
            "Plan a result-verification step after every consequential action and preserve IN_DOUBT when "
            "the action may have occurred but its outcome cannot be established."
        ),
    },
}


def propose_offline_variants(
    *,
    target_kind: str,
    target_id: str,
    baseline_text: str,
    baseline_digest: str,
    failure_signals: list[Mapping[str, Any]],
    max_variants: int = 4,
) -> list[dict[str, Any]]:
    """Create small evidence-linked text candidates without a model or code execution.

    This bounded mutation registry is a free/offline fallback, not a general language
    generator. Each result is proposed only; callers must evaluate it and must not
    activate it merely because this function generated it.
    """
    kind = _text(target_kind, "EVOLUTION_TARGET_KIND_INVALID", 64)
    if kind not in _OFFLINE_MUTATIONS:
        raise EvolutionError("EVOLUTION_OFFLINE_TARGET_UNSUPPORTED")
    tid = _text(target_id, "EVOLUTION_TARGET_ID_INVALID", 128)
    if not _ID.fullmatch(tid):
        raise EvolutionError("EVOLUTION_TARGET_ID_INVALID")
    if not isinstance(baseline_text, str) or not baseline_text.strip():
        raise EvolutionError("EVOLUTION_BASELINE_TEXT_INVALID")
    if len(baseline_text.encode("utf-8")) > 500_000:
        raise EvolutionError("EVOLUTION_BASELINE_TEXT_TOO_LARGE")
    expected = _sha(baseline_digest, "EVOLUTION_BASELINE_DIGEST_INVALID")
    actual = hashlib.sha256(baseline_text.encode("utf-8")).hexdigest()
    if actual != expected:
        raise EvolutionError("EVOLUTION_BASELINE_TEXT_DIGEST_MISMATCH")
    if (isinstance(max_variants, bool) or not isinstance(max_variants, int)
            or not 1 <= max_variants <= 16):
        raise EvolutionError("EVOLUTION_MAX_VARIANTS_INVALID")
    if not isinstance(failure_signals, list) or not failure_signals or len(failure_signals) > 64:
        raise EvolutionError("EVOLUTION_FAILURE_SIGNALS_INVALID")

    collected: dict[str, set[str]] = {}
    for signal in failure_signals:
        if not isinstance(signal, Mapping) or set(signal) != {"code", "evidence_refs"}:
            raise EvolutionError("EVOLUTION_FAILURE_SIGNAL_SCHEMA_INVALID")
        code = _text(signal["code"], "EVOLUTION_FAILURE_CODE_INVALID", 64)
        if code not in _OFFLINE_MUTATIONS[kind]:
            raise EvolutionError("EVOLUTION_FAILURE_CODE_UNSUPPORTED")
        refs = _refs(signal["evidence_refs"], "EVOLUTION_FAILURE_EVIDENCE_INVALID")
        collected.setdefault(code, set()).update(refs)

    candidates = []
    for code in sorted(collected):
        if len(candidates) >= max_variants:
            break
        marker = f"[HG-EVOLUTION:{kind}:{code}:V1]"
        if marker in baseline_text:
            continue
        directive = _OFFLINE_MUTATIONS[kind][code]
        candidate_text = baseline_text.rstrip() + "\n\n" + marker + "\n" + directive + "\n"
        if len(candidate_text.encode("utf-8")) > 500_000:
            raise EvolutionError("EVOLUTION_CANDIDATE_TEXT_TOO_LARGE")
        candidate_digest = hashlib.sha256(candidate_text.encode("utf-8")).hexdigest()
        candidates.append({
            "schema_version": "HG_OFFLINE_CANDIDATE_V1",
            "candidate_id": "candidate-" + candidate_digest[:16],
            "operator_id": "HG_OFFLINE_MUTATOR",
            "operator_version": "1.0.0",
            "target_kind": kind,
            "target_id": tid,
            "diagnostic_code": code,
            "hypothesis": (
                f"Address {code} by adding one versioned {kind} directive; "
                "effect remains unproven until measured against the frozen baseline."
            ),
            "baseline_digest": actual,
            "candidate_digest": candidate_digest,
            "candidate_text": candidate_text,
            "evidence_refs": sorted(collected[code]),
            "activation_state": "PROPOSED_NOT_ACTIVE",
            "requires_evaluation": True,
            "automatic_activation": False,
        })
    return candidates
