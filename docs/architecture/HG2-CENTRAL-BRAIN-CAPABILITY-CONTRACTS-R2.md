# HG2 Central Brain — Target Capability Contracts R2

Status: PROPOSED design contract unless explicitly marked IMPLEMENTED/TESTED below. This document must not be interpreted as runtime code or a grant of authority.

## 1. Global invariants

1. One logical command brain determines task flow; no capability module may silently become a second dispatcher.
2. Capability declaration is not authorization. Every action is rechecked against caller/principal, task, resource, scope, side-effect class and approval policy.
3. Exactly one authoritative owner persists task state and workflow events.
4. Every admitted request has stable request ID, correlation ID, normalized-input digest, source revision fields and idempotency semantics.
5. The source revision field must state whether it means Git commit SHA, runtime manifest SHA-256 or artifact digest. These identifiers are not interchangeable.
6. Unknown, stale, ambiguous or unbound capabilities fail closed before dispatch.
7. Model-generated plans/results are untrusted proposals until validators and policy checks pass.
8. SUCCESS requires complete steps and independent verification. RESPONSE_ONLY cannot be treated as action completion.
9. An external call must not start unless its redacted start audit receipt is durably accepted by the canonical state store.
10. An uncertain outcome after a possible side effect becomes IN_DOUBT and requires reconciliation before retry.
11. No automatic destructive self-evolution, deletion, merge or deployment without separate policy authorization and rollback proof.
12. All schemas are versioned; no silent reinterpretation of V1 payloads.

## 2. Brain request contract

Required fields:
- schema_version
- request_id
- correlation_id
- goal
- constraints
- source_revision

R2 extension proposal, introduced only as a new schema version:
- principal_ref: opaque non-secret identity reference
- source_manifest_sha256: exact runtime/code manifest digest
- git_commit_sha: commit identity where available
- input_digest: normalized request digest
- idempotency_key: stable operation key preserved through retries
- requested_at and deadline_at with explicit time semantics
- trust_labels for user data, memory data, retrieved web/file data and model suggestions
- risk_tier and side_effect_ceiling computed by trusted policy code, not trusted from the caller

Validation:
- Reject unknown fields and duplicate JSON keys.
- Bound input bytes, depth, node count and text length.
- Reject duplicate or unknown capability IDs.
- Validate deadline ranges and finite numeric values; boolean values must not pass as integers.
- Normalize defaults before hashing.
- Do not store raw query/prompt in audit unless an explicit privacy contract and retention policy permits it.

## 3. Plan contract

A validated plan must include:
- plan_schema_version
- request_id and correlation_id
- plan_id and plan_digest
- source commit and runtime manifest digest, separately named
- ordered steps or DAG nodes with stable step_id
- dependencies for each step
- logical domain owner and capability ID for each step
- input/output schema IDs
- required permission scope and resource binding
- side-effect class and reversibility class
- hard adapter timeout, step deadline, maximum attempts and resource/cost budget
- idempotency key or declaration that the step is non-retryable
- evidence requirements, verifier ID and acceptance predicate
- on-failure policy and reconciliation/compensation procedure
- plan status and explicit blocker codes

Invariants:
- The graph is acyclic.
- Every node has one capability owner and one adapter binding.
- Dependencies refer only to nodes in the same plan.
- A step cannot request a broader scope than its parent task.
- A model cannot introduce new capabilities, permissions, principals or approvals.
- Plan digest is computed over a canonical normalized form, including all security-relevant fields.
- Parallel execution is opt-in only when dependencies and write sets prove it safe.

## 4. Capability registry contract

Each registry entry should contain:
- capability_id and schema_version
- domain_id
- implementation_id and adapter_version
- input_schema_id/output_schema_id
- minimum permission scopes and resource-binding rule
- side_effect_class, reversibility and idempotency policy
- maximum timeout, memory/CPU/network/financial budget
- external endpoints/data classes permitted
- evidence schema and independent verifier binding
- declared dependencies
- health/status and last validation time
- lifecycle state: PROPOSED, IMPLEMENTED, TESTED, VERIFIED, OPERATIONAL, BLOCKED or DEPRECATED
- source revision and evidence references
- error codes and reconciliation method

