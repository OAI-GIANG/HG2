# HG2 — Unified Brain Group: Capability Audit & Implementation Matrix
Date: 2026-10-18
Scope: OAI-GIANG/HG2 only
Audit target: candidate branch stt/hg2-circulatory-architecture-20261018
Candidate commit: f662b42426b22d2f526c49318adb5cf4089360d5
Canonical remote hg-genesis observed during audit: 9d83a113ccdf1aeda656e494593fa55b9078c803
PR: https://github.com/OAI-GIANG/HG2/pull/25 (OPEN, DRAFT, unmerged)
Audit type: READ-ONLY source/evidence audit. No source code, commit, push, merge, deploy, service restart, or live-state migration was performed.

## 1. Executive outcome

Status: DESIGN BASELINE PROPOSED; UNIFIED BRAIN IMPLEMENTATION INCOMPLETE; NOT RELEASED.

HG2 has one thin application entry point (hg.agent.HGAgent) above a bounded tool loop (hg.toolplane.ToolPlane), plus separate modules for policy, workflow, identity, provider, event history/state, sync, migration, and recovery. The separation is useful, but it is not yet a complete Brain Group that demonstrably performs perception, knowledge retrieval, reasoning/planning, governed learning, creative synthesis, experimentation, evaluation, and bounded evolution.

No separate competing runtime-brain module was found among registered runtime modules. But orchestration-adjacent services are not yet wired through one demonstrable cognitive controller. They should remain subordinate services, not peer commanders.

The HG-native intelligence v2.1 materials in tests/fixtures are synthetic fixtures and oracle specifications. Their own closure report says HG implementation acceptance is NOT_RUN and these fixtures do not invoke HG. They are not proof of actual learning or creativity behavior.

## 2. Baseline and evidence

- Device and checkout: Termux; /data/data/com.termux/files/home/hg2-circulatory-architecture-20261018.
- Branch: stt/hg2-circulatory-architecture-20261018; working tree clean.
- Candidate HEAD: f662b42426b22d2f526c49318adb5cf4089360d5.
- Remote refs queried during audit: hg-genesis = 9d83a113ccdf1aeda656e494593fa55b9078c803; candidate branch = f662b42426b22d2f526c49318adb5cf4089360d5.
- PR #25 is OPEN and DRAFT, base hg-genesis at 9d83a113ccdf1aeda656e494593fa55b9078c803, head f662b42426b22d2f526c49318adb5cf4089360d5.
- CI: ci/circleci: verify PASS, job 222.
- Current full test run: PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest discover -s tests → 190 tests PASS in 6.678 s, Android 16 / Python 3.14.6.
- git diff --check PASS; checkout remains clean.
- Existing evidence bundles report earlier commits and test counts (112/162/165/190). Do not treat earlier commits' summaries as exact-HEAD evidence.
- No live provider call, runtime state mutation, live data migration, learning experiment, or deployment occurred in this audit.

## 3. Single command hierarchy

1. **HG Brain Group** — the sole cognitive authority that interprets the user goal, retrieves knowledge, decides and arbitrates plans, coordinates subordinate capabilities, evaluates evidence, and proposes improvements.
2. **Internal Brain functions** — perception, reasoning/planning, knowledge/memory, policy consultation, orchestration, learning, creativity, self-monitoring, experimentation/evaluation, identity/history stewardship, capability management. These are internal functions of the same group, not peer commanders.
3. **Guarded execution layer** — policy/approval, workflow, typed capability ports, provider and tool adapters. They execute only requests dispatched by Brain under policy; they do not independently redefine the goal.
4. **Kernel/state authority** — hg.phone_runtime remains the composition root and canonical state boundary. Exactly one selected store owns durable state. This is infrastructure authority, not a second cognitive brain.
5. **Evidence/recovery** — report integrity and recovery evidence; cannot self-certify or silently repair/promote state.
6. **External providers/relay** — optional subordinate adapters with no canonical state ownership or independent task authority.

“One Brain Group” does not mean one monolithic source file or process. It means one owner for cognitive decisions and plan arbitration while retaining modular boundaries. No module can bypass policy or write another module’s private state.

## 4. Implementation audit matrix

Status definitions: IMPLEMENTED (UNIT-TESTED) means source plus direct tests for a defined scope; PARTIAL means primitives exist but no complete end-to-end capability; DESIGN ONLY means no implementation found; FIXTURE ONLY means synthetic fixtures rather than actual HG behavior; NOT VERIFIED means evidence cannot support an active/production claim; OVERLAP means responsibilities need a single owner.

