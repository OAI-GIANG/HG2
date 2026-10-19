# T-018 Sync V2 — Contract and Acceptance Boundary

## Status

`PROTOTYPE_ONLY`; this contract does not certify production readiness, runtime integration, or live cross-context memory synchronization. Release remains blocked only by applicable technical gates below.

## Scope

T-018 V2 transports origin event records through an on-disk spool and records accepted foreign events as local `sync.received` envelopes. It does not, by itself, merge foreign payloads into the receiver's application state or expose a transport endpoint to other runtime contexts.

## Event integrity

Each exported event carries the source `origin_record` plus its `origin_hash`, `origin_seq`, `origin_prev_hash`, `event_id`, `event_type`, `payload`, and `payload_hash`. The receiver checks:

- required envelope and origin-record fields;
- source-record hash recomputation using the HG canonical serializer;
- consistency between envelope fields and the hashed origin record;
- payload hash and SHA-256 field format;
- one origin context per batch, where `context_id` is present;
- in-batch `origin_prev_hash` continuity and consecutive `origin_seq` values;
- duplicate identity/provenance and event-ID conflicts.

The complete batch is preflighted before any foreign event is appended. A semantically invalid later event must not cause an earlier event from that batch to be accepted.

## Idempotency and failure behavior

An exact repeated event is treated as a duplicate. Reuse of an event ID with different payload or provenance is a conflict. Invalid batches are rejected and recorded; their foreign events are not applied. Local rejection/conflict audit events are expected and are not evidence that the rejected foreign payload was accepted.

## Explicit security limitations

- SHA-256 proves record consistency, not sender identity. A party able to rewrite the entire batch can fabricate a new record and recompute its hashes; peer authentication must be provided separately by the configured authentication mechanism.
- `origin_context` is a claimed context label, not a cryptographically authenticated identity.
- For the first event received from a context, this prototype does not possess an independently trusted origin checkpoint. Its `origin_prev_hash` is therefore not anchored to a previously trusted source head.
- The spool transport has no peer authentication or authorization contract in this module.
- `hg/phone_runtime.py` does not instantiate or call `SyncContext`; T-018 is not connected to the canonical phone runtime by this branch alone.
- `sync.received` records preserve foreign event payloads and provenance; this module does not merge them into shared memory or application state.

These limitations are blockers for `LIVE_VERIFIED` and production memory synchronization. Do not describe the current module as authenticated cross-device sync or as a shared memory backend.

## Required production gates

1. Define and implement authenticated peer identity and key provisioning (for example, an approved MAC/key-management contract).
2. Define a trusted initial origin checkpoint and per-origin cursor policy; reject gaps and forks against the last accepted origin head.
3. Define data-classification, sharing permissions, retention and conflict-resolution semantics.
4. Integrate through the single canonical state owner without opening a second independent `StateStore` on the same directory.
5. Define a transport/API and failure/retry behavior; do not assume local spool files are a cross-runtime transport.
6. Test two actual authorized runtime contexts, restart, tamper, replay, sequence gaps, conflicts and offline recovery.
7. Verify source/runtime identity and the tested deployment evidence using hashes, exact revisions, and runtime observations appropriate to the claim.

## Canonical boundary

This branch is an isolated feature branch. It does not modify `hg-genesis` or establish that the canonical `OAI-GIANG/GO` branch has a runtime implementation. The current canonical GO README states `PRODUCT_IMPLEMENTATION: NOT_STARTED` and `RELEASE: BLOCKED` (README blob SHA `79d9db52df0b341ac5dd091dea851185b7ff72d3`, branch `hg-genesis`, observed head `c6f37fce653d8f7515404829d72c95605b227442`).
