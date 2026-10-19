# HG2 — Central Brain Intelligence, Evidence-Driven Governance & Controlled Evolution — Master Plan R3

- Review date: 2026-10-19
- Repository: OAI-GIANG/HG2 only
- Supersedes as planning baseline: R2, without rewriting or erasing its history
- Evidence basis: source-grounded R2 repository audit plus literature review in [Independent Expert Review R2](HG2-CENTRAL-BRAIN-INDEPENDENT-EXPERT-REVIEW-R2.md)
- Review classification: EXTERNAL EVIDENCE + STT SYNTHESIS. No human independent reviewer has been engaged or evidenced. This is not an independent certification.
- Current candidate branch: stt/hg2-brain-orchestrator-r1-20261019
- R2 source candidate: 48c3b2216158e797e3de7ee651db5c870a94ef74
- Release posture: OPEN / DRAFT; no merge or production deployment authorized by this plan.

## 1. MTC-1.0 — Master Task Controller

### OBJECTIVE
Develop a single logical command brain for intake, classification, planning, bounded capability routing, controlled execution, independent verification, architecture governance, knowledge provenance and reversible evolution.

### SCOPE
- OAI-GIANG/HG2 is the sole execution repository.
- Central Brain is the only logical task authority; domain capabilities, skills, tools and modules are subordinate mechanisms, not peer command authorities.
- Initial inventory and verification are READ-ONLY. Implementation changes follow a separately reviewed patch plan.
- No capability is considered available merely because its name appears in a static registry, prompt, document, branch, fixture or test.
- Prefer Python standard library and offline-first operation when feasible; add dependencies only with a documented value, compatibility and supply-chain assessment.
- No autonomous delete, merge, deployment, privilege escalation or other irreversible action without explicit policy and authorization checks.

### INPUT
R1/R2 plans; current source, tests, configuration, history and runtime evidence of HG2; standards and external technical sources with versions and access dates; current failure findings and acceptance oracles.

### OUTPUT
1. Source-grounded architecture and capability inventory.
2. External Evidence & Critical Review Matrix.
3. Finding, dependency, duplication and authority-conflict matrices.
4. Versioned target contracts and state-transition model.
5. Component disposition decisions with rollback.
6. Frozen positive, negative, adversarial and recovery tests.
7. Minimal end-to-end flow with durable state and independent verification.
8. Target-device operational evidence and resource measurements.
9. Evidence index, change traceability, checkpoint and readiness report.
10. Separate record of any actual human independent review, if obtained.

### ACCEPTANCE CRITERIA
- Every important claim is bound to source/revision, command or method, result and limitations; unknowns remain UNKNOWN.
- Every capability has one logical owner, typed contract, principal/resource/action policy, side-effect class, timeout, budget and verification criteria.
- Model output is a proposal, never an authorization or canonical state mutation by itself.
- Workflow task state has exactly one authoritative persistence owner; state, audit intent and idempotency are transactionally bound where they share a database.
- External side effects are treated as distributed boundaries; no blanket exactly-once claim. Ambiguous outcome is represented as IN_DOUBT and reconciled or escalated without blind retry.
- Independent verification reads evidence independently of the executor and tests false acceptance and false rejection.
- Acceptance includes positive, negative, prompt-injection, forged-evidence, fault-injection, crash/restart, replay and rollback cases.
- Production promotion requires target-runtime evidence, security review, independent human review where policy requires it, and explicit release acceptance.
- Metrics are measured against a representative frozen baseline; a composite score cannot hide a critical failure.

### EVIDENCE
Each evidence record contains: ID; source URL or repository path; source/version/access time; target device/runtime; commit/tree and worktree status; exact method/command; exit status; test inventory; artifact/log digest; claim supported; limitations; verifier; and status. A hash proves byte consistency only, not factual truth, identity, authorization or reviewer independence.

### RISKS
Planner misclassification; direct/indirect prompt injection; excessive agency; forged evidence; stale memory; duplicate side effects after retry; split-brain state; process termination; unbounded latency/cost/storage; test-oracle bias; supply-chain compromise; irreversible changes without recovery.

### STOP CONDITION
Stop if repository/branch identity is wrong; worktree changes are unexplained; authority or canonical state owner is ambiguous; evidence integrity fails; a mandatory capability is missing; a side effect could be duplicated without reconciliation; a destructive change has no tested recovery path; or the action exceeds the approved scope.