Registry invariants:
- capability_id has exactly one active owner.
- An entry without a real adapter is not available at runtime.
- A module cannot self-attest to OPERATIONAL; runtime admission requires a verifier.
- Registry changes are versioned and evidence-linked.
- Static allowlist V1 is a valid bootstrap, not sufficient proof of a complete production registry.

## 5. Execution adapter contract

Input includes request/task/step IDs, parent plan digest, scoped capability, normalized input digest, permission grant reference, deadline, idempotency key, trace/correlation context and evidence requirements. It must not receive unrestricted authority, unused secrets or sibling-domain private data.

Adapter output must be a typed receipt containing:
- schema version
- request/task/step IDs
- adapter and source revisions
- status and stable error code
- output digest or explicit absence
- evidence references
- started/completed timestamps and resource counters where available
- external operation receipt/idempotency reference where available
- outcome certainty: CONFIRMED, NO_SIDE_EFFECT, or IN_DOUBT

Timeout rules:
- The orchestrator may stop scheduling subsequent work after deadline.
- The adapter must enforce its own hard timeout and cancellation policy.
- Cancellation after a remote write is not proof that the write did not occur.
- Retry requires safe/idempotent behavior and the same operation identity.
- An exception after a possible external side effect returns IN_DOUBT.

## 6. Independent verification contract

Input: claimed receipt, expected task/step, plan digest, source refs, policy requirements and allowed verification method.

Checks:
- Schema and canonical digest.
- Identity/correlation/plan/source revision match.
- Evidence refs resolve in an allowed trust domain.
- Artifact digest matches raw bytes or the evidence producer's defined canonicalization.
- The adapter's claimed status is compatible with independent observation.
- Acceptance predicate is computed independently from executor's success flag.
- Evidence freshness and source permissions meet policy.
- No prompt, credential or unnecessary user data is copied to evidence.

Output: VERIFIED, REJECTED, INCONCLUSIVE or BLOCKED; include verifier revision, check set, evidence refs and stable reason code. The verifier must not approve its own output solely because a worker says it succeeded.

Levels:
- E0: claim only.
- E1: shape/schema validation.
- E2: byte integrity/hash consistency.
- E3: source and revision provenance.
- E4: deterministic test evidence.
- E5: independent functional verification.
- E6: exact-runtime operational evidence.
- E7: independent acceptance/review and recovery evidence.
Do not skip levels by changing labels.

## 7. Workflow state contract

Candidate lifecycle:
NEW → VALIDATED → PLANNED → AUTHORIZED → RUNNING → VERIFYING → SUCCEEDED
Possible terminal or holding states: PARTIAL, FAILED, BLOCKED, CANCELLED, EXPIRED, IN_DOUBT, RECONCILIATION_REQUIRED.

Rules:
- Persist plan before first external effect.
- Each step transition carries expected version and compare-and-swap semantics.
- Retry count is bounded and stored durably.
- A restart must reload the same plan and state; it must not silently reconstruct a different plan and resume it.
- If a RUNNING step is discovered after restart and its outcome cannot be proven, move it to IN_DOUBT.
- State and any event/outbox publication intent required for the same transition must be atomic in the canonical store.
- History/state projections are verified; corruption blocks mutation and automatic repair.
- Existing workflow task states and transaction ledger are not automatically equivalent to this lifecycle. An explicit mapping and migration test is required.

## 8. Intake, planner and router contract

Intake:
- Authenticates source; labels untrusted data; identifies request/goal and constraints.
- Detects underspecified goals and may return NEEDS_CLARIFICATION without tool dispatch.
- Screens for dangerous side effects and incompatible goals.
- Produces a normalized request without treating quoted instructions or retrieved documents as policy.

