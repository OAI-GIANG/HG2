# T-018 Safe Port Gate — SQLite Dispatcher

- Target branch: `stt/hg2-circulatory-architecture-20261018`
- Audited HEAD before this evidence commit: `4e290e58aa7874add3c2bfec93cf5271c4eb4925`
- Remote refs at audit start: `25`
- Existing T-018 variants inspected: `5`; identical `hg/sync.py` payload SHA-256: `56f53b78754ff2999d5662d0ddb61246e90ac3aedd767a60f03f53b4c486ac82`.
- Regression run: `python -m unittest tests.test_sync tests.test_auth tests.test_core -v` — **OK, 42 tests**.

## Findings

1. Current `hg/sync.py:16-118` is an outbound dispatcher over SQLite outbox. It verifies an authenticated principal, records send attempts/ACKs via mutation permits, binds ACK to `event_id` and `event_digest`, and requires positive monotonic remote cursors.
2. `hg/sqlite_state.py:288-378` has an import routine only for replacing a fresh genesis; `hg/sqlite_state.py:341-350` refuses non-fresh targets. It is not a safe incremental inbound entry point.
3. The legacy T-018 `SyncContext` uses file-spool `HG_SYNC_BATCH_V2`, tracks foreign source events by `(origin_context, event_id)`, pre-validates hash/chain fields, rejects changed provenance, and quarantines conflicts. Its imports append multiple `sync.received` records separately before cursor commit; it does not guarantee atomic batch + cursor updates.
4. Five source refs have identical `hg/sync.py` SHA-256 `56f53b78754ff2999d5662d0ddb61246e90ac3aedd767a60f03f53b4c486ac82`; their differing contracts/evidence do not make them five runtime implementations.
5. Contract line anchors: `docs/T-018-SYNC-V2-CONTRACT.md:5` marks prototype-only; line `11` says no replacement authentication; line `31` leaves first-peer checkpoint unresolved; line `35` states batch atomicity is unproven; line `48` says integration remains unproven.

## Decision

**BLOCKED_NO_COMPATIBLE_INCREMENTAL_IMPORT_API**. No runtime code was ported because copying `SyncContext` or using `import_verified_events()` would either create a second state authority or violate the current migration-only boundary. No source branches were deleted or rewritten.

## Required before implementing an inbound port

- Decide trusted first-peer checkpoint/bootstrap and authorized authentication contract; reconcile the contract that excludes replacement auth with the experimental HMAC gate requiring a separately protected anti-rollback anchor.
- Add SQLite-native per-peer inbound checkpoints, deduplication and conflict state, separate from outbound ACK cursor.
- Ensure accepted event envelopes plus inbound cursor state update inside one transaction; keep foreign events as `sync.received` envelopes on the local chain.
- Test duplicate/replay, changed-provenance conflict, sequence gaps/forks, invalid later event, crash after event write, crash around cursor-anchor advance, restart recovery, and unauthorized callers.

Full machine-readable evidence: `evidence/HG2-T018-SQLITE-DISPATCHER-SAFE-PORT-REPORT-20261019.json`.
