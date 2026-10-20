# HG2 State Ownership and Migration Plan — 2026-10-21

- Repository: `OAI-GIANG/HG2`
- Work branch: `stt/hg2-master-cleanup-20261021`
- Parent checkpoint: `24c80d28fa742078cc62bcbf350f98831027d97f`
- Scope: read-only dependency inspection; no live-state migration or runtime modification
- Status: **DESIGN DECISION / MIGRATION BLOCKED — NO STORE RETIRED**

## Executive decision

Adopt **one logical state-ownership boundary**: the phone's `PhoneRuntime` owns the runtime state boundary and injects its one canonical store into every runtime subsystem that reads or mutates that runtime's history. No subsystem may silently construct a second store over the same canonical state directory.

For the currently observed runtime path, `history.StateStore` remains the **temporary operational canonical backend** because `PhoneRuntime`, `MemoryStore`, and `SyncContext` use it, and existing sync integration tests assert store reuse. This is not a declaration that the JSONL implementation is the final backend or that the production runtime is release-ready.

The target architecture is a versioned `RuntimeStateBoundary` contract with exactly one selected backend per runtime identity. `SQLiteStateStore` is a candidate for a future transactional backend because its event append, task/approval projections, and outbox changes share a SQLite transaction. It must not replace `StateStore` until history/memory/sync semantics, event schema, identity, integrity, and recovery behavior have passed parity and migration tests. Dual-write is prohibited.

`DurableTransactionStore` remains a separate transaction-ledger implementation for now. It encodes plan/step/evidence/commit/recovery semantics not yet proven equivalent to task events in `SQLiteStateStore`. Do not delete or merge it until a field-by-field semantic mapping and crash-recovery proof exist.

## Dependency and function matrix

| Component | Current responsibility | Direct dependencies / use | Durable semantics | Current disposition |
|---|---|---|---|---|
| `hg.history.StateStore` | Runtime event journal, hash-chain, checkpoint/projection, runtime identity, recovery | Constructed by `PhoneRuntime`; used by `MemoryStore`; `SyncContext` accepts the same injected instance | JSONL event chain plus state/head files, bootstrap intent, fsync/atomic replacement, fail-closed recovery | **KEEP as current operational backend; target facade required** |
| `hg.memory.MemoryStore` | Memory projection and mutations | Replays and emits on injected `StateStore` | Memory records/idempotency reconstructed from canonical runtime event stream | **KEEP; must be backend-agnostic only after contract tests** |
| `hg.sync.SyncContext` / `sync.py` | Local sync event, export/import, authenticated batches, spool/cursor checks | Uses `history.StateStore`; `PhoneRuntime` injects its store; can create its own store when standalone | Separate spool/cursor files; accepted batch and cursor atomicity must be tested explicitly | **KEEP; no second store for live runtime** |
| `hg.sqlite_state.SQLiteStateStore` | Transactional hash-chained events, tasks, approvals, outbox and projections | Used by `SyncDispatcher`, `CanonicalWorkflowAdapter`, workflow/sync tests | SQLite WAL, synchronous FULL, event/projection/meta updates inside transactions, verification on open | **KEEP as isolated workflow candidate; no live-runtime cutover** |
| `hg.sync_dispatcher.SyncDispatcher` | Delivers one committed SQLite outbox item and records attempt/ack | Requires `SQLiteStateStore`, transport and principal; validates ACK binding | Outbox attempt/ack are recorded against SQLite events | **KEEP; UNBOUND from live PhoneRuntime until backend ownership is unified** |
| `hg.workflow_store_adapter.CanonicalWorkflowAdapter` | Workflow task lifecycle, task projection replay and integrity contract | Requires `SQLiteStateStore`, sealed principal, actor identity and clock | Transactional task event + projection; adapter reports `runtime_cutover_performed: false` | **KEEP; candidate only, not live-runtime adapter** |
| `hg.durable_transactions.DurableTransactionStore` | Idempotent durable transaction lifecycle, steps, evidence, commit and recovery | File-backed SQLite database supplied by caller | Separate transaction rows/event chain, explicit prepare/evidence/commit authorizers and incomplete recovery | **KEEP; semantic equivalence to workflow tasks not proven** |
| `hg.phone_runtime.PhoneRuntime` | Runtime composition and ownership root | Constructs one `StateStore`; passes it to `SyncContext`; constructs memory from same store | Defines current runtime identity and state directory | **Canonical logical owner; runtime deployment currently blocked by dirty checkout/provenance mismatch** |

## State invariants

1. One runtime identity has one explicit owner and one selected canonical state boundary.
2. Runtime components receive the owner/store by dependency injection; no hidden second owner for the same state directory.
3. Separate databases are not silently treated as one transaction. Cross-store work must use a durable transaction/saga contract with idempotency and explicit IN_DOUBT/recovery handling.
4. No dual-write migration. No deletion of old state, source files, archives, journals, or evidence during cutover.
5. A store opening successfully is not enough: chain verification, projection replay equivalence, runtime identity, outbox state, cursor state and recovery receipts must agree.
6. If ownership, identity, or recovery state is ambiguous, writes and dispatch fail closed.

