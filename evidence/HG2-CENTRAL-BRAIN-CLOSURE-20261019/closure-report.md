# HG2 Central Brain R2/R3 — Candidate Closure Report

Date: 2026-10-19 (Asia/Ho_Chi_Minh)
Repository: OAI-GIANG/HG2 only
Branch: stt/hg2-brain-orchestrator-r1-20261019
Base HEAD before this candidate: 2d5498cc8c28a056c513aace4371ad96a2129adc
Closure classification: CANDIDATE_IMPLEMENTED_TESTED_RELEASE_BLOCKED
Release / deployment: NOT APPROVED
PR #29: must remain OPEN · DRAFT

## Objective and disposition

The R2 plan is closed for this implementation iteration as a bounded, evidence-recorded candidate—not as a production release. R3 remains the governing refinement of the R2 plan. The implementation adds a versioned runtime capability registry and strengthens the serial /api/ask path with stable idempotency, journal receipts, conservative IN_DOUBT recovery, memory-context source/integrity checks, and a production HTTP process lock. All changes are subject to independent review and the remaining release gates below.

## Termux execution evidence

- Runtime: Android 15, aarch64/ARM64, Python 3.14.6; Termux phone environment.
- Full command: PYTHONDONTWRITEBYTECODE=1 python -W error::ResourceWarning -m unittest discover -s tests -v
- Full result: 258 tests passed in 25.952 seconds; exit code 0.
- Full log SHA-256: 31a5fabac0ee673231adf1329038fb72c79fddb0c6bd632c0fd254c243b36fef
- Focused command: PYTHONDONTWRITEBYTECODE=1 python -W error::ResourceWarning -m unittest tests.test_capability_registry tests.test_brain_orchestrator tests.test_server tests.test_core.HistoryTests -v
- Focused result: 56 tests passed in 10.733 seconds; exit code 0.
- Focused log SHA-256: 7c8a8073813c06e2b80911e73dc52f0970d1a096da049c4eea02d479010c0810
- Static checks performed: git diff --check; Python compilation for changed Python modules/tests; python -m json.tool manifest.json.
- No live provider call or deployed-service verification was performed. Fake gateway tests are not evidence that a real provider is operational.
- The logs are author-produced local execution artifacts. Their hashes establish byte identity only, not independent authenticity or semantic correctness.

## Candidate implementation map

1. hg/capability_registry.py: versioned HG_RUNTIME_CAPABILITY_REGISTRY_V1; validates domain ownership, capability identifiers, adapter metadata, lifecycle, side-effect class, source revision, declared timeout and invocation budget; rejects duplicate/cross-domain bindings; readiness-gates availability; returns a canonical registry digest and explicit UNBOUND entries.
2. hg/brain_orchestrator.py and hg/contracts.py: versioned worker context; the orchestrator receives only capabilities projected by the registry.
3. hg/server.py: binds memory.search and synthesis.propose to concrete adapters; writes registry snapshot/digest into plan audit and response metadata; requires client Idempotency-Key; rejects key/input conflicts; blocks concurrent duplicates; audits plan/attempt/step/provider/terminal state; verifies memory context against the canonical journal; locks the production HTTP state directory before runtime startup.
4. hg/phone_runtime.py: recovers an orphan provider-start receipt as IN_DOUBT; it does not blindly retry the external provider operation.
5. hg/history.py: rejects reuse of an event ID for a different event type/payload/explicit correlation or causation identity.
6. ui/index.html: reuses the same idempotency key when retrying the same unchanged question, and clears the key when the user changes the question.
7. manifest.json and tests: register the module and cover registry admission, readiness, invocation budgets, audit binding, idempotency, concurrent duplicate requests, recovery, and event-ID conflicts.

## Registry status

- Bound in /api/ask: memory_knowledge.memory.search and research_synthesis.synthesis.propose.
- Unbound and fail-closed: planning_coordination, tools_execution, security_verification.
- Current bindings declare timeout values but set hard_timeout_enforced=false; these are not hard cancellation guarantees.
- Registry lifecycle TESTED describes this candidate's tested adapter contract; it does not mean live-provider or production OPERATIONAL.

## Mandatory release blockers

- P0-A: StateStore is a file-backed journal plus separate projection/head files. Atomic journal-plus-projection recovery and crash consistency are not yet proven; inconsistent state blocks startup rather than providing a complete safe rebuild/reconciliation path.
- P0-B: only two domains are bound; the other three remain unavailable. A frozen deterministic plan/routing oracle and broader adversarial validation remain required.
- P0-C: memory-context source/integrity/ACL/selection bytes are independently rechecked, but a general independent provenance and semantic answer verifier, with false-accept/false-reject corpus, is not implemented.
- P1: hard wall-clock adapter cancellation, exact phone lifecycle/performance and deployed-service evidence, live-provider evidence, and broader threat corpus evaluation remain open.
- Governance: no independent human review artifact was obtained. External literature and STT synthesis must not be represented as a human expert review.

## Release decision

Do not merge or deploy. Keep PR #29 OPEN · DRAFT until the blockers are addressed, evidence is independently reviewed, and the authorized release gate explicitly accepts the candidate. This closure report closes the current R2/R3 implementation iteration with status CANDIDATE_IMPLEMENTED_TESTED_RELEASE_BLOCKED; it does not claim HG2 is production-ready.

## Reproducibility pointers

- Full test log: evidence/HG2-CENTRAL-BRAIN-CLOSURE-20261019/logs/full-regression.log
- Focused test log: evidence/HG2-CENTRAL-BRAIN-CLOSURE-20261019/logs/focused-regression.log
- SHA-256 manifest: evidence/HG2-CENTRAL-BRAIN-CLOSURE-20261019/SHA256SUMS
- Source/runtime manifest: manifest.json
