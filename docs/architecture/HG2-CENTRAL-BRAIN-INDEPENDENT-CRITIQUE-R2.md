# HG2 Central Brain — Independent Critique R2

Date: 2026-10-19
Scope: OAI-GIANG/HG2; local candidate 67afde1ca027b4012ce0dde190dda00918da3aff; static/source review plus a 240-test pre-change baseline.
Status: findings are engineering judgements grounded in repository evidence. External sources establish principles, not the status of local code.

## Overall decision

The central-orchestrator direction is defensible: a single logical planner/router reduces cyclic coordination and makes it easier to inspect who dispatched what. Capability allowlists, typed results, stable ordering, explicit PARTIAL/IN_DOUBT outcomes and test-injected adapters are good foundations. The design is not yet a complete central brain: it routes caller-specified capability IDs, synchronously invokes injected functions and aggregates results in memory. It does not persist a plan or independently classify arbitrary user intent, and only two adapters are bound in the API path.

Recommendation: accept the design direction; reject any claim that all five domains, durable orchestration or production autonomy are already achieved.

## Review from distinct specialist perspectives

### 1. Distributed systems and workflow reliability

Strengths:
- Fixed dispatch order and fail-closed capability gaps are simple to reason about.
- Worker exceptions are treated as IN_DOUBT rather than retried blindly.
- Existing HG2 workflow and transaction primitives offer useful building blocks.

Critical challenge:
- BrainOrchestrator has no durable task/step record and cannot resume an interrupted plan.
- Deadline checks happen between synchronous calls; they cannot forcibly cancel an adapter that ignores its own timeout.
- The model API route generates a new UUID per HTTP request and has no client-stable task idempotency key. Replayed requests can duplicate provider calls and costs.
- DurableTransactionStore uses its own SQLite file path and is not bound to the same canonical StateStore used by the API. Adding it naively could create a second source of truth.
- Parallel branches would create partial-commit/race states; do not add concurrency until step dependencies, side-effect isolation, compensation and join rules are specified.

Alternative:
- Reuse the existing phone-owned StateStore and workflow event authority; design a versioned plan/step projection or transactionally append the plan/checkpoint there. Do not instantiate a separate authoritative DB. Reconcile uncertain external effects before retry. Keep execution sequential for the first durable slice.

Severity: HIGH; blocks release, not the pure in-memory core.

### 2. Security and adversarial ML

Strengths:
- Capability IDs are allowlisted; unknown capabilities and attempts to claim unowned capabilities are rejected.
- The API authenticates the caller; memory access passes explicit grants.
- Model output is RESPONSE_ONLY and is not treated as proof of tool execution.

Critical challenge:
- The current API route hard-codes the required capability pair; it does not classify task intent or dynamically plan a dependency DAG.
- A static registry is not the same as a trusted runtime registry. A declaration is useful only with a trusted binding, current health and policy check.
- Prompt injection from memory, files or external sources must remain data, never policy or tool authorization.
- The central brain must not manufacture approvals, credential scopes or capabilities. The policy gate must decide permissions independently of model output.
- The execution layer is not yet an operational, sandboxed tool plane; do not route arbitrary shell or repository mutations through a general-purpose model response.

Alternative:
- Treat model classification as an untrusted proposal. Apply schema validation, deterministic capability allowlisting, principal/resource/action policy checks and independent approval for destructive/high-risk operations. Use least-privilege adapters with per-call timeout and resource budgets. Test direct and indirect prompt injection and permission escalation.

Severity: HIGH before tools/write capabilities go operational.

### 3. Evidence integrity and verification

Strengths:
- Result contracts bind request ID, correlation ID and source revision.
- SUCCESS requires evidence references plus a callable verifier.
- The API intentionally emits RESPONSE_ONLY for model text, preserving PARTIAL.