### NEXT ACTION
Close P0 state durability, request idempotency, IN_DOUBT reconciliation and authority-boundary tests before enabling additional execution capabilities.

## 2. Architecture decision

Retain nine logical responsibilities: Intake & Context; Central Planner; Capability Registry & Router; Workflow State Manager; Execution Layer; Independent Verification; Architecture Governance; Knowledge & Evolution; Cross-Cutting Controls.

They are responsibilities, not a mandate to create nine services or agents. Start with explicit in-process contracts. Split a responsibility only if measured contention, fault isolation, permission separation, independent release cadence or testability demonstrates net value.

### Required control flow
1. Validate request envelope and caller identity.
2. Separate untrusted content from policy/authority.
3. Retrieve context with source, scope, freshness and provenance.
4. Produce a typed plan proposal.
5. Validate graph, capabilities, permissions, budgets, deadlines and evidence requirements deterministically.
6. Persist task/step intent and audit intent under one canonical state owner before dispatch.
7. Execute through narrow adapters with timeout, resource limit and stable idempotency.
8. Persist the result or IN_DOUBT before acknowledging terminal status.
9. Resolve evidence independently; hash/schema checks alone are not semantic verification.
10. Record decision, evidence, limitations and whether human review occurred.

## 3. External critical-review conclusions

The detailed source-by-source review is in [HG2-CENTRAL-BRAIN-INDEPENDENT-EXPERT-REVIEW-R2.md](HG2-CENTRAL-BRAIN-INDEPENDENT-EXPERT-REVIEW-R2.md). The key design consequences are:

- Workflow vs agent: deterministic workflow by default; model proposes; validator owns acceptance.
- Retry vs duplicate effects: define per-operation semantics; use stable idempotency and IN_DOUBT; never claim global exactly-once.
- One command brain vs single point of failure: one logical authority, modular internals, bounded queue and explicit recovery.
- Provenance vs truth: provenance binds origin/history; independent checks establish claim validity to a stated level.
- Memory vs task state: memory is contextual knowledge, not authoritative workflow state; volatile facts require source-of-truth reads.
- Phone-first vs Android lifecycle: explicitly test process kill, reboot, screen-off, network transition and low-storage behavior on the target device.
- Autonomy vs safety: authorization is enforced outside model-generated content; read-only adapters precede write-capable adapters.
- Module separation vs complexity: no service/agent split without measurable value.
- External guidance vs independence: published standards are external evidence, not a human review of HG2.
- Testing vs proof: frozen oracle and adversarial cases must be independent enough to detect shared implementation/test assumptions.

## 4. Priority roadmap and gates

### Gate P0-A — Durable workflow state and idempotency
- Map StateStore, WorkflowService and DurableTransactionStore ownership and transactions.
- Use a single canonical task/step authority; do not create a second workflow database.
- Specify stable client request ID, canonical request digest, plan digest, state version, attempt count, deadline, side-effect class and evidence references.
- Specify states including QUEUED, STARTED, SUCCEEDED, FAILED, BLOCKED and IN_DOUBT; define legal transitions and compare-and-set/version conflict behavior.
- Crash-test after every persistence boundary and around provider dispatch/result persistence.
- Do not blindly replay an external operation when acceptance may have occurred but its result is unknown.

### Gate P0-B — Trusted registry and deterministic planner validation
- Registry entry must bind capability ID to code adapter, contract version, owner, allowed principals/actions/resources, side-effect class, timeout, budget, health and verification state.
- Static allowlist is not a grant of authority or proof of runtime availability.
- Test unknown capability, stale/unhealthy adapter, dependency cycle, privilege escalation, scope expansion and over-budget plans.

### Gate P0-C — Independent evidence verifier
- Bind claim to exact artifact bytes, source revision, environment and method.
- Test forged success, altered log, missing artifact, stale source and valid hash of semantically false content.
- Separate executor identity and verifier method; record what was independently rerun versus merely inspected.

### Gate P1-A — AI security and knowledge quality
- Maintain frozen direct/indirect prompt-injection, data-exfiltration and excessive-agency corpus.
- Enforce authorization in adapters, not model prompts.
- Add memory provenance, freshness, scope, contradiction and supersession contracts.
- Add unbounded-consumption budgets and per-task telemetry.

