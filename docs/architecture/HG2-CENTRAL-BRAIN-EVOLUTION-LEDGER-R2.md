# HG2 Central Brain — Evolution Ledger & Evidence Index R2

Date: 2026-10-19
Repository: OAI-GIANG/HG2
Rule: record accepted and rejected decisions, assumptions, evidence boundaries and explicit reconsideration triggers. This is a design ledger; it does not itself authorize code changes or production release.

## 1. Decision ledger

| ID | Decision | State | Rationale | Reconsider when |
|---|---|---|---|---|
| D-001 | One logical Central Brain commands the workflow; capability domains have no independent command authority | ACCEPTED DESIGN | Reduces split-brain planning and simplifies audit | Only if measured availability need proves a delegated design can preserve a single policy/state authority |
| D-002 | Keep five logical capability domains; do not model them as five Git branches or independent agents | ACCEPTED DESIGN | Domains are ownership labels; runtime capability availability depends on real adapters | Rename wire concepts only with versioned contract and compatibility tests |
| D-003 | Keep BrainOrchestrator dependency-free and serial for the first slice | ACCEPTED | Termux ARM64/offline-first, fewer failure modes, stable ordering | Measured need for concurrency plus DAG/side-effect proof |
| D-004 | Keep model output as RESPONSE_ONLY and aggregate PARTIAL | ACCEPTED | Provider response does not prove semantic truth or execution of an external action | Only after a separate verifier is bound to explicit acceptance criteria |
| D-005 | Write model.call.started before calling ModelGateway; block on append failure | ACCEPTED IMPLEMENTATION CHANGE; TESTED | Existing contract/STATE_V1.md requires audit-before-provider and fail-closed audit failure | Reconsider only if contract is formally versioned and alternate durable receipt is proven equivalent |
| D-006 | Do not connect standalone DurableTransactionStore as a second authority | ACCEPTED SAFETY CONSTRAINT | PhoneRuntime currently owns canonical StateStore; standalone DB risks divergent task truth | After transaction boundary is proven atomic on the one canonical store |
| D-007 | Keep PR #29 OPEN/DRAFT; no merge/deploy | ACCEPTED RELEASE DECISION | Durable workflow, trusted registry, independent verifier and exact-runtime operational evidence are open | When every mandatory release gate has evidence and independent acceptance |
| D-008 | Defer dynamic intent classification, parallel dispatch and autonomous architecture mutation | ACCEPTED DEFER | No frozen eval baseline or full action policy; extra concurrency/autonomy expands risk | When representative metrics, authorization and rollback gates are ready |
| D-009 | Treat the ten-entry manifest.json module list as an incomplete/possibly curated map until its intended semantics are confirmed | INVESTIGATE | It omits several source-present modules, but manifest contract does not state whether it is exhaustive | After checking intended manifest contract and runtime consumer expectations |
| D-010 | Require independent review and fixed test oracle for high-risk changes | ACCEPTED DESIGN | Author-generated tests alone do not establish independent acceptance | Revisit workflow mechanics, not the separation-of-duties principle |
| D-011 | Require a client-stable Idempotency-Key for POST /api/ask and bind it to input/principal/source identity | ACCEPTED IMPLEMENTATION; TESTED LOCALLY | Stops repeat calls from ordinary retries and conflicts on key reuse; after restart an uncached answer is not re-issued as a new provider call | Reconsider response recovery only with a defined privacy-safe retention design |
| D-012 | Persist plan/attempt/step/provider receipts in the existing PhoneRuntime StateStore and recover incomplete provider starts as IN_DOUBT | ACCEPTED IMPLEMENTATION; PARTIAL | Adds durable request and step lineage without adding a competing task database | Reopen only after StateStore multi-file transaction/recovery design is proven |
| D-013 | Replace request-local memory-manifest self-check with canonical-history source/integrity/selection verifier | ACCEPTED IMPLEMENTATION; TESTED LOCALLY | Verifier independently re-reads ACL-filtered memory and recomputes lexical selection/context bytes | Does not prove semantic truth of generated answers; extend only with a separately specified verifier contract |
| D-014 | Lock the production HTTP runtime state directory before constructing PhoneRuntime | ACCEPTED IMPLEMENTATION; TESTED LOCALLY | Prevents a second HTTP server from running startup recovery/writes against the same state path | Does not protect arbitrary direct writers bypassing this entrypoint and does not make multi-file journal writes atomic |
| D-015 | Do not claim human independent review from external publications or the STT synthesis | ACCEPTED GOVERNANCE RULE; VERIFIED AGAINST CURRENT PR REVIEW STATE | Current PR #29 has no review submissions and repository collaborator query shows no independent human reviewer | Reconsider only when a real reviewer submits an auditable review artifact |
| D-016 | Project runtime availability from a versioned, fail-closed registry of concrete adapters rather than the static domain map | ACCEPTED IMPLEMENTATION; TESTED LOCALLY | Registry binds adapter identity, contracts, authority, side effects, readiness, lifecycle, source revision, invocation budget and a canonical digest; unbound domains stay unavailable | Revisit composition/multi-adapter support only with a versioned DAG/authority contract and independent tests |