Critical challenge:
- In the current route, the evidence verifier checks a digest against an in-process dictionary built from the memory context. This can show consistency of that request-local manifest; it does not independently prove provenance of an external source or the truth of generated prose.
- Unit tests use synthetic adapters and a test verifier that returns true. They prove core contract handling, not external capability truth.
- A 40/64-hex source revision check is syntactic. Runtime source-manifest SHA-256 and Git commit SHA have different meanings and must remain separately named in evidence.
- The executor can report a success-like payload; verification must remain outside the same trust boundary for consequential actions.

Alternative:
- Use typed EvidenceRef with artifact digest, source identity, source version, verifier method and confidence. Verify using an implementation not supplied by the worker being checked. Record exact boundary: byte integrity, source provenance, semantic correctness, runtime observation are separate claims.

Severity: HIGH for any claim of VERIFIED/OPERATIONAL.

### 4. Audit, privacy and observability

Strengths:
- The API logs redacted digests rather than the raw user query or provider response.
- The existing state-store event log is append-only and hash-linked.
- The plan and branch outcomes have correlation identity.

Critical finding F-01:
- contract/STATE_V1.md requires an audit record before every provider call and fail-closed behavior if the audit write fails.
- Before remediation, hg/server.py emitted model.call.completed only after ModelGateway.ask returned; no model.call.started event was written before external invocation.
- A process crash or audit failure could therefore make a provider call lack an append-only start receipt.

Root cause:
- Runtime integration added orchestration and completion audit, but did not carry the pre-call audit invariant into the synthesis adapter.

Remediation:
- Emit a redacted model.call.started event immediately before invoking the gateway; if the append fails, return BLOCKED and do not call the provider.
- Validate both success ordering and injected start-audit failure with a fake gateway that counts invocations.
- Keep the query itself, response, authorization token and complete provider request out of the audit event.

Status: implemented in the candidate change; confirmation depends on focused and full-suite results captured in the evidence record.

Further issue:
- Correlation ID exists, but cross-process trace/span propagation and service-level latency/resource metrics are not yet evidenced. If later propagated to untrusted endpoints, inbound trace context must be validated and sensitive baggage omitted.

Severity: F-01 was HIGH due direct violation of an existing state contract; further observability work is MEDIUM/HIGH.

### 5. Software architecture and maintainability

Strengths:
- The nine responsibilities can remain logical boundaries; one process with explicit interfaces is appropriate on a constrained phone.
- Reusing current contracts and state primitives avoids needless duplication.

Critical challenge:
- “Branch” in the code names a logical capability domain, but also means Git branch in the repository. This vocabulary could mislead maintainers.
- Static BRANCH_CAPABILITIES, API-local inventory and separately persisted workflow/transaction primitives can diverge unless one contract governs all of them.
- Replacing a runtime component based on filename or apparent similarity would risk breaking the phone state-owner contract and authenticated sync path.

Alternative:
- Preserve schema V1 compatibility, use “domain” in the documentation now, and introduce a domain_id field only through a versioned contract change with migration and compatibility tests. Keep a single source of capability ownership. Map each contract to exactly one module and test set.

Severity: MEDIUM now; HIGH if several registries are added independently.

### 6. Test engineering and acceptance

Strengths:
- Existing tests cover missing capabilities, invalid constraints, evidence rejection, request mismatch, conflict policy, time budget and uncertain worker outcomes.
- The current API integration uses real local HTTP and StateStore with a deterministic fake gateway.

Critical challenge:
- Synthetic success tests are not production acceptance.
- The suite does not make an arbitrary synchronous handler cancellable.
- The current route has no durable restart/replay proof for Brain plans, no operational adapters for three domains and no deployed-phone/live-provider evidence.
- A self-generated evaluator/oracle must not silently replace the frozen test oracle.

Alternative:
- Use a frozen test corpus and explicit expected labels/results; add property-style malformed input cases, direct/indirect prompt injection, start-audit failure, duplicate delivery, crash after side effect, restart replay, verifier false-accept, resource ceilings and restore from checkpoint. Treat zero unauthorized actions as a required result on the stated test corpus only, not a universal guarantee.

Severity: HIGH for release readiness.