| Capability | Source and observed evidence | Status | Disposition |
|---|---|---|---|
| Goal intake / turn entry | hg/agent.py HGAgent.ask; hg/toolplane.py ToolPlane.ask | PARTIAL, tested. Agent is a thin wrapper, not a planner. | KEEP as public Brain facade; expand through typed internal interfaces. |
| Perception / context normalization | prompt validation, provider tool-call parsing, hg.contracts JSON/schema validation | PARTIAL. No typed report separating facts, inferences, unknowns and conflicts found. | ADD PerceptionReport to Brain using existing contract primitives. |
| Reasoning / multi-step planning | bounded provider/tool loop; hg.workflow task state machine | PARTIAL. Iteration is not explicit plan construction/evaluation; workflow manages execution lifecycle. | ADD planner inside Brain; keep workflow subordinate. |
| Memory / knowledge retrieval | hg.history StateStore; hg.sqlite_state SQLiteStateStore; history verify/summary/recent tools | PARTIAL. Event history is audit memory; no full knowledge retrieval, claim provenance, relevance ranking or contradiction resolution. | KEEP event history authoritative; add a derived, rebuildable knowledge index with lineage. |
| Rules / authorization | hg.policy grant/approval predicates; hg.auth authenticates; hg.authority re-exports policy functions | Authorization primitives implemented/tested, integration partial. Not proven that every future mutation path is centrally mediated; ApprovalService not on the current HGAgent ask path. | KEEP hg.policy sole policy owner; keep authority facade compatibility-only or remove in separately gated change. |
| Command / orchestration | hg.agent -> hg.toolplane; current tool allowlist includes identity/history/session actions | PARTIAL. Bounded tool loop exists, but no unified goal decomposition/plan arbitration to workflow. | KEEP one entrypoint; add one internal Brain controller seam. |
| Nervous system / signal routing | hg.contracts, hg.workflow, hg.toolplane, hg.sync | PARTIAL with overlapping vocabulary. No single versioned Brain command/result protocol across them is demonstrated. | CONSOLIDATE protocol vocabulary; keep module owners separate. |
| Learning from feedback | no runtime learning service found; fixture package specifies feedback-delta scenarios | FIXTURE ONLY / runtime gap. | ADD proposal-only learning inside Brain; no automatic live policy/code changes. |
| Creativity / synthesis | creative scoring examples in fixtures; no runtime synthesis/evaluation pipeline found beyond provider output | FIXTURE ONLY / runtime gap. | ADD option generation/comparison with rationale, novelty delta, assumptions, feasibility and tests. |
| Self-monitoring / confidence | PhoneRuntime.health, state verify, bounded tool/provider error handling | PARTIAL; operational health is not epistemic self-monitoring. | ADD BrainAssessment with confidence, evidence coverage, limitations and escalation. |
| Experimentation / verification | unit tests, evidence summaries, code scanner, fixture validator | PARTIAL. No governed experiment ledger with baseline, hypothesis, metrics and rollback found. | ADD experiment records and a controlled runner boundary. |
| Identity / provenance / history | hg.identity, canonical event digests, history verification, manifest and fixture checksums | Implemented for scoped identity/integrity, not truth or authority. | KEEP one identity/history; link knowledge claims to source events/artifacts. |
| Capability lifecycle | fixed allowlist in toolplane; policy scopes | PARTIAL. No unified catalog of owner, interface version, readiness, risk, resources and rollback. | ADD read-only inventory; discovery must not grant authorization. |
| Evidence acceptance | full tests, evidence summaries, CI | PARTIAL; exact candidate tests pass, production is not proven. | KEEP one evidence owner; tie status to revision/environment/artifact digests. |
| Runtime canonical state | phone_runtime selects one backend; legacy default and SQLite opt-in; migration/recovery helpers | Persistence primitives tested; production cutover not certified. | KEEP one phone composition root and one selected store; no silent migration. |
| Sync/remote relay | hg.sync dispatcher, SQLite outbox/cursor, hg.edge | Partial/tested bounded contracts; live remote transport not verified. | KEEP post-commit subordinate flow; relay is not a second authority. |
| Voice I/O | PR #26 draft, not in runtime manifest | NOT INTEGRATED / NOT VERIFIED. | Keep optional until language, license, resource and consent gates pass. |
| Developer code intelligence | tools/hg_code_intelligence.py, static bounded Python analysis, excluded from runtime manifest | Implemented for limited documented scope; not a runtime Brain capability. | KEEP dev-only; future reports can inform proposals through explicit evidence input. |