## 2. Rejected alternatives

| ID | Alternative | Decision | Why rejected | Possible reconsideration |
|---|---|---|---|---|
| R-ALT-01 | Five peer brains/agents with equal authority | REJECT | Blurs authority ownership and creates contradictory plans | Only as non-authoritative advisory modules with one policy gate |
| R-ALT-02 | Give the LLM direct unrestricted shell/tool access | REJECT | Unbounded agency and difficult-to-audit side effects | Never; use narrow adapters and external policy |
| R-ALT-03 | Treat model.call.completed as proof of end-to-end success | REJECT | Proves only a provider response was returned and event written | Never without independent output/action verifier |
| R-ALT-04 | Add a separate SQLite database for Brain task state without a one-store design | REJECT FOR NOW | Risk of dual authoritative state and partial commits | Reconsider after atomic shared-state integration is demonstrated |
| R-ALT-05 | Add concurrency as an automatic performance improvement | DEFER | No full DAG/dependency/write-set model; concurrency can complicate failure handling | Only after serial baseline and explicit join/recovery tests |
| R-ALT-06 | Delete old modules or prune branches based on name or apparent duplication | REJECT | Dependency reachability, persisted data and historical references not completely proven | Only after full dependency mapping, compatibility tests and rollback |
| R-ALT-07 | Set numeric performance thresholds before running representative device tests | REJECT | Would invent performance claims not grounded in a baseline | Establish measured baseline on intended device first |

## 3. Evidence index

| Evidence ID/path | Claim supported | What it does not support |
|---|---|---|
| evidence/HG2-CENTRAL-BRAIN-R2-AUDIT-20261019.json | Local baseline/focused/full test results, static checks, source hashes and open gates | Independent source authenticity or production operation by itself |
| evidence/HG2-CENTRAL-BRAIN-R2-AUDIT-20261019.sha256 | Byte digest for the audit JSON file in this checkpoint | Identity, authorization or truth of the underlying claims |
| evidence/logs/HG2-CENTRAL-BRAIN-R2-BASELINE-20261019.log | Pre-patch 240-test baseline; SHA-256 is recorded in JSON | Candidate patch behavior |
| evidence/logs/HG2-CENTRAL-BRAIN-R2-FOCUSED-20261019.log | 34 focused server/brain tests including new negative audit test | Full runtime/provider acceptance |
| evidence/logs/HG2-CENTRAL-BRAIN-R2-FULL-REGRESSION-20261019.log | 241-test post-code-change full suite | Exact deployed phone behavior or semantic answer truth |
| contract/STATE_V1.md | Existing invariant requires pre-call audit and fail-closed behavior on audit write failure | By itself, proof that every code path satisfied the invariant |
| tests/test_server.py | Assertions for call ordering, audit redaction and no gateway invocation on start-audit failure | Proof against every production failure mode |
| docs/architecture/HG2-CENTRAL-BRAIN-REPOSITORY-ARCHITECTURE-MAP-R2.md | Current source-level module/call map and readiness boundaries | Complete dynamic dependency-graph certification |
| docs/architecture/HG2-CENTRAL-BRAIN-CAPABILITY-INVENTORY-R2.md | Five-domain capability bindings and the distinction between declared, bound, tested and operational | Proof that unbound adapters are implemented or operational |
| docs/architecture/HG2-CENTRAL-BRAIN-EXTERNAL-RESEARCH-R2.md | Research URLs, applied design principles and limitations | HG2 feature implementation or third-party certification |
| docs/architecture/HG2-CENTRAL-BRAIN-INDEPENDENT-EXPERT-REVIEW-R2.md | Ten-angle literature-based critical review; 16 versioned source entries; consensus/disagreement and explicit limits | Human expert review or independent certification; neither was obtained |
| docs/architecture/HG2-CENTRAL-BRAIN-MASTER-PLAN-R3.md | Revised plan with eleven traceable review-driven changes and explicit P0/P1/P2 gates | Implementation or production readiness |
| evidence/HG2-CENTRAL-BRAIN-CLOSURE-20261019/logs/focused-regression.log | Candidate focused server/core regression log with 32 tests, exit 0 and SHA-256 recorded in the closure audit | Full-suite-only behavior, live provider, deployed phone runtime, or human review |
| evidence/HG2-CENTRAL-BRAIN-CLOSURE-20261019/logs/full-regression.log | Candidate full suite on Termux/Android 15 ARM64, Python 3.14.6: 258 tests passed with ResourceWarning as error | Exact deployed-runtime correctness or semantic truth of generated answer |
| evidence/HG2-CENTRAL-BRAIN-CLOSURE-20261019/audit.json | Candidate source hashes, host/runtime identity, test evidence, implementation map, unresolved gates and source citations | Independent third-party verification; report is produced by the implementer and declares that limit |
| evidence/HG2-CENTRAL-BRAIN-CLOSURE-20261019/SHA256SUMS | Hash list for saved closure evidence artifacts | Authenticity of the actor or factual truth of the tests beyond the stored artifacts |

