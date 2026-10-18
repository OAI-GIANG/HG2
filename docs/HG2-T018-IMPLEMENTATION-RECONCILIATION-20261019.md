# HG2 T-018 Implementation Reconciliation — 2026-10-19

## Current architecture

- The existing target `hg/sync.py` implements `SyncDispatcher` over `SQLiteStateStore`, with outbound `send_event`, authorized principal, mutation permits and ACK validation.
- The legacy T-018 source `feat/hg-t018-cross-context-sync-20261013:hg/sync.py` implements file-spool `SyncContext` with `publish`, `export_batch`, and `import_batch`. It is a different inbound/outbound protocol, not a drop-in replacement for the current dispatcher.
- The candidate authenticated gate on the brain target is a third API surface. Its HMAC/checkpoint assumptions cannot silently override the T-018 contract.

## Contract conflict retained, not guessed

The copied contract from `docs/t018-remove-signature-scope-20261013` says `PROTOTYPE_ONLY`, does not introduce substitute authentication, and leaves the first-peer cursor trust policy unresolved. It also requires all-or-none batch application, which the per-event `StateStore.emit` loop does not prove. The design branch `design/t018-auth-checkpoint-memory-20261013` proposes authenticated checkpoint gates, so its assumptions conflict with the later contract's explicit no-substitute-authentication boundary.

## Gate decision

`BLOCKED_NO_COMPATIBLE_INCREMENTAL_IMPORT_API`. No T-018 `hg/sync.py` implementation was copied into the security target. Inbound import must remain disabled until an authorized decision defines the trust/bootstrap contract and storage boundary. `last_ack_cursor` remains outbound-only; inbound checkpoints must be peer-scoped and transactionally updated with deduplication and accepted `sync.received` envelopes.

## Acceptance still required

1. Resolve first-peer bootstrap trust and permitted authentication model.
2. Define peer-scoped inbound checkpoint, replay/dedup and conflict/quarantine state separately from outbox ACKs.
3. Implement validate-all-before-mutation and atomic batch + checkpoint commit with crash/restart tests.
4. Test unauthorized caller, duplicate/replay, provenance mismatch, gaps/forks, malformed late event, transaction rollback and restart recovery.

Source refs remain untouched. No merge of incompatible code and no branch deletion occurred.
