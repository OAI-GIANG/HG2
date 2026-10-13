"""HG Creative Assimilation V1: pure, fail-closed candidate evaluation.

This module has no runtime, network, filesystem, model, or execution authority.
It proposes and evaluates knowledge artifacts; existing HG governance and the
phone runtime remain the only authority/state owners.
"""
from __future__ import annotations
from dataclasses import dataclass, field, replace
import re
from typing import Mapping, Sequence
from urllib.parse import urlparse

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
LIFECYCLE = frozenset({"DRAFT", "CANDIDATE", "REVIEW_REQUIRED", "ACCEPTED", "REJECTED", "QUARANTINED", "REVOKED"})
TRUST_VALUES = frozenset({"UNKNOWN", "PASS", "FAIL"})
LICENSE_VALUES = frozenset({"UNKNOWN", "VERIFIED", "INCOMPATIBLE"})
_TRANSITIONS = {
    "DRAFT": frozenset({"CANDIDATE"}),
    "CANDIDATE": frozenset({"REVIEW_REQUIRED", "REJECTED", "QUARANTINED"}),
    "REVIEW_REQUIRED": frozenset({"ACCEPTED", "REJECTED", "QUARANTINED"}),
    "ACCEPTED": frozenset({"QUARANTINED", "REVOKED"}),
    "REJECTED": frozenset(),
    "QUARANTINED": frozenset({"REVOKED"}),
    "REVOKED": frozenset(),
}

@dataclass(frozen=True)
class SourceEvidence:
    source_id: str
    archive_sha256: str
    upstream_url: str = ""
    source_revision: str = ""
    license_status: str = "UNKNOWN"
    artifact_integrity: str = "UNKNOWN"
    source_authenticity: str = "UNKNOWN"
    inspected_paths: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

@dataclass(frozen=True)
class TrustAssessment:
    artifact_integrity: str = "UNKNOWN"
    source_authenticity: str = "UNKNOWN"
    license_status: str = "UNKNOWN"
    semantic_validity: str = "UNKNOWN"
    independent_verification: str = "UNKNOWN"

    def __post_init__(self):
        for name in ("artifact_integrity", "source_authenticity", "semantic_validity", "independent_verification"):
            if getattr(self, name) not in TRUST_VALUES:
                raise ValueError("INVALID_TRUST_VALUE:" + name)
        if self.license_status not in LICENSE_VALUES:
            raise ValueError("INVALID_LICENSE_STATUS")

@dataclass(frozen=True)
class CreativePrinciple:
    principle_id: str
    source_id: str
    mechanism: str
    context: str
    limitations: tuple[str, ...]
    evidence_refs: tuple[str, ...]

@dataclass(frozen=True)
class SynthesisCandidate:
    candidate_id: str
    principle_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    hypothesis: str
    expected_benefit: str
    scope: str
    experiment: str
    acceptance_criteria: tuple[str, ...]
    failure_modes: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    lifecycle_status: str = "DRAFT"
    trust: TrustAssessment = field(default_factory=TrustAssessment)
    revision: int = 1

    def __post_init__(self):
        if self.lifecycle_status not in LIFECYCLE:
            raise ValueError("INVALID_LIFECYCLE_STATUS")
        if self.revision < 1:
            raise ValueError("INVALID_REVISION")

@dataclass(frozen=True)
class Evaluation:
    ready_for_review: bool
    blockers: tuple[str, ...]

def validate_source(source: SourceEvidence) -> tuple[str, ...]:
    """Digest proves byte consistency, not source authenticity or license."""
    blockers = []
    if not source.source_id.strip():
        blockers.append("SOURCE_ID_MISSING")
    if not _SHA256.fullmatch(source.archive_sha256):
        blockers.append("ARCHIVE_SHA256_INVALID")
    parsed = urlparse(source.upstream_url)
    if parsed.scheme != "https" or not parsed.netloc:
        blockers.append("UPSTREAM_URL_UNVERIFIED")
    if not _COMMIT.fullmatch(source.source_revision):
        blockers.append("UPSTREAM_REVISION_UNVERIFIED")
    if source.license_status != "VERIFIED":
        blockers.append("LICENSE_NOT_VERIFIED")
    if source.artifact_integrity != "PASS":
        blockers.append("ARTIFACT_INTEGRITY_NOT_VERIFIED")
    if source.source_authenticity != "PASS":
        blockers.append("SOURCE_AUTHENTICITY_NOT_VERIFIED")
    if not source.inspected_paths:
        blockers.append("INSPECTED_PATHS_MISSING")
    if not source.evidence_refs:
        blockers.append("SOURCE_EVIDENCE_REFS_MISSING")
    return tuple(blockers)

