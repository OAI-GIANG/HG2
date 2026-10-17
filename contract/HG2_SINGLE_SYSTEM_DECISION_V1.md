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
5. One UI served by the same runtime; browser storage is cache/import input, never authority. Read and write tokens are distinct, entered in memory only, and never stored in browser storage.
6. Optional durable replication uses a narrowly scoped credential and an explicit outbox/reconciliation protocol. Remote acceptance is not local commit; timeout is not success.
7. One health/diagnostics surface that distinguishes liveness, integrity, storage, model-provider readiness, and source/build identity.
8. The canonical API binds to loopback only. Remote access must go through an authenticated HTTPS edge; no public cleartext listener is permitted.

## Current implementation branch evidence

- `hg/memory.py`: event-sourced memory with explicit scopes, optimistic version checks, idempotency, checksums, tombstones, no resurrection, deterministic lexical retrieval, and context manifests marked `model_called=false`.
- `hg/model_gateway.py`: OpenAI-compatible provider adapter that keeps retrieved memory as untrusted data, stores hashes/provenance rather than prompt or response bodies in audit events, reports configuration without contacting the provider, requires HTTPS except loopback tests, rejects embedded URL credentials/query strings, and refuses redirects to prevent bearer-token forwarding.
- `hg/durable.py`: append-only event-log outbox, deterministic batch/idempotency IDs, explicit non-wildcard `HG_DURABLE_MEMORY_SCOPES` allowlist so excluded memory cannot leak to the remote, strict contract negotiation including explicit `MEMORY_PERSIST` capability, authenticated delivery, TLS-required remote URLs, redirect rejection to prevent bearer-token forwarding, strict receipt validation, and append-only acknowledgement. Delivery is at-least-once; remote receipt never replaces the phone's state authority.
- `hg/replica.py`: HG2-owned SQLite batch receiver for memory events only; strict event+record hash/checksum and scope validation, idempotent transactions/receipts, tombstones, no read API, loopback-only bind, and `WAL`/`synchronous=FULL`. Its status does not disclose scope names. It is code/test only and is NOT deployed. Its SQLite event payloads are plaintext at rest, so disk/volume encryption, a dedicated `MEMORY_PERSIST` credential, HTTPS edge, and restore rehearsal remain required before enabling it. Runbook: `docs/HG2_DURABLE_REPLICA_RUNBOOK_V1.md`.
- `hg/server.py` + `ui/index.html`: one-process local API/UI with chat, retrieval, context preview, memory CRUD, hash-verified Library metadata API (`GET /api/library`), and durable status/sync endpoints; health fails closed if source files change after startup. Requires separate `HG_API_READ_TOKEN` and `HG_API_WRITE_TOKEN`, explicit read/write scopes, and loopback bind. `hg/provenance.py` exposes a deterministic source manifest and requires a declared 40-char commit plus matching 64-char source digest at startup; `tools/run_phone_runtime.sh` is the fail-closed launcher.
- `tools/legacy_state_preflight.py` + `tools/import_legacy_state.py`: read-only inventory and dry-run-by-default importer. The importer preserves legacy messages/conversations as inert events, copies only verified Library assets inside the canonical root, and redacts device tokens from the event log.
- Rehearsal against the frozen snapshot imported 31 scoped memories, preserved 2 unscoped records in quarantine, imported 68 messages and 4 conversations, copied 4 verified assets, quarantined 13 unsafe/missing Library metadata records, and recorded 2 device records without tokens. The hash-chained target passed integrity and content/hash reconciliation. This is staging evidence only, not a production cutover. Detailed import evidence: `evidence/HG2-UNIFIED-STAGING-IMPORT-20261017.json`.
- Earlier API smoke evidence applies only to a pre-provenance runtime revision: `evidence/HG2-UNIFIED-RUNTIME-API-SMOKE-20261017.json`. Candidate `ac4c6b980befa73aeae989b3543227d85ce0f023` passed 17/17 loopback acceptance checks using `tools/smoke_single_system.py`, including exact source manifest ↔ process PID/commit, independent read/write tokens, Library hash checks, memory create/read/tombstone, no model provider call, and durable endpoint fail-closed. An isolated 127-event staging snapshot passed byte-identical backup copy, replay integrity and history-head reconciliation. The durable sender now requires an explicit non-wildcard `HG_DURABLE_MEMORY_SCOPES` allowlist and never sends excluded scopes. Local suite: 84 passed, 26 subtests passed; Python compilation, launcher shell syntax, UI inline JavaScript syntax, and `git diff --check` passed. Evidence: `evidence/HG2-SOURCE-PROVENANCE-STAGING-20261017.json`, status `PASS_STAGING_ONLY`. Legacy source SHA and production PID snapshot remained unchanged; this is not production cutover evidence.
- Durable outbox tests pass for missing credentials, successful receipt, idempotent acknowledgement, invalid receipt and legacy-contract mismatch. Source inspection of the current backend confirms it exposes `/backend/memory/persist` with a legacy `{memory_id, claim, version, checksum, ...}` schema but no `/backend/hg2/capabilities`, no scope field in persisted records, and no tombstone contract. The adapter therefore fails closed on contract negotiation and never posts memory to that backend. A token with only `MEMORY_PERSIST` exists in backend configuration, but it has not been copied into runtime config because the destination contract is incompatible.
- `tests/` and `tools/smoke_single_system.py` cover independent read/write authorization, model-provider fail-closed behavior, durable-contract fail-closed behavior, Library asset checksum/path containment, source-manifest mismatch, and end-to-end receiver/idempotency/backup-restore tests. The reusable smoke is restricted to loopback port 8788 and has no real model call.
- The inactive durable replica stores payloads in plaintext SQLite. Do not enable it until the remote filesystem is encrypted at rest, a dedicated `MEMORY_PERSIST` credential is provisioned for the exact compatible endpoint, HTTPS is proven, and external backup/restore/rollback have been rehearsed.
- Production API read/write credentials have not been provisioned. Do not deploy until credential ownership/provisioning is resolved without reusing a credential outside its intended scope.

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