## 5. Six new capabilities inside the Brain Group

### B1 — Proactive need and gap detection
Inputs: user goal, current context, capability catalog, constraints, unknowns, failed outcomes.
Output: NeedReport items with description, trigger, impact, confidence, evidence references, missing information, and safest next step.
Rules: distinguish blockers from optional improvements; no invented evidence; detection alone causes no side effects.
Acceptance: detect seeded missing dependency, conflicting requirement, stale knowledge and unsupported request with correct references; measure false-positive rate on held-out cases.

### B2 — Knowledge assessment and selective admission
Inputs: candidate knowledge, provenance, time/version, applicability, evidence and conflict candidates.
Output: KnowledgeDecision = ACCEPT, PROVISIONAL, REJECT, SUPERSEDE or NEEDS_REVIEW, with reason, owner, sources, confidence and verification state.
Rules: distinguish fact, inference, hypothesis, user assertion, policy and historical decision; reputation is not proof; corrections append lineage rather than silently rewriting the past.
Acceptance: missing provenance is never ACCEPT; conflicts stay unresolved or use explicit precedence; decisions are replayable.

### B3 — Synthesis and invention
Inputs: goal/constraints, verified and provisional knowledge, prior HG solutions, authorized external references and capability limits.
Output: at least two meaningfully distinct options when feasible, including novelty delta, assumptions, expected benefit, resource cost, risks, counterexamples and comparison with a simple baseline.
Rules: references are inspiration, not automatic truth or copied implementation; record HG's own transformation and tests; do not claim uniqueness without evidence.
Acceptance: held-out tests separate superficial restatement from mechanism changes; scoring is reproducible; unsupported facts are flagged; infeasible options are filtered before ranking.

### B4 — Controlled experimentation and verification
Inputs: explicit hypothesis, baseline revision, scope, metrics/oracles, resource budget, stop and rollback conditions.
Output: ExperimentRecord with revision/digest, hypothesis, environment, actions, raw results, metrics, conclusion, evidence refs, rollback result and status.
Rules: default to static/dry-run; execution requires authorization and isolation; exploratory experiments never mutate live/canonical state; test results apply only to the tested artifact/environment.
Acceptance: repeatability within declared bounds; partial/failed runs cannot aggregate to PASS; rollback proves pre-state restoration or remains BLOCKED.

### B5 — HG identity and development-history stewardship
Inputs: canonical product identity, repository/revision/tree, references, decisions, experiments and capability changes.
Output: append-only DevelopmentRecord linking actor/action/reason, provenance, old/new digest and gate result.
Rules: HG's own history stays in OAI-GIANG/HG2; external references remain labeled external and cannot rewrite HG history. Digest integrity is not authority or truth.
Acceptance: every accepted capability has source and decision lineage; missing/tampered lineage is detected; provider output cannot change identity.

### B6 — Capability inventory and lifecycle
Inputs: manifest, import/dependency graph, policy scopes, tests, runtime wiring, resource/platform constraints and external dependencies.
Output: CapabilityRecord with ID, owner, interface version, status, dependencies, risk class, resource budget, permission scope, evidence refs, lifecycle and rollback method.
Lifecycle: PROPOSED -> SPECIFIED -> IMPLEMENTED -> TESTED -> INTEGRATION_VERIFIED -> RUNTIME_VERIFIED -> RELEASED; failure moves to BLOCKED or ROLLED_BACK with evidence.
Rules: inventory/readiness is distinct from authorization; discovering a capability never grants permission.
Acceptance: detect manifest/code/test mismatches; capabilities without evidence cannot be verified; unauthorized capabilities cannot execute.

## 6. Internal contracts and shared signal protocol