def evaluate_candidate(candidate: SynthesisCandidate, sources: Mapping[str, SourceEvidence],
                       principles: Mapping[str, CreativePrinciple]) -> Evaluation:
    """Assess eligibility without mutating lifecycle or trust state."""
    blockers = []
    if not candidate.candidate_id.strip():
        blockers.append("CANDIDATE_ID_MISSING")
    if len(set(candidate.source_ids)) < 2:
        blockers.append("CROSS_SOURCE_SYNTHESIS_REQUIRED")
    if len(set(candidate.principle_ids)) < 2:
        blockers.append("TWO_DISTINCT_PRINCIPLES_REQUIRED")
    resolved_principles = []
    for principle_id in sorted(set(candidate.principle_ids)):
        principle = principles.get(principle_id)
        if principle is None:
            blockers.append("PRINCIPLE_NOT_FOUND:" + principle_id)
        else:
            resolved_principles.append(principle)
            if not principle.evidence_refs:
                blockers.append("PRINCIPLE_EVIDENCE_MISSING:" + principle_id)
            if not principle.mechanism.strip() or not principle.context.strip():
                blockers.append("PRINCIPLE_DESCRIPTION_INCOMPLETE:" + principle_id)
    principle_source_ids = {p.source_id for p in resolved_principles}
    if resolved_principles and principle_source_ids != set(candidate.source_ids):
        blockers.append("PRINCIPLE_SOURCE_BINDING_MISMATCH")
    for name, value in (("HYPOTHESIS", candidate.hypothesis), ("EXPECTED_BENEFIT", candidate.expected_benefit),
                        ("SCOPE", candidate.scope), ("EXPERIMENT", candidate.experiment)):
        if not value.strip():
            blockers.append(name + "_MISSING")
    if not candidate.acceptance_criteria:
        blockers.append("ACCEPTANCE_CRITERIA_MISSING")
    if not candidate.failure_modes:
        blockers.append("FAILURE_MODES_MISSING")
    if not candidate.evidence_refs:
        blockers.append("EVIDENCE_REFS_MISSING")
    for source_id in sorted(set(candidate.source_ids)):
        source = sources.get(source_id)
        if source is None:
            blockers.append("SOURCE_NOT_FOUND:" + source_id)
            continue
        if source.source_id != source_id:
            blockers.append("SOURCE_ID_BINDING_MISMATCH:" + source_id)
        blockers.extend(source_id + ":" + issue for issue in validate_source(source))
    if candidate.trust.semantic_validity != "PASS":
        blockers.append("SEMANTIC_VALIDITY_NOT_VERIFIED")
    if candidate.trust.independent_verification != "PASS":
        blockers.append("INDEPENDENT_VERIFICATION_NOT_PASS")
    if candidate.trust.artifact_integrity != "PASS":
        blockers.append("CANDIDATE_ARTIFACT_INTEGRITY_NOT_PASS")
    if candidate.trust.source_authenticity != "PASS":
        blockers.append("CANDIDATE_SOURCE_AUTHENTICITY_NOT_PASS")
    if candidate.trust.license_status != "VERIFIED":
        blockers.append("CANDIDATE_LICENSE_NOT_VERIFIED")
    return Evaluation(not blockers, tuple(dict.fromkeys(blockers)))

def transition(candidate: SynthesisCandidate, target: str, *, actor_id: str,
               sources: Mapping[str, SourceEvidence], principles: Mapping[str, CreativePrinciple], reviewer_id: str = "",
               evidence_refs: Sequence[str] = ()) -> SynthesisCandidate:
    """Apply a checked lifecycle transition; never grants execution authority."""
    if not actor_id.strip():
        raise ValueError("ACTOR_REQUIRED")
    if target not in _TRANSITIONS.get(candidate.lifecycle_status, frozenset()):
        raise ValueError("TRANSITION_NOT_ALLOWED")
    if target == "CANDIDATE":
        result = evaluate_candidate(candidate, sources, principles)
        ignored = (
            "UPSTREAM_URL_UNVERIFIED", "UPSTREAM_REVISION_UNVERIFIED", "LICENSE_NOT_VERIFIED",
            "ARTIFACT_INTEGRITY_NOT_VERIFIED", "SOURCE_AUTHENTICITY_NOT_VERIFIED",
            "SEMANTIC_VALIDITY_NOT_VERIFIED", "INDEPENDENT_VERIFICATION_NOT_PASS",
            "CANDIDATE_ARTIFACT_INTEGRITY_NOT_PASS", "CANDIDATE_SOURCE_AUTHENTICITY_NOT_PASS",
            "CANDIDATE_LICENSE_NOT_VERIFIED",
        )
        structural = tuple(x for x in result.blockers if not any(x.endswith(i) for i in ignored))
        if structural:
            raise ValueError("CANDIDATE_INCOMPLETE:" + ",".join(structural))
    if target == "REVIEW_REQUIRED":
        result = evaluate_candidate(candidate, sources, principles)
        if not result.ready_for_review:
            raise ValueError("REVIEW_GATE_BLOCKED:" + ",".join(result.blockers))
        if not evidence_refs:
            raise ValueError("REVIEW_EVIDENCE_REQUIRED")
    if target == "ACCEPTED":
        result = evaluate_candidate(candidate, sources, principles)
        if not result.ready_for_review:
            raise ValueError("ACCEPTANCE_GATE_BLOCKED:" + ",".join(result.blockers))
        if not reviewer_id.strip() or reviewer_id == actor_id:
            raise ValueError("INDEPENDENT_REVIEWER_REQUIRED")
        if not evidence_refs:
            raise ValueError("ACCEPTANCE_EVIDENCE_REQUIRED")
    if target in {"REJECTED", "QUARANTINED", "REVOKED"} and not evidence_refs:
        raise ValueError("DECISION_EVIDENCE_REQUIRED")
    return replace(candidate, lifecycle_status=target, revision=candidate.revision + 1)
