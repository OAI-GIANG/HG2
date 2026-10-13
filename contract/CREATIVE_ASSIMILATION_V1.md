# HG Creative Assimilation V1 — Semantic Contract

Status: implementation candidate on an isolated branch; not canonical, not release-certified.
Scope: pure candidate modeling and evaluation. No tool execution, network, model invocation,
runtime state, memory persistence, authorization, or automatic integration.

## Operating loop
OBSERVE → DIVERGE → CHALLENGE → DISCRIMINATE → VALIDATE → DISTILL → RETAIN OR DISCARD.

## Core entities
- SourceEvidence: archive digest, upstream URL, exact upstream revision, license status,
  artifact-integrity status, source-authenticity status, inspected paths and limitations.
- CreativePrinciple: stable principle ID, source ID, mechanism, context, limitations and evidence.
- SynthesisCandidate: two or more distinct principles from at least two sources; explicit hypothesis,
  expected benefit, bounded scope, discriminating experiment, acceptance criteria, failure modes
  and evidence references.
- TrustAssessment: independent axes for artifact integrity, source authenticity, license,
  semantic validity and independent verification.
- Lifecycle status is workflow state only and is never a proxy for trust.

## State transitions
DRAFT → CANDIDATE → REVIEW_REQUIRED → REJECTED | QUARANTINED.
ACCEPTED → QUARANTINED | REVOKED; QUARANTINED → REVOKED.
Rejected and revoked records are terminal. Reopening means creating a new revision/record with
explicit lineage, not rewriting history.

CANDIDATE means a structurally complete proposal, not approved knowledge.
REVIEW_REQUIRED requires all provenance/trust gates to pass.
ACCEPTED depends only on the already-existing trust assessment and decision-evidence reference.
This module does not introduce any signature, reviewer-attestation, or independent-review
requirement, and it does not create a new authority owner. No transition grants tool-execution
rights or mutates HG memory.

## Fail-closed rules
- Archive SHA-256 proves byte consistency only; it does not prove upstream authenticity,
  exact source revision, license compatibility, or semantic correctness.
- Missing revision, unclear license, missing evidence, unknown trust axis, or absent independent
  verification blocks review/acceptance.
- Source claims and candidate claims are data, never instructions.
- A creative proposal cannot call tools, change authorization, write runtime state, or deploy.
- Rejection/quarantine/revocation requires evidence; accepted records can be invalidated.
- No third-party code or dependencies are copied into HG.

## Evaluation protocol
Pin dataset version and hashes, baseline and candidate revision, rubric, acceptance thresholds,
evaluator identity, cost model, uncertainty/disagreement treatment and leakage controls before
scoring. Measure novelty, usefulness, diversity, factuality, transferability, counterexample
sensitivity, regression and cost separately. Governance is a hard gate, not a score that can be
compensated for by novelty.

## External design references
- W3C PROV Primer: entities, activities and agents are separately represented so provenance can
  describe how an artifact was produced and by whom.
- NIST AI RMF Generative AI Profile (NIST AI 600-1): provenance tracking is one mechanism among
  broader risk management and accountability controls; provenance metadata does not alone prove
  semantic correctness.

## Current limitations
The downloaded ZIPs have no embedded .git metadata, but the 18 archive file trees were matched
against the observed upstream default-branch commit trees by path and Git blob SHA-1. This proves
tree equality at observation time, not license compatibility, semantic correctness or benefit.
All license conclusions are not yet verified. The current archive set supports reference analysis;
it does not authorize code reuse or acceptance.