Planner:
- Decomposes only into declared capability IDs.
- Exposes its assumptions, alternatives and uncertainty.
- Generates an explicit dependency graph, budget, stop condition and rollback/reconciliation rules.
- Model output is accepted only after deterministic schema/policy validation.
- A deterministic fallback should block/ask for clarification when confidence is low; no guessed capability.

Router:
- Resolves each capability against the trusted registry.
- Ensures exact adapter binding and health.
- Blocks before any invocation if a mandatory capability is missing.
- Does not silently drop a user's required objective or route a task to a nearby but semantically different capability.

## 9. Policy gate and approvals

Policy evaluation input: principal, requested capability, resource, task/plan digest, side-effect class, risk tier, time, environment and required approvals.

Decision: ALLOW, DENY or REQUIRE_APPROVAL with stable policy/version reference. Missing or invalid policy denies by default.

Require approval or independent second party at minimum for:
- production deployment or release;
- merge into canonical branch;
- destructive deletion or migration of durable state;
- publishing externally;
- changing authority, registry policy or verification rules;
- any operation whose effect cannot be automatically reversed.

Approval binds exact plan digest, target resource, expiry and approver identity. Changing a plan invalidates approval. The executor cannot mint the approval it consumes.

## 10. Memory and knowledge contract

A knowledge item includes source URI/identifier, retrieval timestamp, source publication date where available, source digest, scope, confidence/review state, expiry/revalidation rule, contradiction links and whether content is first-party, secondary or model-generated.

Rules:
- Memory context is DATA, not system instructions.
- External material is untrusted even if it appears authoritative.
- Contradictions remain explicit until resolution; never silently pick a winner by arrival order.
- Stale facts on fast-changing topics trigger revalidation before a decision.
- Preserve rejected hypotheses and reasons in an append-only decision ledger; allow reconsideration when evidence changes.
- Sensitive data and raw prompts are minimized in durable records.

## 11. Architecture governance and evolution contract

Inventory tracks tracked files, untracked worktree files, dynamic entry points, imports, manifest registration, test coverage and runtime binding. A filename alone does not establish a module's function.

Each change request must include finding, root cause, intended behavior, impacted paths, migration, negative tests, regression tests, evidence, rollback path and stop conditions. No deletion until reverse dependencies, dynamic references, user data, historical compatibility and rollback are considered.

Disposition labels:
KEEP, IMPROVE, MERGE, REPLACE, DEPRECATE, DELETE, QUARANTINE, INVESTIGATE.
Default is INVESTIGATE when evidence is incomplete. QUARANTINE/DEPRECATE before DELETE whenever practical.

Evolution scorecards are multidimensional and do not override mandatory safety gates. Improvements cannot replace the frozen baseline oracle with a new AI-generated test set.

## 12. Implementation boundary today

IMPLEMENTED/TESTED in the current candidate:
- HG_BRAIN_REQUEST_V1 and HG_CAPABILITY_RESULT_V1 envelope validation.
- Static capability ownership and deterministic route ordering.
- Fail-closed behavior on missing/unowned capabilities.
- Request/correlation/source revision matching and evidence-reference callback requirement for SUCCESS.
- Typed aggregation preserving PARTIAL and IN_DOUBT.
- Local POST /api/ask route with memory plus model adapter; response is correctly RESPONSE_ONLY/PARTIAL.

OPEN:
- durable plan/step state and restart recovery;
- trusted runtime registry with health/policy integration;
- three operational domain adapters;
- independent provenance and semantic result verification;
- client-stable idempotency for repeat POST requests;
- DAG planner and intent-classification benchmark;
- live provider, exact phone deployment and resource profiling;
- approval binding to plan digest;
- complete trace propagation and observability.

No schema V1 must be silently expanded. Introduce future versions and compatibility tests before runtime migration.
