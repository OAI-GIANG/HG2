# T-018 Threat Model V1 — Local Spool Sync (Signature-Free Scope)

**Status:** DESIGN ONLY — TECHNICAL GATES OPEN
**Canonical boundary:** `hg-genesis` remains unchanged
**Release:** `BLOCKED`

## 1. Security objective and scope

T-018 is limited to local, same-device/same-user file-spool exchange. The goal is to preserve event consistency, idempotency, replay detection, rollback checks against a previously accepted cursor, fail-closed batch validation, and a single canonical state owner.

Digital signatures, signed envelopes/checkpoints, peer key registries and signature key lifecycle are out of scope and are not acceptance requirements. No substitute authentication mechanism is proposed. Existing host-provided credential handling and the `context_id` / `runtime_id` boundary are preserved. This design does not claim protection against an attacker who can arbitrarily rewrite the spool and recompute unkeyed hashes.

## 2. Assets and trust boundaries

The earlier source inspection was recorded at design base `4d97c34d8bb7c1091265330aef63dd78d0e72c49`; it is not a substitute for runtime evidence on the corrected commit.

### Assets
- Phone canonical event history, state projections and runtime identity.
- Event IDs, origin sequence/predecessor hashes and accepted-event index.
- Durable cursor/checkpoint state, once its initial policy is approved.
- Local spool, inbox/outbox/conflict records and audit evidence.
- Application/shared-memory values, if a future owner-approved integration is designed.
- Availability and integrity of the phone-primary runtime.

### Boundaries
1. Local producer → spool file → local importer.
2. Raw batch → parser and schema/hash validation.
3. Validated batch → replay/cursor/conflict checks.
4. Planned import → canonical persistence boundary.
5. Runtime process → durable state and audit files.

The spool is not a network transport or an authenticated identity channel. The phone remains the sole canonical state owner.

## 3. Threats, mitigations and proof obligations

| ID | Threat | Required control | Acceptance evidence |
|---|---|---|---|
| T01 | Malformed or unsupported batch | Strict schema/field validation and fail-closed rejection | Malformed/truncated/unsupported inputs rejected; no foreign event applied |
| T02 | Payload or origin-record tampering | Recompute payload and origin hashes; compare envelope and origin fields | Independent field mutations rejected |
| T03 | Full batch rewritten and hashes recomputed | Explicitly recognize this is not prevented by unkeyed hashes; constrain current scope to the local spool trust boundary | Documentation makes no sender-authentication claim; arbitrary spool writer remains a residual risk |
| T04 | Exact event replay | Durable accepted-event identity and cursor; exact duplicate is idempotent | Repeated replay, including after restart, causes no second effect |
| T05 | Event ID reused with changed content | Compare stored provenance/content; fail closed on conflict | Same ID with changed payload/hash is rejected/quarantined |
| T06 | Sequence rollback | Compare against previously accepted durable cursor | Lower sequence/head rejected |
| T07 | Fork or same-sequence conflict | Bind accepted sequence to one predecessor/head; quarantine divergence | Conflicting head for same origin/sequence is not applied |
| T08 | Sequence gap or omitted events | Enforce approved sequence policy; do not invent recovery semantics | Gap blocks import unless an owner-approved recovery rule exists |
| T09 | Untrusted initial cursor | Owner decision required; do not trust a sender-provided first head by default | First-origin import stays blocked while policy is unresolved |
| T10 | Partial persistence on failure | All-or-none apply boundary across event, dedupe, cursor and receipt | Fault injection proves full commit or no accepted mutation |
| T11 | Crash/restart | Durable replay state and deterministic recovery | Restart tests preserve cursor and duplicate behavior |
| T12 | Concurrent duplicate imports | Serialize/coordinate writers and enforce durable uniqueness | Concurrent import causes one mutation only |
| T13 | Unauthorized state import | Preserve existing authority denial; do not bypass `state.import` | Unauthorized import remains denied |
| T14 | Memory overwrite or disclosure | No shared-memory merge until schema, sharing and conflict policies are approved | Unresolved conflicts cause no application-state mutation |
| T15 | Split-brain / second state owner | Phone is sole canonical writer | Integration evidence proves no second canonical `StateStore` |
| T16 | Audit omission/tampering | Record rejection/acceptance outcomes and verify evidence hashes | Manifest rehash and negative tests pass |
| T17 | Resource exhaustion | Bound batch size/count/depth and reject malformed structures | Oversized/nested inputs fail safely; exact limits require implementation contract |
| T18 | Spool path/name manipulation | Constrain import paths to the configured spool and validate resolved file identity | Path traversal/out-of-spool paths rejected |
| T19 | Storage backend or migration failure | Do not migrate until owner decision; verify recovery properties for selected design | No migration assumed; exact storage design and fault-recovery evidence required |
| T20 | Clock rollback/freeze | Cursor/sequence, not wall-clock time alone, drives replay protection | Old sequence remains rejected after clock rollback |

## 4. Residual risks and assumptions

- Unkeyed SHA-256 detects inconsistency only when the attacker has not recomputed all dependent hashes; it does not prove authorship.
- A party able to rewrite the spool can fabricate a new origin record and recompute its hashes. Current scope does not claim to prevent this.
- The initial origin cursor/checkpoint policy is unresolved. Rollback protection against an already accepted cursor does not solve trust establishment for the first cursor.
- Atomicity across event history, projections, deduplication and cursor has not been proven by the current sequential file-write implementation.
- Shared-memory schema, access/data-sharing rules, retention and conflict policy are unresolved.
- Runtime integration is unproven; `hg/phone_runtime.py` does not currently instantiate or call `SyncContext`.
- No claim is made that signatures, another authentication mechanism, network sync, or a production key lifecycle exists or is required.

## 5. Required controls before acceptance

- Full-batch preflight and fail-closed validation.
- Durable idempotency and replay detection across restart.
- Rollback/fork checks against a previously accepted cursor, with initial-cursor behavior blocked pending owner decision.
- A proven all-or-none persistence boundary before claiming atomic apply.
- Explicitly preserved authority and single canonical writer.
- No application-memory merge until its schema and conflict policy are approved.
- Exact-commit tests and reproducible evidence hashes.

## 6. Technical status

**Current decision: BLOCKED — design and runtime gates remain open.**

This threat model is documentation-only. It authorizes no runtime patch, authentication replacement, memory policy, storage migration, canonical mutation, merge or deployment.