### 7. Product and operations

Strengths:
- The phone remains the intended state authority; offline-first and standard-library-first choices match the target operating environment.
- The API correctly labels model output as a response, not a completed external action.

Critical challenge:
- “Central brain intelligence” can be overstated by naming a deterministic dispatcher a planner. Current operation selects capabilities already present in the request; it is not yet an evaluated natural-language intent classifier.
- A successful provider call says nothing by itself about answer correctness, Vietnamese quality, user satisfaction or production availability.
- Per-request rate/resource limits need to include model costs and cumulative retries, not only HTTP request size.

Alternative:
- Report separate dimensions: orchestration correctness, classification quality, evidence integrity, user outcome, resource cost and operational availability. Begin with an explicitly scoped MVP rather than enabling arbitrary actions.

Severity: MEDIUM/HIGH.

## Finding register

| ID | Severity | Finding | Root cause | Required action | Current disposition |
|---|---|---|---|---|---|
| F-01 | HIGH | No pre-call provider audit in /api/ask | Completion logging was added without enforcing contract/STATE_V1 start-before-call invariant | Add model.call.started; fail closed if write fails; test ordering and injected audit failure | Remediated in candidate; test result is authoritative |
| F-02 | HIGH | Brain plan/step outcomes not durably persisted or replayed | Orchestrator is in-memory, synchronous | Design transactionally persisted plan/step lifecycle on canonical StateStore | OPEN; release blocker |
| F-03 | HIGH | No trusted runtime capability registry and three domains are unbound | Allowlist and API inventory are code-local | Add registry contract, binding proof, health gate and policy scope mapping | OPEN; release blocker for five-domain claim |
| F-04 | HIGH | Evidence verifier is local and not independently trusted for external/semantic claims | Request-local manifest validation is used as proof of memory artifact integrity | Separate byte-integrity/provenance/semantic/runtime verification | OPEN |
| F-05 | HIGH | Runtime production path not verified | Evidence is local test with fake model gateway | Test live provider and exact intended phone deployment without leaking credentials | BLOCKED / NOT RUN |
| F-06 | HIGH | State split risk if DurableTransactionStore is added beside StateStore | Separate database abstraction exists but is not bound to runtime canonical state owner | Decide one canonical transaction boundary; never dual-write independent stores | INVESTIGATE |
| F-07 | MEDIUM | Arbitrary synchronous worker can exceed deadline | Deadline checks are performed before dispatch only | Require adapter-level timeout; test non-cooperative adapter; do not claim hard cancellation | OPEN |
| F-08 | MEDIUM | Client retry may repeat model calls and incur costs | Request UUID is generated per server request; no stable client operation key | Add idempotency key bound to normalized request digest where API semantics allow | OPEN |
| F-09 | MEDIUM | “branch” overloaded between Git and logical domain | Historical naming | Keep V1 compatible; use domain terminology in design and version future schema deliberately | OPEN |
| F-10 | HIGH | Model-output quality and intent routing are unmeasured | Static capability routing is not natural-language classification evaluation | Freeze oracle corpus and measure separate metrics before thresholds | OPEN |

## Rejected or deferred alternatives

- Five peer agents with independent authority: rejected; creates ambiguous command hierarchy and duplicated permissions.
- LLM directly selecting arbitrary shell/tool functions: rejected; excessive agency and untestable authority boundary.
- Parallel execution by default: deferred until dependency DAG, side-effect isolation, idempotency and join/compensation semantics are tested.
- Two authoritative databases, one for history and another for brain tasks: rejected unless a documented single transactional boundary proves there is no conflicting state authority.
- Auto-delete or self-upgrade based on a scalar quality score: rejected.
- Claiming “production verified” from unit tests or a fake gateway: rejected.

## Acceptance verdict

The design direction is suitable to proceed to contract hardening and a durable single-workflow increment. The candidate is not release-ready. F-02 through F-06 must remain visible, and the PR must remain Draft until the required independent verification and exact-runtime evidence exist.
