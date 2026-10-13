# HG Creative Assimilation V1 — Implementation and Evidence Status

## Objective
Enable HG to create and evaluate cross-source synthesis proposals while preserving one authority
owner, one canonical runtime/state owner, and fail-closed evidence gates.

## Source-derived ideas retained as principles only
- memXT: durable retrieval and explicit evidence/source references; no memory code copied.
- Friday: approval and visible action receipts; no execution flow copied.
- PP-Finder: candidate discovery and anomaly signals; findings remain hypotheses until tested.
- DOM-Explorer: compare transformation pipelines and preserve intermediate observations.
- Vulnerable Code Snippets: counterexamples and failure cases as negative test fixtures; no exploit
  payloads included in the HG core.
- PwnFox: explicit scope/container separation; no browser extension code copied.
- YWH2BugTracker: finding lifecycle and synchronization require provenance and conflict handling.
- YesWeBurp / YesWeCaido: external feedback adapters are optional references, not core dependencies.
- MyOpenVDP: intake needs a bounded, auditable lifecycle.
- xsstools: excluded from core; security payload tooling is not a creativity primitive.
- Burp Addon Tutorial: adapter/plugin pattern only.
- Hoglet: observability and contracts as candidate design inputs.
- OpenGTM: orchestration and source selection are proposals only; not an execution owner.
- VoiceStudio: multimodal adapter boundary only; no model/media runtime copied.
- Opal: reference-only media workflow patterns.
- Bootable: staged action/review/execute/verify pattern; HG-CTI itself cannot execute.
- Homebrew memXT: packaging/distribution reference only.

The source-by-source evidence and remaining license gates are recorded in
HG_CREATIVE_ASSIMILATION_SOURCE_MATRIX.md. These are bounded abstractions, not claims that every
upstream revision or implementation detail has been independently verified.

## Architecture decision
HG-CTI is a pure proposal/evaluation layer. Existing hg.authority, hg.phone_runtime and hg.history
remain unchanged and remain the only authority/state owners. No third-party code, runtime, model,
dependency or service was integrated.

## Acceptance gates
1. Source inventory: 18 archive SHA-256 values and ZIP CRC checks are recorded in
   evidence/HG-CTI-20261013/archive-manifest.json. ZIPs lack embedded .git metadata, but all 18 archive file trees now match exact observed upstream
   default-branch commits (evidence includes repository, commit SHA, paths and blob-hash comparison).
   License files are absent from some archives, so license status is not inferred from project names.
2. Capability gap: canonical HG had no creative-assimilation candidate contract/evaluator. This
   branch adds a bounded pure module; it does not claim a production intelligence advantage.
3. Semantic safety: tests cover missing source, unverified revision/license, unknown trust,
   same-source false synthesis, missing experiment/evidence, self-review, illegal transitions,
   and terminal-state reopening.
4. Benefit proof: not established. The pre-registered protocol in HG_CTI_BENCHMARK_PROTOCOL_V1.md
   defines a versioned baseline-vs-candidate benchmark; it has not been executed.
5. Independent review: not performed by the authoring agent; required before canonical merge.
6. Runtime/production: no runtime wiring or deployment is included or claimed.

## Verdict
Implementation candidate on isolated branch. No production/release certification. License compatibility, benchmark advantage and independent review remain open gates.
