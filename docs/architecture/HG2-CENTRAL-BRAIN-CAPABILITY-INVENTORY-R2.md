# HG2 Central Brain — Capability Inventory R2

- Repository: OAI-GIANG/HG2 only.
- Evidence scope: source files and local tests inspected on 2026-10-19; all statuses are bounded to that evidence.
- Purpose: distinguish declared capability ownership from an adapter actually bound to the API and from independently verified operation.

## 1. Domain inventory

| Domain ID | Declared capabilities in static map | Concrete adapter observed in /api/ask | Contract/authority source | Status | Required evidence to promote |
|---|---|---|---|---|---|
| memory_knowledge | memory.search, memory.recall, provenance.inspect | memory.search builds scoped context with authenticated grants; the verifier now re-reads authorized records and recomputes query selection/context against the canonical journal | server.py, memory.py, StateStore, Brain request/result contracts | LIMITED IMPLEMENTATION; TESTED on local HTTP path; context integrity verifier tested | Context source/integrity/ACL/selection is checked; semantic truth of model-generated claims, freshness policy, exact deployed runtime and independent human acceptance remain OPEN |
| research_synthesis | research.analyze, synthesis.propose, source.compare | synthesis.propose calls ModelGateway after a durable redacted start receipt; request, plan, attempt, step and terminal receipts are recorded under the existing StateStore | server.py, model_gateway.py, contracts.py, history.py, phone_runtime.py | RESPONSE_ONLY; TESTED with fake gateway, same-key conflict/concurrency and restart-to-IN_DOUBT tests | Live-provider boundary proof, answer-claim verifier, hard wall-clock deadline/cancellation, provider-level reconciliation and cost budget |
| planning_coordination | task.decompose, dependency.plan | No adapter bound in /api/ask | brain_orchestrator.py; workflow.py exists but is not wired to Brain steps | DECLARED; UNBOUND | Validated acyclic plan, persisted steps, routing oracle and restart recovery |
| tools_execution | tool.execute, artifact.build | No adapter bound in /api/ask | capability allowlist and policy primitives exist; no operational execution adapter proven | DECLARED; UNBOUND | A narrow least-privilege adapter, approval/policy binding, receipt, idempotency and adversarial test |
| security_verification | policy.check, evidence.verify, conflict.review | Read-only memory-context verifier checks journal integrity, source-head binding, access scope, record checksums, canonical manifest, retrieval selection and reconstructed context bytes; no general verifier adapter is bound | contracts.py, server.py, policy.py, authority.py, provenance.py, history.py, memory.py | PARTIAL implementation on this API path; NOT a fully bound domain | Independent artifact/provenance verifier, semantic answer verification, false-accept/false-reject corpus and verifier provenance remain OPEN |

“DECLARED” means an ID exists in a static allowlist; it does not mean available, authorized, healthy, tested end-to-end or operational. “Bound” means an actual implementation is passed into the runtime dispatcher for the stated path; it does not automatically mean the whole domain is implemented.

## 2. Evidence levels per capability

| Level | Meaning | Minimum evidence |
|---|---|---|
| PROPOSED | Contract/design only | Versioned spec and risk analysis |
| IMPLEMENTED | Adapter or logic exists in source | Source path, revision and explicit invocation boundary |
| TESTED | Relevant tests were run | Command, result count, exit code, environment and log digest |
| VERIFIED | Defined acceptance predicate independently checked | Independent verifier, source/result binding, positive and negative tests |
| OPERATIONAL | Observed on named target runtime | Runtime identity, health, actual execution receipt, logs, resource metrics and post-run state integrity |
| BLOCKED | Must not be invoked now | Stable blocker code and reason |
| UNKNOWN | Evidence insufficient | Explicit unknown and next evidence needed |

Promotion is capability-specific. Passing an orchestrator unit test cannot promote three unbound domains to IMPLEMENTED. A response from a fake gateway cannot promote a live provider to OPERATIONAL.

## 3. Contract matrix

| Contract | Required fields/invariants | Main tests |
|---|---|---|
| BrainRequest V1 | schema version, request/correlation identity, goal, constraints, source revision | malformed input, unsafe constraints, revision mismatch |
| CapabilityResult V1 | request/correlation/source binding, status, output digest, evidence refs and error code | missing/mismatched result, false evidence, worker exception |
| Plan V2 proposal | stable plan/step IDs, acyclic dependencies, capability/domain owner, scopes, idempotency, deadlines, budgets, evidence requirements | cycle, unknown node, scope expansion, duplicate step, over-budget |
| ExecutionReceipt V1 proposal | task/step/plan identity, adapter revision, outcome certainty, digest, external receipt and evidence refs | forged success, timeout, missing receipt, duplicated operation |
| EvidenceRef V1 proposal | artifact digest, source identity/version, verifier/method, trust domain, freshness and claim type | unavailable bytes, tampered bytes, stale provenance, semantic false accept |
| RegistryEntry V1 proposal | one owner, adapter binding, contract versions, permissions, side-effect class, limits, health, verification state | duplicate owner, unbound/disabled adapter, stale health |
| WorkflowState V2 proposal | task/step status, version, retry count, stable idempotency, checkpoint, result/evidence digest | CAS conflict, crash/restart, retry bound, IN_DOUBT reconcile |

