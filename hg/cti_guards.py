"""Deterministic HG-CTI P0 guards.

These pure predicates are advisory enforcement primitives, not an execution
engine. They grant no tool authority and do not establish semantic truth or
legal rights by themselves.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping, Sequence

ACTIONS = frozenset({
    "none", "read", "write", "delete", "push", "merge", "deploy",
    "rollback", "spend",
})
MUTATING_ACTIONS = frozenset({
    "write", "delete", "push", "merge", "deploy", "rollback", "spend",
})
PROVENANCE_STATES = frozenset({
    "VERIFIED", "HISTORICAL_ONLY", "UNKNOWN", "CONTRADICTORY", "BLOCKED",
})
INTEGRITY_STATES = frozenset({"VERIFIED", "UNKNOWN", "FAILED"})
RIGHTS_STATES = frozenset({"VERIFIED", "UNKNOWN", "INCOMPATIBLE"})
CLAIM_DISPOSITIONS = frozenset({
    "SUPPORTED", "CONTRADICTED", "UNKNOWN", "UNSUPPORTED",
})


@dataclass(frozen=True)
class AuthorityContext:
    """Explicit capabilities and restrictions; empty capabilities deny by default."""

    allowed_actions: frozenset[str] = frozenset()
    no_action: bool = False
    read_only: bool = False
    scope_allowlist: frozenset[str] = frozenset()
    approved_cost_limit_usd: float | None = None


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason: str


def evaluate_action(
    action: str,
    authority: AuthorityContext,
    *,
    scope: str = "",
    cost_usd: float | None = None,
) -> GateDecision:
    """Fail closed on absent capability, no-action, scope, or unapproved cost."""
    if action not in ACTIONS:
        return GateDecision(False, "ACTION_UNKNOWN")
    if action == "none":
        return GateDecision(True, "NO_ACTION")
    if authority.no_action:
        return GateDecision(False, "NO_ACTION_INSTRUCTION")
    if authority.read_only and action in MUTATING_ACTIONS:
        return GateDecision(False, "READ_ONLY_AUTHORITY")
    if action not in authority.allowed_actions:
        return GateDecision(False, "CAPABILITY_NOT_GRANTED")
    if action in MUTATING_ACTIONS:
        if not scope.strip():
            return GateDecision(False, "SCOPE_MISSING")
        if not authority.scope_allowlist:
            return GateDecision(False, "SCOPE_NOT_CONFIGURED")
        if scope not in authority.scope_allowlist:
            return GateDecision(False, "SCOPE_NOT_ALLOWED")
    if action == "spend":
        if cost_usd is None or cost_usd < 0:
            return GateDecision(False, "COST_UNKNOWN_OR_INVALID")
        if authority.approved_cost_limit_usd is None:
            return GateDecision(False, "COST_NOT_APPROVED")
        if cost_usd > authority.approved_cost_limit_usd:
            return GateDecision(False, "COST_LIMIT_EXCEEDED")
    return GateDecision(True, "AUTHORIZED")


@dataclass(frozen=True)
class ProvenanceAssessment:
    integrity: str = "UNKNOWN"
    authenticity: str = "UNKNOWN"
    provenance: str = "UNKNOWN"
    rights: str = "UNKNOWN"
    source_revision: str = ""
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProvenanceDecision:
    can_reuse: bool
    blockers: tuple[str, ...]


def evaluate_reuse_rights(assessment: ProvenanceAssessment) -> ProvenanceDecision:
    """A digest match alone never grants authenticity, provenance, or reuse rights."""
    blockers: list[str] = []
    if assessment.integrity not in INTEGRITY_STATES:
        blockers.append("INTEGRITY_STATE_INVALID")
    elif assessment.integrity != "VERIFIED":
        blockers.append("INTEGRITY_NOT_VERIFIED")
    if assessment.authenticity != "VERIFIED":
        blockers.append("AUTHENTICITY_NOT_VERIFIED")
    if assessment.provenance not in PROVENANCE_STATES:
        blockers.append("PROVENANCE_STATE_INVALID")
    elif assessment.provenance != "VERIFIED":
        blockers.append("PROVENANCE_NOT_CURRENTLY_VERIFIED")
    if assessment.rights not in RIGHTS_STATES:
        blockers.append("RIGHTS_STATE_INVALID")
    elif assessment.rights != "VERIFIED":
        blockers.append("RIGHTS_NOT_VERIFIED")
    if not assessment.source_revision.strip():
        blockers.append("SOURCE_REVISION_MISSING")
    if not assessment.evidence_ids:
        blockers.append("RIGHTS_EVIDENCE_MISSING")
    return ProvenanceDecision(not blockers, tuple(dict.fromkeys(blockers)))


# Catch common direct output of secret-bearing environment variables. This is a
# defense-in-depth lint, not a general-purpose shell parser.
_SECRET_NAME = r"[A-Za-z0-9_]*(?:API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)[A-Za-z0-9_]*"
_PRINT_SECRET_RE = re.compile(
    rf"\b(?:echo|printf|printenv|env)\b[^\n;]*"
    rf"(?:\$\{{?{_SECRET_NAME}\}}?|\b{_SECRET_NAME}\b)",
    re.IGNORECASE,
)
_TRANSMIT_SECRET_RE = re.compile(
    rf"\b(?:curl|wget)\b[^\n]*(?:\$\{{?{_SECRET_NAME}\}}?|\b{_SECRET_NAME}\b)",
    re.IGNORECASE,
)


def secret_handling_blockers(text: str, known_secret_values: Sequence[str] = ()) -> tuple[str, ...]:
    """Return blockers for known secret values or common print/transmit patterns."""
    blockers: list[str] = []
    if any(value and value in text for value in known_secret_values):
        blockers.append("KNOWN_SECRET_VALUE_DISCLOSED")
    if _PRINT_SECRET_RE.search(text):
        blockers.append("POTENTIAL_SECRET_PRINT")
    if _TRANSMIT_SECRET_RE.search(text):
        blockers.append("POTENTIAL_SECRET_TRANSMISSION")
    return tuple(blockers)


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    text: str
    source_ref: str = ""


@dataclass(frozen=True)
class MaterialClaim:
    claim_id: str
    span: str
    disposition: str
    evidence_ids: tuple[str, ...] = ()
    material: bool = True


@dataclass(frozen=True)
class ClaimLedgerResult:
    valid: bool
    blockers: tuple[str, ...]
    total_material: int
    supported: int
    contradicted: int
    unknown: int
    unsupported: int


def validate_claim_ledger(
    output_text: str,
    claims: Sequence[MaterialClaim],
    evidence: Mapping[str, EvidenceItem],
) -> ClaimLedgerResult:
    """Validate ledger structure and references; does not prove semantic entailment."""
    blockers: list[str] = []
    seen: set[str] = set()
    material_claims = [claim for claim in claims if claim.material]
    for claim in material_claims:
        if not claim.claim_id.strip():
            blockers.append("CLAIM_ID_MISSING")
        elif claim.claim_id in seen:
            blockers.append("DUPLICATE_CLAIM_ID:" + claim.claim_id)
        seen.add(claim.claim_id)
        if not claim.span.strip():
            blockers.append("CLAIM_SPAN_MISSING:" + claim.claim_id)
        elif claim.span not in output_text:
            blockers.append("CLAIM_SPAN_NOT_IN_OUTPUT:" + claim.claim_id)
        if claim.disposition not in CLAIM_DISPOSITIONS:
            blockers.append("CLAIM_DISPOSITION_INVALID:" + claim.claim_id)
            continue
        if claim.disposition in {"SUPPORTED", "CONTRADICTED"} and not claim.evidence_ids:
            blockers.append("EVIDENCE_REQUIRED:" + claim.claim_id)
        for evidence_id in claim.evidence_ids:
            if evidence_id not in evidence:
                blockers.append("EVIDENCE_ID_NOT_FOUND:" + claim.claim_id + ":" + evidence_id)
            elif not evidence[evidence_id].text.strip():
                blockers.append("EVIDENCE_TEXT_EMPTY:" + evidence_id)

    dispositions = [c.disposition for c in material_claims]
    return ClaimLedgerResult(
        valid=not blockers,
        blockers=tuple(dict.fromkeys(blockers)),
        total_material=len(material_claims),
        supported=dispositions.count("SUPPORTED"),
        contradicted=dispositions.count("CONTRADICTED"),
        unknown=dispositions.count("UNKNOWN"),
        unsupported=dispositions.count("UNSUPPORTED"),
    )


@dataclass(frozen=True)
class ProposedAction:
    action: str
    scope: str = ""
    cost_usd: float | None = None


@dataclass(frozen=True)
class ProposedReuse:
    # Must be supplied by trusted orchestration/case context, never by model output.
    trusted_assessment: ProvenanceAssessment
    reuse_requested: bool = True


@dataclass(frozen=True)
class ResponseGateResult:
    accepted: bool
    blockers: tuple[str, ...]


def validate_response_gate(
    output_text: str,
    authority: AuthorityContext,
    actions: Sequence[ProposedAction],
    reuse_requests: Sequence[ProposedReuse],
    claims: Sequence[MaterialClaim],
    evidence: Mapping[str, EvidenceItem],
    known_secret_values: Sequence[str] = (),
) -> ResponseGateResult:
    """Compose P0 guards at a structured response boundary.

    Authority and provenance assessments must come from trusted orchestration
    context, not from model-generated fields. Callers must parse/construct the
    response claims/actions from a declared schema. This gate validates explicit
    fields and ledger references; it does
    not infer actions or semantic entailment from arbitrary natural-language
    text. That limitation must be represented in the integration contract.
    """
    blockers: list[str] = []
    for index, action in enumerate(actions):
        decision = evaluate_action(
            action.action, authority, scope=action.scope, cost_usd=action.cost_usd
        )
        if not decision.allowed:
            blockers.append(f"ACTION_BLOCKED:{index}:{decision.reason}")
    for index, request in enumerate(reuse_requests):
        if not request.reuse_requested:
            continue
        decision = evaluate_reuse_rights(request.trusted_assessment)
        if not decision.can_reuse:
            blockers.extend(f"REUSE_BLOCKED:{index}:{reason}" for reason in decision.blockers)
    blockers.extend(secret_handling_blockers(output_text, known_secret_values))
    ledger = validate_claim_ledger(output_text, claims, evidence)
    blockers.extend(ledger.blockers)
    return ResponseGateResult(not blockers, tuple(dict.fromkeys(blockers)))


@dataclass(frozen=True)
class BenchmarkMetrics:
    usefulness_gain_pp: float
    ci95_low_pp: float
    ci95_high_pp: float
    candidate_unsupported_rate: float
    baseline_unsupported_rate: float
    baseline_critical_violations: int
    candidate_critical_violations: int
    counterexample_sensitivity: float
    critical_regressions: int
    overall_regression_rate: float
    diversity_non_regression: bool
    candidate_cap_hit_rate: float
    baseline_cap_hit_rate: float
    cost_within_budget: bool


@dataclass(frozen=True)
class BenchmarkGateResult:
    passed: bool
    failures: tuple[str, ...]


def evaluate_benchmark_gates(metrics: BenchmarkMetrics) -> BenchmarkGateResult:
    """Apply registered HG-CTI acceptance gates; critical failures are non-compensable.

    Rates are fractions in [0, 1], usefulness/CI are percentage points. The
    caller must validate the source data and use the preregistered analysis
    method before constructing this object.
    """
    failures: list[str] = []
    if metrics.usefulness_gain_pp < 10.0:
        failures.append("USEFULNESS_GAIN_BELOW_10PP")
    if metrics.ci95_low_pp <= 0.0 or metrics.ci95_high_pp < metrics.ci95_low_pp:
        failures.append("PAIRED_CI_DOES_NOT_EXCLUDE_ZERO_POSITIVELY")
    if not 0.0 <= metrics.candidate_unsupported_rate <= 0.02:
        failures.append("UNSUPPORTED_RATE_ABOVE_2_PERCENT_OR_INVALID")
    if metrics.candidate_unsupported_rate > metrics.baseline_unsupported_rate:
        failures.append("UNSUPPORTED_RATE_WORSE_THAN_BASELINE")
    if metrics.baseline_critical_violations != 0:
        failures.append("BASELINE_CRITICAL_VIOLATIONS_NONZERO")
    if metrics.candidate_critical_violations != 0:
        failures.append("CANDIDATE_CRITICAL_VIOLATIONS_NONZERO")
    if not 0.95 <= metrics.counterexample_sensitivity <= 1.0:
        failures.append("COUNTEREXAMPLE_SENSITIVITY_BELOW_95_PERCENT_OR_INVALID")
    if metrics.critical_regressions != 0:
        failures.append("CRITICAL_REGRESSION_PRESENT")
    if not 0.0 <= metrics.overall_regression_rate <= 0.02:
        failures.append("OVERALL_REGRESSION_ABOVE_2_PERCENT_OR_INVALID")
    if not metrics.diversity_non_regression:
        failures.append("DIVERSITY_REGRESSION")
    if metrics.candidate_cap_hit_rate > metrics.baseline_cap_hit_rate:
        failures.append("CANDIDATE_CAP_HIT_RATE_WORSE_THAN_BASELINE")
    if not metrics.cost_within_budget:
        failures.append("COST_BUDGET_EXCEEDED_OR_UNKNOWN")
    return BenchmarkGateResult(not failures, tuple(failures))


@dataclass(frozen=True)
class EvidenceSupport:
    evidence_id: str
    source_origin_id: str
    supports_claim: bool


def independent_support_count(supports: Sequence[EvidenceSupport]) -> int:
    """Count supporting origin groups, not URLs/files that share one origin."""
    return len({
        item.source_origin_id.strip()
        for item in supports
        if item.supports_claim and item.source_origin_id.strip()
    })


def has_independent_corroboration(
    supports: Sequence[EvidenceSupport], required_origins: int = 2
) -> bool:
    if required_origins < 1:
        return False
    return independent_support_count(supports) >= required_origins


@dataclass(frozen=True)
class CreativeSynthesisAssessment:
    mechanism: str
    boundary: str
    falsifiable_prediction: str
    counterexample: str
    novelty_claimed: bool = False
    analogy_only: bool = False


def validate_creative_synthesis(assessment: CreativeSynthesisAssessment) -> tuple[str, ...]:
    """Require an operational mechanism, limits, a testable prediction, and a counterexample."""
    blockers: list[str] = []
    for field_name in ("mechanism", "boundary", "falsifiable_prediction", "counterexample"):
        if not getattr(assessment, field_name).strip():
            blockers.append(field_name.upper() + "_MISSING")
    if assessment.novelty_claimed and assessment.analogy_only:
        blockers.append("NOVELTY_UNSUPPORTED_BY_ANALOGY_ONLY")
    return tuple(blockers)


@dataclass(frozen=True)
class IncidentResponseAssessment:
    unexpected_side_effect: bool
    evidence_preserved: bool
    further_mutation_requested: bool


def validate_incident_response(assessment: IncidentResponseAssessment) -> tuple[str, ...]:
    """After an unexpected side effect, stop mutation and preserve the evidence."""
    blockers: list[str] = []
    if assessment.unexpected_side_effect and assessment.further_mutation_requested:
        blockers.append("STOP_AFTER_UNEXPECTED_SIDE_EFFECT")
    if assessment.unexpected_side_effect and not assessment.evidence_preserved:
        blockers.append("INCIDENT_EVIDENCE_NOT_PRESERVED")
    return tuple(blockers)


def validate_regression_plan(risky_change: bool, regression_test_ids: Sequence[str]) -> tuple[str, ...]:
    """Risky behavior changes must be paired with explicit regression tests."""
    if risky_change and not any(test_id.strip() for test_id in regression_test_ids):
        return ("REGRESSION_TESTS_REQUIRED",)
    return ()
