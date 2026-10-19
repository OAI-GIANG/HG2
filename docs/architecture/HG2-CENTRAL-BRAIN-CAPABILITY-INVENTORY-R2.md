# HG2 Central Brain — Capability Inventory R2

- Repository: OAI-GIANG/HG2 only.
- Evidence scope: source files and local tests inspected on 2026-10-19; all statuses are bounded to that evidence.
- Purpose: distinguish declared capability ownership from an adapter actually bound to the API and from independently verified operation.

## 1. Domain inventory

| Domain ID | Declared capabilities in static map | Concrete adapter observed in /api/ask | Contract/authority source | Status | Required evidence to promote |
|---|---|---|---|---|---|
| memory_knowledge | memory.search, memory.recall, provenance.inspect | memory.search path builds scoped memory context using authenticated grants and MemoryStore | server.py, memory.py, StateStore, Brain request/result contracts | LIMITED IMPLEMENTATION; TESTED on local HTTP path | Cross-scope denial, provenance/freshness checks, restart/recovery test, exact runtime proof |
| research_synthesis | research.analyze, synthesis.propose, source.compare | synthesis.propose calls ModelGateway after pre-call audit receipt | server.py, model_gateway.py, contracts.py | RESPONSE_ONLY; TESTED with fake gateway | Live-provider boundary proof, source/citation/semantic verifier, timeout/cost budget |
| planning_coordination | task.decompose, dependency.plan | No adapter bound in /api/ask | brain_orchestrator.py; workflow.py exists but is not wired to Brain steps | DECLARED; UNBOUND | Validated acyclic plan, persisted steps, routing oracle and restart recovery |
| tools_execution | tool.execute, artifact.build | No adapter bound in /api/ask | capability allowlist and policy primitives exist; no operational execution adapter proven | DECLARED; UNBOUND | A narrow least-privilege adapter, approval/policy binding, receipt, idempotency and adversarial test |
| security_verification | policy.check, evidence.verify, conflict.review | A request-local manifest callback exists; no full independent domain adapter | contracts.py, server.py, policy.py, authority.py, provenance.py | DECLARED; verifier is PARTIAL / UNBOUND as a domain | Independent artifact/provenance/semantic verifier, false-accept/false-reject benchmark and verifier provenance |

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

## 5. Required next implementation increment

1. Define the authoritative registry source and its relationship to the static V1 allowlist.
2. Map Brain step states to the existing task/workflow primitives without adding a second task database.
3. Implement one read-only execution adapter and a trusted evidence resolver.
4. Add fixed-oracle routing, malformed-contract and adversarial tests.
5. Prove restart/replay and exact-phone runtime behavior.
6. Only then consider connecting additional domains or external-write capabilities.
