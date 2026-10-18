# HG2 Unified Brain Group — G1–G3 Implementation and Verification Record

**Date:** 2026-10-18
**Repository:** `OAI-GIANG/HG2`
**Working branch:** `stt/hg2-circulatory-architecture-20261018`
**Runtime used for verification:** Termux on Android / aarch64; Python 3.14.6
**Production state:** `NOT_RELEASED`

## 1. Baseline, ownership and safety

- Initial checked-out HEAD: `f662b42426b22d2f526c49318adb5cf4089360d5`.
- Initial tree: `1ff6c4c1e204230ebe2c8588343d8c0d658f2b44`.
- The initial working tree had the untracked audit matrix `docs/HG2_UNIFIED_BRAIN_GROUP_AUDIT_MATRIX_20261018.md`. Its initial copy and SHA-256 are preserved under `evidence/HG2-UNIFIED-BRAIN-GROUP-G1-G3-20261018/prechange/`.
- Read-only remote ref check: remote `hg-genesis` was `9d83a113ccdf1aeda656e494593fa55b9078c803`; the remote feature branch initially pointed to `f662b42426b22d2f526c49318adb5cf4089360d5`. The local `hg-genesis` ref was stale (`cdebaeed014371f033f14352f552c6d0d4e69198`) and was not modified.
- PR #25 was observed as OPEN/DRAFT before the branch update. It was not merged.
- No production config/secrets were changed. No services restarted, no live state migrated, and no deploy performed.

## 2. Architecture decision

The single production composition hierarchy is recorded in `manifest.json`:

1. `hg.agent.HGAgent` — sole production composition root and public Brain entry.
2. `hg.toolplane.ToolPlane` — subordinate bounded turn/tool router; not a peer planner or second command owner.
3. `hg.policy` — single policy decision point and issuer/consumer of single-use mutation permits.
4. `hg.phone_runtime.PhoneRuntime` — runtime composition root and selection point for the one canonical state store.
5. `hg.provider` — sole provider boundary.

The architecture tests parse every `hg/*.py` module and verify only `hg.agent` imports and instantiates `ToolPlane`. The lower-level `ToolPlane` and direct tool-dispatch entrypoints also enforce their required Brain/provider scopes; a direct call cannot bypass authorization by skipping `HGAgent`.

## 3. Findings and root causes resolved

### G1 — One command owner

Source inspection found one production `ToolPlane` construction site in `hg/agent.py`. The Brain entry now creates a request ID and correlation ID, records `brain.request.accepted`, passes the same IDs down through `ToolPlane`/provider/tool audit events, then records `brain.request.completed`. The user goal itself is not copied to durable audit events; only its digest is stored. This avoids logging the prompt while preserving a trace binding.

### G2 — One mutation authorization point

Previously, workflow and approval services called `store.emit` directly, and raw store APIs could write domain events without a policy decision. The following controls are now implemented:

- `AuthenticatedPrincipal` is sealed and subject-bound (`principal_id`); no subject ID is inferred from the bearer token.
- `hg.policy.authorize_service_mutation` denies missing principals, missing subject identity, unknown actions and wrong scopes.
- `hg.policy.issue_mutation_permit` issues an exact, single-use in-process permit bound to the action/event type, subject and actor, canonical payload digest, correlation ID, idempotency/event ID, and exact authority context.
- `consume_mutation_permit` rejects absent, forged, replayed, stale or mismatched permits and consumes only the exact registered permit once.
- `StateStore.emit` and `SQLiteStateStore.emit` reject direct public writes without the permit. Genesis is reserved for store initialization.
- Legacy history now writes strict `HG_HISTORY_EVENT_V2` records after genesis, persisting actor, authority context, authorization action and idempotency key under the record hash; original V1 records remain readable and schema-checked.
- SQLite domain events, workflow, approvals, session creation, Brain audit events, sync outbox attempt/acknowledgement, migration import, and backup/restore each pass their scoped authorization gate before the protected mutation.
- `WorkflowService` actor and approval requester/reviewer identities must match their sealed authenticated principals. Self-approval remains forbidden.
- Legacy `StateStore` idempotency now checks matching operation identity; reuse of an event ID or idempotency key for a different operation fails without appending a record.