### Gate P1-B — Target-device reliability and governance
- Exercise screen-off, process kill, reboot, network loss/recovery, low storage, corrupt checkpoint and restore on the exact supported phone configuration.
- Keep separate permissions for commit, push, merge and deploy.
- Require migration recovery evidence as well as code rollback evidence.

### Gate P2 — Measured evolution
- Establish frozen routing and answer-quality oracle, performance baseline, resource/cost budgets and test-set governance.
- Add parallel execution or extra services only when measured outcomes justify added complexity.
- Run a periodic review of source freshness and risk taxonomy versions.

## 5. Component disposition policy

For each component choose KEEP, IMPROVE, MERGE, REPLACE, DEPRECATE, DELETE, QUARANTINE or INVESTIGATE. Record evidence, owner, dependency graph, benefit, risk, migration, rollback, test result and confidence. Prefer quarantine/deprecation before deletion if safety is not proven. No disposition automatically authorizes a destructive operation.

## 6. Required tests and acceptance oracle

Minimum fixed tests:
- Request schema, identity, scope and size validation.
- Planner malformed output, cycle, unknown capability and budget overrun.
- Authorization denial regardless of prompt/model request.
- Direct and indirect prompt injection, exfiltration and confused-deputy attempts.
- State version conflict and duplicate client request.
- Crash after state commit but before dispatch.
- Provider accepted request then process dies before result persistence.
- Restart/replay from every nonterminal state.
- IN_DOUBT reconciliation with and without provider idempotency/status API.
- Forged execution receipt, altered log, missing artifact and hash-only false acceptance.
- Stale/conflicting memory and provenance mismatch.
- Timeout, cancellation, rate limit, storage exhaustion and network loss.
- Rollback after code migration and after partial side effect.
- Android process kill/reboot/restart on exact target device.
- Frozen oracle routing/answer quality with negative controls.

AI-generated tests may supplement but may not replace the frozen acceptance oracle without an independently reviewed change to the oracle.

## 7. Change traceability: R2 review → R3 plan

| Change ID | R2 weakness / external evidence | R3 decision | Acceptance gate |
|---|---|---|---|
| CH-R3-01 | EXT-04: agent complexity trades off against predictability | Workflow-first; model emits plan proposal, deterministic validator accepts/rejects | P0-B fixed oracle and malformed-plan tests |
| CH-R3-02 | EXT-05/06: retries replay side effects; no global exactly-once guarantee | Explicit idempotency, IN_DOUBT and reconciliation; no blind retry | P0-A crash/replay matrix |
| CH-R3-03 | EXT-07/08/09: database atomicity has specific scope and runtime assumptions | Keep one canonical StateStore; verify actual transaction mode and device filesystem | P0-A transaction and restart evidence |
| CH-R3-04 | EXT-02/03: prompt injection/excessive agency | Enforce principal/resource/action outside model; least-privilege adapters | P0-B/P1-A adversarial tests |
| CH-R3-05 | EXT-10: provenance supports traceability but does not itself prove truth | Independent verifier and false-accept tests | P0-C |
| CH-R3-06 | EXT-01/11: lifecycle risk management and secure SDLC | Add frozen test oracle, source/version record, security review and release gates | P1-B/P2 |
| CH-R3-07 | EXT-12: Android background limits and OEM variability | Add exact-device process lifecycle and recovery matrix | P1-B |
| CH-R3-08 | EXT-04: prefer simple composable design | Keep responsibilities logical; split only on measured benefit | P2 measured decision record |
| CH-R3-09 | No actual human review artifact existed | Explicitly mark human independent review as NOT OBTAINED; do not relabel literature synthesis | Human review gate if required |
| CH-R3-10 | Hash integrity can be overclaimed | Separate byte integrity, provenance, semantic verification and reviewer independence | P0-C forged-evidence suite |

## 8. Readiness and honest status

- DESIGN: R3 architecture and acceptance plan documented.
- EXTERNAL EVIDENCE: published sources registered with URL and access date in the R2 review matrix.
- STT SYNTHESIS: recommendations and trade-offs recorded; they are not attributed to external authors as HG2-specific opinions.
- INDEPENDENT HUMAN REVIEW: NOT OBTAINED.
- IMPLEMENTED: only source behavior evidenced by the specific commit and files; this plan itself is documentation.
- TESTED / VERIFIED / OPERATIONAL: must be assigned per capability from actual evidence, never inherited from this plan.
- Release status remains OPEN / DRAFT until the mandatory gates have evidence and authorized acceptance.