Define versioned typed schemas:
- BrainRequestV1: request_id, goal, user_context_ref, constraints, requested_outcome, deadline, risk_tolerance, correlation_id, source_revision.
- PerceptionReportV1: facts, inferences, unknowns, conflicts, user_constraints, evidence_refs, confidence_by_claim.
- KnowledgeQueryV1 / KnowledgeItemV1: query, scope, relevance, source/artifact, digest, provenance class, observed_at, validity window, claim type, confidence, lifecycle status.
- PlanV1: plan_id, goal_digest, ordered_steps, dependencies, alternatives, risks, stop_conditions, rollback_plan_ref, expected_outputs, required_permissions.
- CapabilityRequestV1: capability_id, interface_version, input_digest, principal_ref, risk_class, idempotency_key, deadline, approval_ref, correlation_id.
- CapabilityResultV1: request_id, status (SUCCESS/FAIL/BLOCKED/PARTIAL/NOT_RUN), output_digest, error_code, side_effect_summary, evidence_refs, duration, retryable.
- LearningProposalV1: observed_gap, supporting_events, hypothesis, proposed_delta, expected_gain, regression_risk, required_tests, approval_gate.
- ExperimentRecordV1: baseline revision/digest, hypothesis, method, environment, limits, metrics, raw artifact digests, conclusion, rollback status.
- BrainAssessmentV1: confidence, evidence_coverage, limitations, missing_evidence, escalation_required, status.
- AcceptanceDecisionV1: gate_id, target_revision, status, evaluator, criteria_digest, evidence_refs, reasons, rollback_requirement.

Protocol invariants:
1. Every message has a schema version, request/correlation IDs, source revision, typed status and bounded size.
2. Provider/tool output is untrusted; it cannot rewrite policy, identity, plan authority or permissions.
3. Fact, inference, hypothesis and instruction remain distinct fields.
4. A response is not success until CapabilityResult status is SUCCESS and evidence satisfies the declared gate.
5. Mutations pass the single policy owner, validate inputs, use idempotency and commit through PhoneRuntime's selected store.
6. No cross-module private writes and no ambient shell/filesystem/network authority.
7. Retries are bounded, deadline-aware and idempotent; uncertain side effects return PARTIAL/BLOCKED, not false SUCCESS.
8. Semantic indexes/caches/provider context are derived and rebuildable, never a second source of truth.

## 7. Knowledge lifecycle and learning safety

Lifecycle:
CAPTURED -> NORMALIZED -> PROVENANCE_CHECKED -> ASSESSED -> PROVISIONAL or ACCEPTED -> INDEXED/RETRIEVABLE -> PERIODICALLY_REVALIDATED -> SUPERSEDED/REVOKED/EXPIRED.

Any stage can move to REJECTED or NEEDS_REVIEW with a reason. Corrections append new events linked to corrected and dependent claims; original records remain auditable. Acceptance is scoped by claim, time, source and environment, not universal certainty.

Claim classes:
- FACT: independently supported and linked to evidence.
- USER_ASSERTION: attributed to the user; not automatically externally verified.
- INFERENCE: derivation with premises and confidence.
- HYPOTHESIS: testable proposal, not fact.
- POLICY: controlled by hg.policy/governance; knowledge cannot overwrite it.
- HISTORICAL_DECISION: immutable record of what was decided at a point in time.
- EXTERNAL_REFERENCE: attributed source with license/provenance assessment.
- SYNTHESIS: HG-derived proposal with source links and transformation notes.

Learning may write only to a staging/proposal ledger until promotion. It cannot silently change code, policy, grants, live configuration, identity or canonical state. Promotion requires evidence, tests on the exact revision, regression/security checks, authorized acceptance where required, and demonstrated rollback. The component that proposes a change cannot certify its own success.

## 8. Unified Brain loop

1. Intake: validate request/identity and risk.
2. Perceive: normalize goal, constraints, facts, unknowns, conflicts and evidence.
3. Retrieve: obtain relevant accepted/provisional knowledge without mixing authority levels.
4. Reason/plan: make PlanV1 with alternatives, risks, deadlines, permissions and rollback.
5. Gate: hg.policy decides whether each action is allowed; required approvals remain binding.
6. Execute: route steps through workflow/capability adapters via runtime.
7. Verify: compare actual results with declared acceptance oracle; attach exact evidence.
8. Reflect: compare expected and actual outcomes; produce a learning proposal only.
9. Admit: knowledge gate checks provenance/conflicts/scope; accepted deltas are appended and indexed.
10. Close: report SUCCESS/PARTIAL/BLOCKED/NOT_RUN accurately with evidence and residual risks.

## 9. Implementation matrix