**Security scope:** these checks protect HG2's public in-process application/store interfaces and the production call graph. Python code already executing with arbitrary access to the same process's private attributes, raw SQLite connection, or OS/filesystem can bypass in-process APIs; HG2 is not an adversarial-code sandbox. Production modules are therefore trusted implementation code, and direct private writes remain prohibited by architecture/review.

### G3 — Versioned contracts and fail-closed result handling

- `HG_BRAIN_REQUEST_V1` validates the exact fields, bounded size, request ID, correlation ID, goal, constraints and source-revision field.
- `HG_CAPABILITY_RESULT_V1` validates the exact fields, supported status, request/correlation/revision binding, output digest, error code and evidence-reference shape.
- A `SUCCESS` result is accepted only when the source revision is an attested 40/64-character commit-like digest and a trusted injected evidence verifier returns literal `True` for every evidence reference. A URI or digest-shaped string alone is not proof.
- Provider text is never upgraded into task-execution success. The current Brain path records the result as `RESPONSE_ONLY`, with digest and explicit error code `PROVIDER_RESPONSE_ONLY_NOT_EXECUTION_PROOF`, empty evidence references and revision `RUNTIME_REVISION_UNATTESTED`. Provider errors are recorded as `FAIL` with an error code. Both are correlated with the accepted request and durably stored.
- Unknown schema versions, unknown fields, missing fields, mismatched IDs, malformed digests, fake evidence locators, success without a verifier, or failure without an error code are rejected.

**Scope of G3:** this verifies the shared request/result contract and its fail-closed behavior. It does not claim a real capability-execution result is available or that a live evidence service exists. That is why the Brain currently records `RESPONSE_ONLY`, not `SUCCESS`.

## 4. Changed files

### Runtime and policy

- `hg/agent.py`
- `hg/auth.py`
- `hg/contracts.py`
- `hg/history.py`
- `hg/migration.py`
- `hg/phone_runtime.py`
- `hg/policy.py`
- `hg/recovery.py`
- `hg/sqlite_state.py`
- `hg/sync.py`
- `hg/toolplane.py`
- `hg/workflow.py`
- `manifest.json`

### Tests

- `tests/_support.py`
- `tests/test_agent.py`
- `tests/test_approval_service.py`
- `tests/test_auth.py`
- `tests/test_brain_contracts.py`
- `tests/test_circulatory_architecture.py`
- `tests/test_core.py`
- `tests/test_migration.py`
- `tests/test_mutation_boundary.py`
- `tests/test_policy.py`
- `tests/test_recovery.py`
- `tests/test_sqlite_state.py`
- `tests/test_sync.py`
- `tests/test_toolplane.py`
- `tests/test_workflow.py`

### Documentation and evidence

- `docs/HG2_UNIFIED_BRAIN_GROUP_AUDIT_MATRIX_20261018.md`
- `docs/HG2_UNIFIED_BRAIN_GROUP_G1_G3_IMPLEMENTATION_20261018.md`
- `evidence/HG2-UNIFIED-BRAIN-GROUP-G1-G3-20261018/prechange/` — checkpoint, original matrix copy and pre-change hashes.
- `evidence/HG2-UNIFIED-BRAIN-GROUP-G1-G3-20261018/final/` — preserved historical evidence from the earlier 202-test iteration; it is not the evidence for this hardened candidate.
- `evidence/HG2-UNIFIED-BRAIN-GROUP-G1-G3-20261018/final-hardening-20261018-02/` — exact-run output, exit codes, revision/tree record and SHA-256 verification for this implementation.

## 5. Negative and regression coverage