## 4. Reconsideration protocol

For each new architecture proposal:
1. Assign a decision ID; state PROPOSED/ACCEPTED/REJECTED/DEFERRED/INVESTIGATE.
2. Capture the source commit and current baseline.
3. State the problem, root cause, alternatives and why each is accepted/rejected.
4. Define a falsifiable hypothesis, fixed test oracle and metrics.
5. Identify permissions, data, side effects, recovery and rollback.
6. Change one bounded component, run negative and regression tests, capture immutable evidence.
7. Record results and known limitations; do not delete rejected decisions.
8. Reopen an old decision only if new evidence, a requirement change, or a measurable threshold justifies reconsideration.

## 5. Final readiness snapshot

- Architecture/design package: documented; local static checks passed.
- Pre-call provider audit remediation: TESTED by targeted and full suite.
- Local test suite: 241 tests passed with ResourceWarning promoted to error.
- Five logical domains OPERATIONAL: NO.
- Durable Brain plan/step/restart recovery: OPEN.
- Trusted runtime capability registry: OPEN.
- Independent external/semantic verifier: OPEN.
- Live provider/deployed phone runtime verification: NOT RUN.
- Merge/deployment authorization: NOT APPROVED; PR #29 remains Draft.


## 6. Candidate closure update — 2026-10-19

- Full local regression suite: 258 tests passed in 25.952 seconds with ResourceWarning promoted to an error on Termux Android 15 ARM64 / Python 3.14.6. Focused registry, Brain and server suites are recorded separately in the closure evidence folder.
- Candidate changes add durable request/plan/attempt/step receipts, stable HTTP idempotency, no duplicate provider call on a replay, startup recovery to IN_DOUBT for a provider start without a terminal receipt, context/source verification, conflicting event-id rejection, and a production HTTP process lock.
- Remaining hard blockers for a release claim: file-backed StateStore journal/projection atomic recovery, three unbound domain adapters, hard wall-clock adapter timeout, independent semantic answer verification, a frozen evaluation oracle, exact-device lifecycle/performance/deployed service evidence, a live-provider test, and a real independent human review artifact.
- This is implementation evidence from the author-controlled Termux environment, not an independent review or production certification. PR #29 remains OPEN / DRAFT.


## 7. Closure state after final candidate regression — 2026-10-19

- evidence/HG2-CENTRAL-BRAIN-CLOSURE-20261019/closure-report.md is the authoritative bounded closure report for this candidate.
- Full regression result: 258 tests passed; exact command, runtime identity and log digest are recorded there. This is local implementation evidence, not release certification.
- Runtime registry implementation is present and tested. Current /api/ask binds two adapters only; the remaining three domains are unbound and fail closed. Timeout values are declared but hard cancellation is not enforced.
- R2/R3 design-and-candidate implementation work is closed for this iteration with status CANDIDATE_IMPLEMENTED_TESTED_RELEASE_BLOCKED; production/release gates are not marked complete.
- PR #29 must remain OPEN / DRAFT; no merge or deployment is authorized by this closure.