| ID | Function | Current owner | Disposition / first slice | Tests | Rollback / stop rule |
|---|---|---|---|---|---|
| IM-01 | Brain facade | hg.agent.HGAgent | KEEP + EXPAND; retain public entry, add typed internal controller after contract tests | existing agent/toolplane tests, dependency graph, baseline equivalence | preserve old route until equivalent; stop if policy path bypassed |
| IM-02 | Provider/tool loop | hg.toolplane.ToolPlane | KEEP subordinate; preserve allowlist and bounded loops; executor port, not planner | invalid args, loop/call limits, malicious provider, no unapproved side effects | revert adapter wiring; never broaden allowlist as shortcut |
| IM-03 | Sole policy | hg.policy | KEEP as sole owner; route every mutation through it; confirm approval reachability | deny-by-default, invalid principal, self-approval, expired/revoked grant, every entrypoint | block all mutations if any bypass appears |
| IM-04 | Authentication | hg.auth | KEEP sealed principal model | missing/bad/ambiguous credential, boolean impostor, invalid scopes | fail closed; never use authenticated=True shortcut |
| IM-05 | Workflow | hg.workflow | KEEP + WIRE UNDER BRAIN as executor-facing state machine | dependency failures, retries, cancel/deadline, approvals, idempotency | revert new wiring only; preserve persisted event history |
| IM-06 | Kernel/state owner | hg.phone_runtime + selected store | KEEP single owner; no live backend change in this work | exactly one store, conflict, failed commit, concurrency, crash, offline | stop on ambiguous owner; restore only from verified backup |
| IM-07 | Event/history | hg.history + hg.contracts | KEEP; reuse canonical serializer/parser/digest | malformed JSON, duplicate keys, corruption, replay, missing provenance | stop mutations on integrity failure; preserve evidence |
| IM-08 | SQLite store | hg.sqlite_state | KEEP opt-in; isolated dirs only until migration acceptance | migration, replay, atomicity, idempotency, power-loss, rollback drill | no dual-write; do not switch live environment casually |
| IM-09 | Knowledge retrieval | history + future knowledge adapter | ADD derived/rebuildable index; events remain authoritative | relevance, staleness, contradictions, attribution, deterministic rebuild | drop/rebuild index; never delete source events |
| IM-10 | Perception | prompt + schema parsing | ADD pure PerceptionReport normalizer | adversarial, contradictory, missing fields, claim/evidence alignment | test-only fallback to old path; no canonical writes |
| IM-11 | Reasoner/planner | agent/workflow boundaries | ADD inside Brain; model plan is an untrusted proposal | decomposition, constraints, cycles, infeasible plan, counterexample, bounds | reject plan/fall back safely; no side effects before policy |
| IM-12 | Learning | none found at runtime | ADD proposal-only staging | missing provenance, conflicts, regression, replay, denied promotion | discard staged proposal, not canonical data |
| IM-13 | Creativity | fixture-only today | ADD alternative generator/comparator | distinctness, feasibility, novelty delta, counterexamples, deterministic scoring | feature flag OFF; retain baseline response |
| IM-14 | Self-monitoring | health/verify/error paths | EXTEND with BrainAssessment; keep technical health separate | calibrated known/unknown cases, false confidence, escalation | block high-risk actions when confidence/evidence gate fails |
| IM-15 | Gap detection | none found at runtime | ADD read-only NeedReport | missing evidence/dependency, stale knowledge, conflicts, false positives | disable advisory feature; no state mutation |
| IM-16 | Knowledge admission | none found at runtime | ADD lifecycle/append-only correction chain | provenance, conflict policy, expiry, supersede, replayability | rebuild derived index; retain ledger and raw evidence |
| IM-17 | Identity/provenance | hg.identity/contracts/history | KEEP + add trace links | manifest tampering, invalid revision, digest/authority distinction, correction lineage | reject invalid provenance; never rewrite history |
| IM-18 | Capability lifecycle | manifest/allowlist/policy | ADD read-only catalog from source/tests/runtime wiring | unregistered module, untested active flag, unauthorized dispatch | revert projection; do not grant permissions |
| IM-19 | Shared signals | contracts/workflow/toolplane | CONSOLIDATE schema vocabulary, not code owners | schema mismatch, untrusted fields, correlation, payload bounds | retain existing persisted shape until migration is separately proven |
| IM-20 | Sync/relay | hg.sync, SQLite outbox, hg.edge | KEEP post-commit transport only | bad auth/ack, duplicate, cursor regression, outage, secret redaction | keep pending outbox; relay cannot become primary |
| IM-21 | Recovery/migration | hg.recovery, hg.migration | KEEP separate operational service; Brain can request/report, not auto-promote | corrupt/stale backup, wrong lineage, non-empty target, source immutability | quarantine candidate; no overwrite/promotion under uncertainty |
| IM-22 | Evidence/acceptance | evidence summaries/tests/CI | CONSOLIDATE statuses and exact revision provenance | stale evidence, forged PASS, missing evidence, aggregation | mark BLOCKED; no release from narrative |
| IM-23 | Code intelligence | tools/hg_code_intelligence.py | KEEP developer-only; proposal/evidence input only | bounds, incomplete coverage, stale revision, symlink/secret exclusion | disable tool; runtime unaffected |
| IM-24 | Voice | PR #26 | KEEP optional and inactive until quality/license/resource/consent gates pass | Vietnamese quality, latency/RAM, permissions, opt-in, TTS/ASR, license | leave unwired/unregistered |
| IM-25 | Compatibility facade | hg.authority | KEEP temporarily or remove later behind import-compatibility gate | repo-wide imports, consumers, policy equivalence | keep thin facade if consumer unknown; no duplicate policy |
| IM-26 | Role hierarchy | manifest and architecture contract | CONSOLIDATE design metadata around one Brain group and subordinate layers | dependency rules, no second orchestrator/provider/policy/state owner | revert metadata if tooling breaks; no runtime-state impact |

