# HG2 Independent Architecture — R2 Candidate

Date: 2026-10-19
Repository: OAI-GIANG/HG2 only
Base: `hg-genesis` at `1dca305b4d6e9442e259442486efb5127cc0cb09`
Candidate branch: `stt/hg2-brain-orchestrator-r1-20261019`
Status: IMPLEMENTED AS A TESTABLE ORCHESTRATION CORE; RUNTIME INTEGRATION AND PRODUCTION CLOSURE BLOCKED

## MTC-1.0 control block

- OBJECTIVE: define and test one central, capability-gated router over five logical HG domains.
- SCOPE: the pure-Python coordinator contract and its unit tests; no remote branch is treated as a running brain.
- INPUT: HG_BRAIN_REQUEST_V1, canonical source revision, explicitly required capability IDs, trusted capability inventory and injected worker adapters.
- OUTPUT: deterministic route plan, typed branch result ledger in-memory, fail-closed aggregate state.
- ACCEPTANCE CRITERIA: all required capabilities mapped or blocked before execution; only allowed capability ownership; request/correlation/source revision binding; evidence verification for SUCCESS; missing/duplicate/foreign results not promoted to SUCCESS; conflict policy explicit; bounded selected branch count and deadline checks.
- EVIDENCE: focused unittest module, complete Termux suite, compile/checksum/git-diff results added to the candidate evidence file.
- RISKS: synchronous injected handlers cannot be forcibly cancelled safely by this module; an adapter exception may occur after an external side effect, so the aggregate is IN_DOUBT. This module is not durable and does not itself create an audit event or persist a task.
- STOP CONDITION: any regression, evidence verification failure, invalid authority/capability inventory, mismatched request provenance, or unresolved production integration blocks promotion.
- NEXT ACTION: connect the orchestrator to one authoritative durable request/worker adapter and add exact-runtime end-to-end evidence before closing P0.

## Findings re-confirmed on canonical base

The existing HTTP `POST /api/ask` path builds authorized memory context and calls the configured model gateway. It records a model-call completion event. The inspected path does not use `validate_brain_request`/`validate_capability_result`, does not dispatch a TaskContract across five logical domains, and does not run the aggregation policy defined by native-intelligence fixtures. Therefore the prior test count did not prove five-domain routing.

Existing building blocks retained, not duplicated:
- `hg/contracts.py`: bounded request/result envelopes and strict evidence-verification requirement for SUCCESS.
- `hg/task_contract.py`: immutable task declaration validation; it explicitly does not authorize or execute.
- `hg/workflow.py`: persisted task state machine with authority, deadlines and idempotency.
- `hg/history.py` / `hg/phone_runtime.py`: phone-owned state path.
- `hg/durable_transactions.py`: durable execution-state ledger and recovery to IN_DOUBT.
- `hg/sync_dispatcher.py`: replication/outbox dispatch, not assumed to be the task scheduler.
- `tests/fixtures/hg-native-intelligence-v2.1/validate_v21.py`: fixture-only verdict rules; not treated as production runtime wiring.

## HG-specific mechanism: Single Authority / Capability Gate / Evidence Return (SACER)

1. The central Brain accepts only a versioned request with stable request ID, correlation ID, goal, explicit constraints and source revision.
2. The request must name one or more registered capabilities. The registry assigns each capability to exactly one logical domain; unknown capabilities are rejected.
3. Capability inventory counts only when that domain has an injected worker adapter. A declaration without an adapter is not operational capacity.
4. If any required capability is missing, the coordinator returns `BLOCKED_CAPABILITY_GAP` without invoking any worker. It does not silently downgrade the objective.
5. Otherwise, the coordinator selects domains in a stable canonical order, passes a scoped child context and enforces top-level branch/step budget. An adapter must enforce its own hard execution timeout and internal step budget.
6. Each worker returns `HG_CAPABILITY_RESULT_V1`; the coordinator validates exact request ID, correlation ID, source revision, status, output digest, and evidence references. SUCCESS is accepted only if the trusted evidence verifier returns true for every reference.
7. A worker/contract/verifier exception is treated as `IN_DOUBT` because side-effect completion may be unknowable. Stop dispatching after the uncertain result; reconcile before retry.
8. Aggregation preserves FAIL, BLOCKED, PARTIAL and INCONCLUSIVE distinctions. `REQUIRE_IDENTICAL_DIGEST` is only for an explicitly shared/same-claim result; independent domains use `INDEPENDENT_OUTPUTS`. No implicit winner is chosen on a detected same-claim digest conflict.
9. This core is dependency-free and synchronous. Durable queue/state persistence, API integration, trusted inventory source, real worker adapters, cross-process tracing and runtime health admission are further gates, not hidden assumptions.

## Five logical domains

| Domain | Initial capabilities (allowlisted) | Runtime status |
|---|---|---|
| memory_knowledge | memory.search, memory.recall, provenance.inspect | Declared logical domain; operational adapter not bound by this change |
| research_synthesis | research.analyze, synthesis.propose, source.compare | Declared logical domain; operational adapter not bound by this change |
| planning_coordination | task.decompose, dependency.plan | Declared logical domain; operational adapter not bound by this change |
| tools_execution | tool.execute, artifact.build | Declared logical domain; operational adapter not bound by this change |
| security_verification | policy.check, evidence.verify, conflict.review | Declared logical domain; operational adapter not bound by this change |

These are logical capability domains, not Git branches and not five independent command authorities.

## External references and application

- Microsoft Azure Architecture Center, [Saga](https://learn.microsoft.com/en-us/azure/architecture/patterns/saga): explicit orchestration is useful for complex multi-step flow; HG adopts one coordinator but keeps phone-state ownership local. Saga compensations apply only where actions are actually compensable.
- Microsoft Azure Architecture Center, [Idempotent Consumer](https://learn.microsoft.com/en-us/azure/architecture/patterns/idempotent-consumer): use stable operation identity for duplicate-safe work; do not use correlation ID alone as idempotency key.
- Microsoft Azure Architecture Center, [Transactional Outbox](https://learn.microsoft.com/en-us/azure/architecture/patterns/transactional-outbox): persist state and publication intent atomically in one store. HG's replication outbox is not automatically the job queue.
- OpenTelemetry, [Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): preserve causal context across process boundaries and treat inbound trace context as untrusted. The core presently carries request/correlation identity; W3C trace/span propagation remains unimplemented.
- NIST, [AI RMF Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/): governance and evidence evaluation should apply through design, test and deployment, not only final score.

## Test boundary

The new tests use synthetic worker adapters and a deterministic test evidence verifier. They prove the coordinator contract only. They do not prove:
- production backend availability for any of the five domains;
- persistence/replay of orchestration plans and results;
- real authorization for external tools;
- live HTTP/API integration or model-driven domain classification;
- end-to-end correctness on a deployed phone runtime;
- human-independent review or signed artifact provenance.

## Release gates

P0-F01 (real API/request-to-router-to-worker-to-result integration): OPEN until exact-runtime E2E test is added.
P0-F02 (real conflict adjudication and terminal no-capability behavior): core semantics TESTED; production integration OPEN.
P1 (durable task ledger and transactional dispatch binding): OPEN.
P1 (trusted capability inventory and evidence root): OPEN.
P1 (causal trace/span propagation): OPEN.
P1 (extended outage/restore and Termux resource thresholds): OPEN.
Independent reviewer: NOT OBTAINED.
Production, merge and deployment: NOT APPROVED by this candidate.

This R2 candidate closes the architecture-design work product, but it does not declare the overall five-domain HG runtime or the P0 integration gate closed.
