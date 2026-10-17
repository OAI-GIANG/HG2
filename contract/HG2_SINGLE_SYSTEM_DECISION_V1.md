# HG2 Single-System Architecture Decision V1

Status: IMPLEMENTATION BRANCH — NOT RELEASED
Branch: `stt/hg2-single-system-20261017`
Base: canonical `hg-genesis` at `9d83a113ccdf1aeda656e494593fa55b9078c803`

## Decision

HG2 is the sole source repository and operating structure for HG. HG is the product identity (`PRODUCT_ID=HG`, `HG_STATE_V1`); HG2 is not a second product. The phone is the only primary runtime and the only canonical state owner. Any VPS is an optional edge/relay or disaster-recovery target and must never become a competing state owner.

Build one cohesive runtime from canonical HG2 source. Do not mount or import a second production runtime, do not make a staging prototype the production authority, and do not preserve parallel memory authorities merely for compatibility. UI state, indexes, caches, remote replicas and durable transport are derived/replicated layers. The phone's verified canonical state remains authoritative.

## Explicit non-goals

- No blind directory deletion, state reset, credential rotation, or backup removal.
- No production restart or cutover until the replacement has passed compatibility, data migration, backup/restore, rollback and acceptance gates.
- No inference of source provenance from HTTP status codes or process names.
- No provider/model call during storage-only acceptance tests.

## Runtime consolidation target

1. One HTTP/API process loaded from the canonical HG2 checkout.
2. One state owner based on `hg.history.StateStore`; append-only hash-chained events are the durable local authority.
3. One memory service with server-side identity/scope checks, optimistic version guards, idempotency, checksums, tombstones, and auditable events.
4. One model gateway that receives only authorized context and emits a source/version/checksum manifest.
5. One UI served by the same runtime; browser storage is cache/import input, never authority.
6. Optional durable replication uses a narrowly scoped credential and an explicit outbox/reconciliation protocol. Remote acceptance is not local commit; timeout is not success.
7. One health/diagnostics surface that distinguishes liveness, integrity, storage, model-provider readiness, and source/build identity.

## Local component disposition

- Canonical `hg/` modules, contract, tests and evidence: retain and evolve on this branch.
- `~/hg/core/runtime/hg_runtime.py`, `~/hg/backend/hg_backend.py`, `~/hg2-service/entry.py`, and staging prototypes: treat as non-canonical implementation inputs only. Do not run them as co-equal authorities after verified cutover. Preserve them read-only until the replacement is deployed and rollback is proven.
- Existing state directories, SQLite data, Library content, credentials, backups, evidence, and rollback artifacts: protected assets. Do not delete or overwrite during consolidation.
- Caches, stale checkouts, unrelated experiments and old logs: classify by dependency/retention before cleanup; no broad `rm -rf` based on directory names.

## Cutover gates

A. Source-to-artifact-to-process provenance maps to the exact canonical commit and build digest.
B. Memory API contract, scope model, and durable backend schema have contract tests.
C. Snapshot and hash all existing state/Library/SQLite data; migration is deterministic and reversible, with zero silent loss or resurrection.
D. Unit, adversarial, integration, UI, restart/replay, backup/restore and rollback tests pass without production mutation.
E. Cutover only after A-D pass; post-cutover compare health, UI, bootstrap, state counts, record checksums and history head. Roll back code/config without rolling back or overwriting newly written user state.

Until all gates pass, state remains `BLOCKED / NOT_RELEASED`; do not claim `CLOSED_VERIFIED`.