Rows labelled proposal are not implemented runtime contracts. V1 remains unchanged until a new schema, compatibility tests and migration are separately reviewed.

## 4. Authority constraints

- The static capability map limits what each domain may claim; it does not grant user or system permissions.
- Caller identity and memory scope are checked outside model-generated content.
- Tool/write permission must be evaluated independently for exact principal, resource, action, risk tier and plan digest.
- No model/worker may manufacture an approval, credential, owner or permission scope.
- Registry health, adapter binding and contract-version compatibility are prerequisites for dispatch.
- Missing or stale mandatory capability means BLOCKED before side effects.
- Independent verification must not be implemented solely as the same worker returning “success”.
- Response generation remains RESPONSE_ONLY unless an explicit acceptance contract and independent verifier support a stronger claim.

## 5. Candidate registry implementation and remaining increment

hg.capability_registry.RuntimeCapabilityRegistry now implements a versioned, fail-closed request-scoped projection over the static ownership allowlist. It binds one concrete adapter per domain in V1, records adapter/version/contracts/authority/side-effect/timeout/limit/lifecycle/source/evidence-verifier metadata, rejects duplicate or cross-owner bindings, performs readiness checks, enforces a per-request invocation budget, and emits a canonical registry digest. BrainOrchestrator receives only the capabilities projected by that registry; an unbound domain is unavailable rather than assumed to exist.

The current /api/ask candidate binds two adapters only:
- memory_knowledge.memory.search: local read-only context construction; lifecycle TESTED for the local fake/tested HTTP path.
- research_synthesis.synthesis.propose: configured ModelGateway response path; lifecycle TESTED only in the sense of the locally exercised adapter contract, not a live provider or deployed service.

The other three domains remain unbound: planning_coordination, tools_execution, and security_verification. Registry metadata explicitly records that hard wall-clock cancellation is not enforced for either current adapter. A readiness check and a declared timeout are not proof of timeout enforcement or operational health.

Next implementation increment:
1. Complete one-store crash-safe recovery for StateStore journal and projection/head files; preserve fail-closed behavior until the recovery oracle passes.
2. Define and freeze a fixed plan/routing/evidence acceptance corpus, including false accept and false reject cases.
3. Bind a general evidence verifier that independently validates provenance and semantic claims; keep memory-context byte/integrity verification distinct from answer truth.
4. Implement the other three domain adapters only after authority, side effects, approval and recovery contracts are explicit.
5. Add enforceable wall-clock deadlines/cancellation, then verify behavior on the exact phone runtime and deployed service.
6. Obtain real independent human review and release acceptance before any merge/deployment.


## 6. Candidate implementation update — 2026-10-19

The following code paths are implemented and tested in the current candidate, subject to the evidence log and its stated limits:

- HTTP /api/ask requires a stable client Idempotency-Key. The stored request fingerprint is bound to configured principal, normalized query/schema and source-manifest revision. Same key with different input/source is a conflict.
- brain.request.accepted, planned, started, attempt.started, step started/completed, model-call started/completed, terminal and recovery markers are written to the existing PhoneRuntime StateStore. There is no second workflow database.
- Concurrent duplicate requests are denied before a second provider call. Same-process duplicate delivery returns a bounded in-memory cached response. After restart, the system does not call the provider again when completion was already recorded, but it may return IDEMPOTENCY_OUTCOME_FINAL_RESPONSE_NOT_CACHED because the raw answer is deliberately not persisted.
- A model.call.started record without a matching terminal event is marked IN_DOUBT during PhoneRuntime startup. No automatic provider replay is performed.
- The production HTTP entrypoint acquires a Unix flock on the state directory before constructing PhoneRuntime, creates a fresh state directory securely when needed, and refuses a second HTTP server for the same state path. Code that writes through a direct, separately constructed PhoneRuntime must still obey the single-writer rule; the lock is not a general transaction layer for arbitrary writers.
- StateStore is still a file-backed journal plus separate projections/checkpoint. A process failure between these writes can cause startup to fail closed. This implementation does not provide atomic journal + projection recovery.
- The local answer status is still RESPONSE_ONLY/PARTIAL. Memory-context integrity verification is not semantic truth verification. Live-provider/deployed service/device tests and independent human review were not obtained in this closure pass.


## 7. Candidate closure evidence — 2026-10-19

- Candidate full suite: 258 tests passed in 25.952 seconds on Termux Android 15 ARM64, Python 3.14.6, with ResourceWarning promoted to an error. See evidence/HG2-CENTRAL-BRAIN-CLOSURE-20261019/logs/full-regression.log and the closure report for its digest.
- The versioned registry is implemented and locally tested, but it is not a full five-domain registry deployment. Only two domains have adapters in /api/ask; the three remaining domains are deliberately unavailable.
- hard_timeout_enforced=false for current bindings is explicit; configured time values are declarations, not an enforced cancellation guarantee.
- No live provider, deployed service, independent human reviewer, or production-release acceptance was obtained in this pass.
