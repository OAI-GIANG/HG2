# HG-ADR-001 — HG2 Primary Platform Designation for HG

- **Document version:** 1.0
- **Document status:** APPROVED FOR FORMAL RECORDING; repository write pending explicit confirmation of destination and write authorization
- **Decision authority:** Product Owner instruction in the current conversation
- **Prepared by:** STT (orchestration and audit support; not an independent approver)
- **Decision date:** 2026-10-13
- **Canonical repository:** `OAI-GIANG/HG2`
- **Canonical branch/SHA:** `hg-genesis` / `d11e71ed8b34338b8568664b39bc777c926826d5`
- **Candidate SHA (reference only):** `d1f67a35a70f5a048a8dba725d5d3c24e8f05283`
- **PR #5:** `OPEN / DRAFT / NOT MERGED`

## 1. Decision

HG2 is designated as the primary structural and operational platform for HG. HG and GO are reference sources only.

This is a strategic architecture decision. It does not certify HG2 as production-ready, close any technical gate, approve a merge or deployment, or imply that every capability of HG or GO exists in HG2.

## 2. Objective

Concentrate HG architecture and implementation work on HG2, reduce fragmentation across platforms, and require evidence-based assessment before adopting ideas, functionality, protocols, or implementation patterns from reference sources.

## 3. Scope

### In scope
- HG architecture and implementation priorities centered on HG2.
- Assessment of functions, contracts, protocols, dependencies, and lessons from HG and GO.
- Architecture boundaries, provenance, testing, change control, and acceptance criteria.
- Planning and prioritization of unresolved HG2 readiness blockers.

### Out of scope
This decision does not authorize:
- Merge, deployment, tagging, release, or production changes.
- Changes to the canonical branch, candidate commit, PR #5, or repository history.
- Deletion or archival of repositories, branches, or evidence.
- Claims that HG2 has replaced every capability of HG or GO.
- Claims that unresolved technical acceptance gates have passed.

## 4. Platform roles

### HG2 — primary platform
HG2 is the default target for architecture, implementation, durable state and history, identity, authentication boundaries, testing, runtime integration, evidence capture, and readiness assessment. New HG work should first assess whether it belongs in HG2 before proposing another operational platform.

### HG and GO — reference sources
HG and GO may be consulted for architecture, features, protocols, contracts, implementation lessons, defects, and historical evidence. Their content is not automatically inherited or accepted.

Every proposed adoption must identify the exact source, assess differences and risks, establish compatibility and security implications, define acceptance criteria, and obtain the required change approval.

## 5. Authority and change boundaries

The Product Owner's decision establishes strategic direction. STT supports orchestration, audit, comparison, and evidence assessment within the capabilities actually available.

This ADR does not grant blanket authority to mutate the repository. Each repository change must have a defined scope, target, acceptance criteria, and appropriate authorization. STT must not fabricate reviews, self-approve an unsigned exception, or claim actions occurred without tool-confirmed evidence.

## 6. Reference-adoption procedure

1. Identify source repository, URL, branch, and exact commit SHA.
2. Describe the specific capability or lesson proposed for adoption.
3. Compare source behavior and contracts with HG2.
4. Assess security, identity, persistence, compatibility, runtime, and external dependency risks.
5. Classify evidence by type and strength; do not substitute documentation or CI for independent review or provenance verification.
6. Define the proposed change, acceptance criteria, rollback/stop conditions, and required approvals.
7. Implement only after the applicable authorization and change gates are satisfied.

Similar names do not prove equivalence. Presence in a reference repository does not by itself justify copying a capability.

## 7. Roadmap implications

### P0 — Preserve controlled state
Preserve the canonical SHA, candidate SHA, and PR #5 state. Do not merge or release while required gates remain blocked.

### P1 — Complete the HG2 architecture map
Document core components, contracts, responsibilities, and a function matrix comparing HG2 with reference sources. Mark capabilities as verified, unverified, missing, intentionally removed, replaced, defective, or unknown where appropriate.

### P2 — Resolve evidence blockers
- Gate 3: obtain a real formal review by a person other than the author, bound to the exact candidate SHA.
- Gate 6: obtain verified signature provenance or a valid, traceable, properly approved unsigned exception.
- Assess production authentication, production-device/VPS/HTTPS end-to-end behavior, external consumers, runtime/build attribution, and power-loss recovery against their applicable acceptance criteria.
- Do not mark a gate passed based only on plans, documentation, or a green CI result.

### P3 — Acceptance and release
Consider release only after all mandatory gates have qualifying evidence, residual risks are handled by the proper authority, and required independent verification is recorded.

These phases are priorities, not claims that the work has been completed.

## 8. Evidence and status semantics

Keep separate: strategic decision evidence; design and contract evidence; implementation evidence tied to a specific revision; test evidence tied to exact SHA and environment; production/runtime evidence; provenance and signature evidence; and independent review evidence.

One category must not substitute for another where a gate explicitly requires it.

## 9. Acceptance criteria for this ADR

This ADR is fit for formal recording when:
1. HG2's primary role and HG/GO reference-only role are unambiguous.
2. Scope and exclusions are explicit.
3. Strategic authority is distinguished from technical mutation authority.
4. Reference adoption has an evidence-based process.
5. The roadmap and gate prerequisites are stated without claiming completion.
6. Canonical and candidate references are preserved exactly.
7. Version, decision authority, status, and storage location are recorded.
8. Repository recording is independently verifiable and does not alter canonical, candidate, or PR #5.

## 10. Risks and controls

- Strategic designation mistaken for production readiness: maintain separate strategic and technical statuses.
- Blind copying from reference sources: require source-specific comparison, risk assessment, and acceptance evidence.
- Unauthorized canonical mutation: enforce Zero Unauthorized Change and explicit scoped authorization.
- Unsupported gate closure: fail closed; do not treat CI as a substitute for formal review or signature verification.
- Draft mistaken for approved repository record: label local and repository states separately until the recording operation is confirmed and verified.

## 11. Stop conditions

Stop and report a blocker if canonical or candidate SHA differs from the stated value, required authority is absent, evidence cannot be bound to the target revision, provenance conflicts appear, or progress would require bypassing a mandatory gate.

## 12. Current status

**Strategic decision:** approved by the Product Owner's instruction in the current conversation.

**Document:** version 1.0, approved for formal recording.

**Repository recording:** pending confirmation of the proposed destination path and explicit authorization for the scoped write operation.

**Technical readiness:** unchanged. Gate 3 and Gate 6 remain blocked based on the latest queried evidence; Gate 4, Gate 5, and Gate 7 remain unchanged and not reevaluated.

**No repository write, merge, deployment, tag, release, canonical mutation, candidate mutation, or history rewrite has been performed as part of preparing this document.**
