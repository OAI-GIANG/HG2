# T-018 Sync V2 — Contract and Acceptance Boundary

## Status

`PROTOTYPE_ONLY`; production release remains `BLOCKED`. This contract is scoped to local, same-device/same-user file-spool exchange. It does not certify production readiness, network transport, authenticated cross-device sync, or live shared-memory synchronization.

## Scope

T-018 transports origin event records through an on-disk spool and records accepted foreign events as local `sync.received` envelopes. The scope does not add a network endpoint and does not, by itself, merge foreign payloads into application state.

Digital signatures, signed envelopes, signed origin checkpoints, peer key registries, and key lifecycle for signature verification are **out of scope and are not acceptance requirements**. No substitute authentication mechanism is introduced by this contract. Existing host-provided credential handling and the `context_id` / `runtime_id` boundary must not be silently replaced or expanded. The spool is not a trust boundary against an attacker who can arbitrarily rewrite its contents.

## Event integrity

Each exported event carries the source `origin_record` plus `origin_hash`, `origin_seq`, `origin_prev_hash`, `event_id`, `event_type`, `payload`, and `payload_hash`. The receiver validates:

- required envelope and origin-record fields and schema;
- source-record hash recomputation using the existing HG canonical serializer;
- consistency between envelope fields and the hashed origin record;
- payload hash and SHA-256 field format;
- one origin context per batch;
- in-batch `origin_prev_hash` continuity and consecutive `origin_seq` values;
- duplicate identity/provenance and event-ID conflicts.

These hashes establish consistency of the submitted data only. They do not prove who created it.

## Idempotency, replay, and failure behavior

An exact repeated event must not cause a second application of its effects. Reuse of an event ID with different content or provenance is a conflict. Replay detection must use durable accepted-event/cursor state, not timestamps alone. Invalid batches are rejected and recorded; no foreign event from an invalid batch may be applied. Rejection/conflict audit events do not mean the rejected payload was accepted.

Rollback protection is required against the last durably accepted origin cursor. The initial cursor/checkpoint trust policy is unresolved; until the owner approves it, first-time origin imports must fail closed rather than treating a sender-provided initial head as independently trusted.

## Atomicity and state ownership

The complete batch must be validated before mutation. The required apply boundary must prevent a crash or write failure from leaving an accepted prefix with no matching deduplication/cursor state. The current sequence of `StateStore.emit` calls does not by itself prove all-or-none persistence across history, projections, deduplication and cursor. The storage implementation choice is not selected by this contract.

The phone remains the single canonical state owner. T-018 must not instantiate a second independent `StateStore` on the same canonical directory. `sync.received` currently preserves foreign payload and provenance; application/shared-memory merge is not implied by acceptance of a spool batch.

## Explicit limitations and unresolved decisions

- No signature-based or replacement authentication mechanism is required or authorized by this contract.
- The spool is local-only; network and cross-device transport are outside the current scope.
- `origin_context` is a claimed context label, not a cryptographically authenticated identity.
- A party able to rewrite the entire batch can fabricate records and recompute unkeyed hashes.
- The initial trusted cursor/checkpoint policy is unresolved and requires an owner decision.
- Shared-memory schema, data-sharing rules, retention and conflict-resolution semantics are unresolved; do not overwrite or merge conflicting values automatically.
- Storage migration (including SQLite) is not selected.
- The current `hg/phone_runtime.py` does not instantiate or call `SyncContext`; runtime integration remains unproven.
- This contract does not describe T-018 as authenticated cross-device sync or as a production shared-memory backend.

## Required gates before release

1. Preserve the existing host credential and `context_id` / `runtime_id` contract without adding a signature requirement or substituting another authentication scheme.
2. Obtain an owner decision for the initial origin cursor/checkpoint policy; prove replay and rollback handling against persisted accepted state.
3. Define shared-memory schema, sharing permissions, retention and conflict behavior before any application-state merge.
4. Choose and independently review a storage/apply boundary that satisfies the all-or-none requirement; no storage migration is presumed.
5. Integrate through the single canonical state owner; do not open a second independent `StateStore` on the canonical directory.
6. Test duplicate/replay, changed-content ID conflict, sequence gaps/forks, malformed batches, restart, crash/failure points and offline recovery.
7. Run tests against exact commit, record provenance and obtain independent review.

## Canonical boundary

This contract correction is documentation-only on a separate branch. It does not modify `hg-genesis`, merge any branch, or deploy runtime code. Release remains `BLOCKED` until the gates above are independently evidenced.