## 10. Acceptance gates for the Unified Brain

- G0 Baseline: exact source commit/tree, clean checkout, canonical ref recorded.
- G1 One commander: every user goal enters one Brain facade; trace proves no peer planner arbitrates independently.
- G2 One policy owner: every mutating capability path is authorized by hg.policy; denied action cannot mutate durable state.
- G3 Contracts: messages validate schema/version/size, request/correlation and provenance; unknown schemas fail closed.
- G4 Knowledge truthfulness: facts/inferences/hypotheses/user assertions remain distinct; missing provenance cannot be marked verified.
- G5 Plan correctness: constraints, alternatives and risks are represented; infeasible plans cannot dispatch.
- G6 Capability mediation: registry status never implies permission; only explicitly granted and in-scope capabilities execute.
- G7 Experiment safety: exact baseline, isolated target, bounded resources, reproducible metrics, stop conditions and rollback evidence.
- G8 Learning safety: deltas remain proposals until tested and accepted; no self-modification of policy/identity/runtime.
- G9 Evidence: every PASS ties to exact candidate revision, environment, test command and artifact digest; missing evidence is BLOCKED/NOT_RUN.
- G10 Runtime: phone is sole canonical state owner; no dual writers; production integration waits for migration/recovery acceptance.
- G11 Regression: exact-head full suite, security negatives, dependency checks and side-effect tests pass.
- G12 Rollback: each integration has an OFF/compatibility seam; rollback preserves prior behavior/history; schema migration needs a proven restore path.
- G13 Release: no release before runtime provenance, trust/credential, resource, backup/restore and target installation gates pass.

## 11. Rollback and stop rules

- Specification-only work is reversible by dropping the spec change; no live impact.
- Pure functions are implemented on isolated branches with direct unit tests; remove new modules/wiring while preserving the prior entrypoint and persisted schema.
- Wiring defaults OFF until acceptance; tests must prove OFF retains prior behavior.
- Stateful features begin in disposable test directories. Never dual-write legacy and SQLite. Migration requires source manifest/digest, source immutability, empty target, backup, restore drill and exact rollback.
- This plan itself authorizes no hot replacement, deployment or production runtime change.
- Stop immediately on policy bypass, ambiguous state owner, unknown schema, secret leak, false success, non-idempotent retry, missing evidence or failed rollback.
- A process exit code alone does not prove rollback.

## 12. Recommended execution order

1. Freeze the Brain Group contract and hierarchy.
2. Implement pure schemas, PerceptionReport/BrainAssessment, dependency tests and a single-controller trace.
3. Wire existing workflow beneath Brain and prove all mutations pass policy.
4. Add read-only capability catalog and knowledge retrieval/lineage.
5. Add proactive gap detection and creativity comparison as non-mutating functions.
6. Add proposal-only learning and experiment/evidence records.
7. Only after those gates, consider semantic memory, adaptive model routing, voice and broader autonomy.
8. Integrate one work package at a time; no big-bang rewrite or release while gates are open.

## 13. Final decision

Do not create a second peer brain and do not add all six capabilities into runtime in one patch. First establish one Brain Group contract, then build internal capabilities around existing owners, beginning with read-only and proposal-only functionality.

Current candidate suite is PASS (190/190), but full cognitive behavior and production runtime acceptance remain NOT VERIFIED. PR #25 remains draft/unmerged. Canonical hg-genesis was not changed by this audit.