Tests exercise at least the following failure conditions:

- missing subject/principal, wrong scope, caller-supplied boolean, unknown action;
- forged actor, mismatched requester/reviewer, self-approval, forged session payload subject;
- direct raw writes to session/task/approval event APIs without permits;
- direct arbitrary audit append without a permit;
- mutation permit replay, payload substitution, correlation substitution, actor substitution and event/action mismatch;
- event ID/idempotency-key reuse for a different operation, with no history append;
- denied outbox attempt/ack, denied migration import and denied backup/restore;
- unknown schema version, unknown/missing fields, invalid digest, result identity mismatch, fake evidence locator, absent evidence verifier, false/error evidence verifier result, and success with an unattested revision;
- provider success is logged as RESPONSE_ONLY and provider failure as FAIL, each with request/correlation linkage.

## 6. Acceptance gates

| Gate | Status | Evidence scope |
|---|---|---|
| G1 — One commander | `VERIFIED_REPOSITORY_SCOPE` | AST/source checks show only `HGAgent` composes `ToolPlane`; integration tests verify accepted/provider/completed trace shares request and correlation IDs. |
| G2 — One policy owner for public mutation APIs | `VERIFIED_PUBLIC_API_SCOPE` | Mutation permit boundary, actor/subject checks, public store guards, direct-write negative tests, outbox/migration/recovery guards and regression tests. In-process arbitrary-code sandboxing is explicitly out of scope. |
| G3 — Versioned contracts, validation and fail-closed behavior | `VERIFIED_FAIL_CLOSED_CONTRACT_SCOPE` | Request/result schemas, expected-ID binding, strict result status rules, durable result event, evidence-verifier negative tests and “provider output is not execution success” behavior. |
| Production release | `NOT_RELEASED` | No live runtime integration, deploy, service restart or live data migration; no actual execution SUCCESS is asserted by the provider-only path. |
| B1–B6 expanded cognition | `PARTIAL / DESIGN OR IMPLEMENTATION GAP` | Existing audit matrix describes perception, knowledge admission, creativity, experiment controls, development-history stewardship and capability lifecycle not yet delivered end-to-end. |

## 7. Exact-run evidence and revision binding

The earlier `final/` evidence folder is preserved as a historical run; do not use it as proof for this hardened code. Final verification for this implementation is captured in `evidence/HG2-UNIFIED-BRAIN-GROUP-G1-G3-20261018/final-hardening-20261018-02/`. The final files record:

- exact source commit/tree and branch;
- environment: Android/Termux/aarch64, kernel and Python version;
- full unit-test command/stdout/exit code;
- `git diff --check` output/exit code;
- Python AST parsing and auth-scope consistency check;
- per-file SHA-256 inventory, verified with `sha256sum -c`.

A test result applies only to the source revision recorded in that evidence file. Later documentation/evidence-only commits must not be represented as a new runtime source test unless the test command is run again.

## 8. External references applied

- OWASP, *Authorization Patterns Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Patterns_Cheat_Sheet.html — policy enforcement close to the protected resource, trusted subject context, denial by default and checks at every operation boundary.
- OWASP, *Authorization Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html — least privilege and authorization checks at the decisive server/resource boundary.
- OWASP, *Authorization Decisions and Output Handling Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Decisions_And_Output_Handling_Cheat_Sheet.html — bind each decision to the specific subject/action/context; reject missing/invalid decisions rather than treating them as permits.

## 9. Final decision

**G1–G3: VERIFIED for the declared repository/application boundary. Overall task: CLOSED_VERIFIED for G1–G3 implementation and tests; PRODUCTION NOT RELEASED.** The result path explicitly declines to claim capability-execution success until a real trusted evidence verifier and attested source revision are supplied. No canonical branch was changed, no PR was merged, no service restarted and no live data moved. The expanded B1–B6 capabilities and production release gates remain separate work; they are not silently marked complete by this result.