## Required migration sequence

### M0 — Freeze and inventory (required before implementation)
- Record source revision, process identity, loaded-module fingerprint, on-disk hashes, service status, state paths, schema versions, runtime IDs and current dirty worktree.
- Preserve all uncommitted runtime files and logs. Do not restart or switch branches.
- Inventory all stores/databases and identify whether any two implementations point at the same directory/path.

### M1 — Contract and semantic parity
- Define the `RuntimeStateBoundary` protocol: runtime identity, owner ID, append/emit, replay, verify, audit export, idempotency, recovery state and close lifecycle.
- Map every `StateStore` event field and behavior to the SQLite event envelope, including genesis/bootstrap identity, ordering, causation/correlation, duplicate IDs, hash-chain, projection replay, incomplete-tail behavior and recovery receipts.
- Map `MemoryStore` events and projections, sync batch identity/import conflict semantics, spool durability, authenticated cursor anchoring, outbox semantics, task/approval projections and transaction-ledger states.
- Reject migration if any field or transition has no lossless representation.

### M2 — Offline backup and migration rehearsal
- Create a quiescent, consistent backup of all state files/databases, SQLite WAL/SHM state, sync spools, cursor anchors and transaction journals. Record relative paths, byte lengths, SHA-256, owner/mode, runtime ID, sequence/head, schema and UTC capture time.
- Verify the backup in a separate directory using read-only integrity/replay tools. Never test restore over the source.
- Run a deterministic migration on a disposable copy; compare canonical event semantics and projections, not just record counts.
- Keep the source copy immutable and preserve an append-only migration receipt.

### M3 — Crash/restart and fault injection
- Inject process termination at every persistence boundary: before append, during event append, after event append/before checkpoint, between projection and metadata update, after outbox send/before ACK, after ACK/before cursor commit, and during transaction prepare/commit/recovery.
- Restart repeatedly and prove exactly-once/idempotent logical effects, no accepted-prefix ambiguity, no lost ACK, no duplicated task transition, and correct IN_DOUBT classification.
- Verify state chain, all projections, outbox, cursor, runtime identity and transaction ledger before and after every restart.
- Run on Android/Termux Python version and filesystem; a desktop-only test is insufficient.

### M4 — Shadow verification without dual writes
- Keep the old backend authoritative and read-only export a consistent snapshot into a separate target directory.
- Compare semantic digests and query results. The shadow target must never receive production writes and must never be used for dispatch.
- Obtain independent review of the migration report and provenance/signature checks.

### M5 — Authorized cutover and rollback
- Cutover only during an explicitly approved maintenance window after backup and restore verification.
- Stop new writes at the application boundary only after an approved procedure; do not stop unrelated services or improvise a restart.
- Switch one backend pointer/configuration atomically; do not run two authoritative writers.
- Rollback uses the frozen pre-cutover snapshot and explicit compatibility policy. Never reverse-migrate by overwriting a newer journal.
- Keep the old backend and backup immutable until a defined observation window and acceptance gates pass.

### M6 — Retirement
A store can be removed only after repository-wide dependency coverage is complete, dynamic imports/configuration/CLI/service references are checked, the target backend passes the full regression and fault-injection suite, restore/rollback has been rehearsed, and independent provenance/review gates pass.

## Acceptance gates

- **G1 Ownership:** exactly one selected owner per runtime ID; no accidental same-directory dual store.
- **G2 Semantic parity:** event, projection, identity, idempotency and policy behavior mapped with no unexplained loss.
- **G3 Recovery:** crash/restart matrix passes on Termux; evidence hashes bind to exact candidate commit.
- **G4 Backup/restore:** independently verified backup restores to an isolated directory with identical semantic digest.
- **G5 Sync:** authenticated import, deduplication, cursor anchoring, outbox send/ACK and retry semantics pass.
- **G6 Workflow/transactions:** approvals, task transitions, evidence and IN_DOUBT recovery are equivalent or explicitly remain separate bounded subsystems.
- **G7 Provenance:** signed/verified source and independent review gates pass before push/merge/deploy.
- **G8 Runtime:** exact loaded code and disk code are matched to an approved candidate before any deployment claim.

## Current stop condition

The live `~/hg2-phone` checkout is detached at `4d97c34d8bb7c1091265330aef63dd78d0e72c49` with substantial tracked modifications and untracked source/log files. Its running `hg2-runtime` log reports `OBSERVED_UNMATCHED` and `PROCESS_LOCAL_OBSERVATION_UNATTESTED`; no expected-code fingerprint was supplied for comparison. The service is running from that dirty checkout. This blocks live migration, runtime integration, restart, deploy, and any claim of production verification. The isolated candidate worktree may continue with non-destructive documentation, tests and adapter contract work.

No store has been deleted or migrated in this phase.
