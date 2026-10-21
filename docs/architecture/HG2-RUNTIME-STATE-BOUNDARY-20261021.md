# HG2 Runtime State Boundary — 2026-10-21

## Status

**Contract implemented for read-only inspection; backend migration remains NOT AUTHORIZED / NOT RUN.** This document and its tests operate on disposable temporary directories only. No runtime data was opened for writing, copied, migrated, or restored.

## Boundary contract: `HG_RUNTIME_STATE_BOUNDARY_V1`

`hg.runtime_state_boundary.RuntimeStateBoundary` defines the minimal *read-only* inspection surface: `runtime_id`, `replay()`, `verify()`, and `audit_export()`. `inspect_runtime_state_boundary()` fails closed unless:

1. runtime identity is a non-empty string;
2. integrity verification returns `ok: true`;
3. replay is a list of event objects;
4. audit export identifies the same runtime and event count;
5. verification and replay event counts agree.

The helper does not call mutation methods, switch a backend, infer source provenance, or certify that two stores have equivalent semantics. The two backends have different event schemas, authorization gates, recovery rules, and projection models. A shared read-only protocol is **not** proof of write-path compatibility.

## Compatibility matrix

| Component | Current role | Evidence / boundary | Phase 3 disposition |
|---|---|---|---|
| `hg.history.StateStore` | Existing file journal and runtime projection | Implements the read-only boundary; recovery behavior covered by fault-injection tests | Retain as current PhoneRuntime store; no migration |
| `hg.sqlite_state.SQLiteStateStore` | Transactional event store, projections and outbox | Implements read-only boundary; SQLite-specific authorization and transaction semantics remain distinct | Candidate only; no live cutover |
| `PhoneRuntime` | Intended canonical owner | Constructs one `StateStore`; no production identity attestation established by this test suite | Preserve current composition; runtime identity gate remains open |
| `SyncContext` | File-store sync envelope producer/importer | Injected store identity checked; integration test confirms object identity reuse | Compatible only with injected `StateStore` path tested here |
| `SyncDispatcher` | SQLite outbox transport/ack dispatcher | Receives the same SQLite instance; principal scopes and ACK binding required | No claim of compatibility with `SyncContext` wire/import semantics |
| `CanonicalWorkflowAdapter` | SQLite workflow/task projection adapter | Verifies replay against SQLite task projection; explicitly reports no runtime cutover | Keep SQLite-specific; do not adapt onto `StateStore` by duck typing |
| `DurableTransactionStore` | Separate transaction plan/step/evidence/commit ledger | Own event chain, recovery and idempotency semantics; intentionally does not satisfy runtime event-store protocol | Keep separate; no equivalence or retirement claim |
| Central Brain adapters | Routing/capability surface | No production-bound, independently verified state identity supplied by this phase | Unsafe/unproven adapters remain `UNBOUND` |

## Isolated migration rehearsal design (not a production run)

The only executed rehearsal in this phase copies a synthetic `StateStore` fixture into a temporary backup directory, compares SHA-256 hashes of copied files, reopens the copy, and verifies stable runtime identity, event count, replay and integrity. The source fixture hashes are checked again after the rehearsal. It does **not** translate file-journal events into SQLite or claim backend parity.

Before a future cross-backend rehearsal can be considered, implement and independently review an explicit versioned event mapping with:

- schema-by-schema field mapping and rejection rules for unsupported fields;
- runtime/state-owner identity policy and genesis/checkpoint semantics;
- canonical serialization, sequence ordering, digest-chain and idempotency mapping;
- projection parity for sessions, tasks, approvals, memory and outbox;
- preservation of authorization principal, evidence references, correlation/causation, delivery policy and cursor monotonicity;
- a disposable source copy with immutable source hashes, an isolated target, restore verification, and fault injection at every migration boundary;
- proof that the source remains unchanged and the target is independently replayable;
- explicit approval before any production cutover, a single atomic backend pointer, and a tested rollback path.

Do not dual-write production state. Do not migrate or restore over the live runtime directory. The transaction ledger remains separate until semantic equivalence is established independently.

## Verification executed on Termux

- `tests.test_runtime_state_boundary`: 7 tests passed (read-only contract, stable identity after reopen, sync injection/identity, shared SQLite consumer identity, ledger role separation, fail-closed checks, synthetic backup/restore with SHA-256).
- Related regression group (`test_runtime_state_boundary`, `test_state_recovery`, `test_sqlite_state`, `test_sync`, `test_phone_runtime_sync_integration`, `test_workflow_store_adapter`, `test_durable_transactions`, `test_workflow_crash_recovery`, `test_brain_orchestrator`): 101 tests passed.
- These are local test fixtures, not evidence of live runtime identity, signature provenance, independent review, or production migration readiness.

## Open gates

- [x] Full regression suite after this change: 436 tests passed.
- [x] Compile and whitespace checks passed.
- [ ] Evidence manifest with hashes tied to the tested commit.
- [ ] Commit signature/provenance verification and independent review.
- [ ] Live runtime source identity attestation and expected code fingerprint comparison.
- [ ] Explicit authorization for any cutover; none granted by this phase.

**Current phase outcome:** `PHASE3_IN_PROGRESS — MIGRATION_BLOCKED_PENDING_PARITY_AND_PROVENANCE`. Not `CLOSED_VERIFIED`.
