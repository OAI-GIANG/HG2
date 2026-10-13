# T-018 Authenticated Sync and Shared-Memory Integration — Implementation Design V1

**Status:** DESIGN ONLY — NOT IMPLEMENTED — REVIEW REQUIRED
**Repository:** `OAI-GIANG/HG2`
**Design base:** feature commit `4d97c34d8bb7c1091265330aef63dd78d0e72c49`
**Canonical boundary:** `hg-genesis` must remain `d11e71ed8b34338b8568664b39bc777c926826d5`
**PR #8:** OPEN / DRAFT / NOT MERGED; no merge or deployment authorized
**Release:** BLOCKED

## 1. MTC-1.0 task contract

- **OBJECTIVE:** specify a reviewed path from spool-based T-018 prototype to authenticated, rollback-resistant, idempotent cross-context sync through the phone-primary runtime.
- **SCOPE:** source inspection, design, threat model, interfaces, schemas, migration options, test plan, rollback and acceptance gates only.
- **INPUT:** the exact design-base source files and the linked standards below.
- **OUTPUT:** this design, the companion threat model, and a SHA-256 evidence manifest.
- **ACCEPTANCE:** design reflects actual source; no source/runtime/audit mutation; all unresolved choices are explicit; canonical ref and PR #8 remain unchanged; design branch is separate; hashes verify.
- **EVIDENCE:** exact commit/ref, source blob SHAs, local Git checks, design-file hashes and remote refs.
- **RISKS:** incorrectly treating an unkeyed hash as authentication; replay/rollback; split-brain; partial writes; unintended disclosure; migration corruption; unreviewed key lifecycle.
- **STOP CONDITION:** stop before implementation if any required policy choice, trust root, migration boundary, or independent reviewer is missing.
- **NEXT ACTION:** independent review of the design and threat model, followed by an owner decision record for the unresolved decisions in §11.

## 2. Source inspection: observed facts at the design base

The following facts were checked against files at the exact design-base commit; these are not claims about a live deployment.

| File | Blob SHA | Observed fact |
|---|---|---|
| `hg/phone_runtime.py` | `75fa6bcda1e29bf08aeb5341dbe8f0e124684199` | Instantiates `StateStore`; does not import or instantiate `SyncContext`; no sync API is exposed. |
| `hg/sync.py` | `f5c706348de6b2364fe2286a4121594d08e74a22` | Spool-based V2; checks unkeyed hashes and in-batch continuity; stores foreign payloads as `sync.received`; does not merge them into application state. |
| `hg/history.py` | `acb466e8a4c2b8882db58b783028b59804ecc812` | Canonical JSON uses `json.dumps(sort_keys=True, separators=(',', ':'), ensure_ascii=False)`; state is JSONL history plus `head.json` and `state.json`; checkpoint is not signed. |
| `hg/authority.py` | `a9fb1ddae181944e2e87decb806368e916ac6379` | Allowlist does not authorize `state.import`; no peer-specific identity or key policy exists. |
| `hg/edge.py` | `8a018ac5a7fd6113d979f4f0e2a65bb5ae192f91` | Uses one shared bearer token for edge register/heartbeat; this is not a per-peer signed event identity contract. |
| `hg/identity.py` | `58df90a6b7d69d87df75bead52a3b3435a88f23f` | Static product/architecture/schema identity; no cryptographic peer binding. |
| `contract/ARCHITECTURE_V1.md` | `7defc59985b2ea291b614a63de0a3152b64d064d` | Phone is the sole canonical state owner; VPS1 is relay only; VPS2 must not own canonical state. |
| `docs/T-018-SYNC-V2-CONTRACT.md` | `35aba35631b8a74b0366d52f9f4c381ffc2c2a4b` | Explicitly labels sync prototype-only and lists authentication, trusted checkpoint, runtime integration and memory merge as open gates. |

A search of tracked `hg/` files at this commit found no `hg/memory.py` or `hg/core.py`; those paths return 404 at this ref. The current state projection only applies `session.created` to its session map and otherwise updates event-type counters. Therefore, **a general-purpose shared-memory data model and merge policy are not present in this repository version**.

### 2.1 Consequences

1. The current `record_hash` is a consistency hash, not proof of authorship.
2. `origin_context` is an asserted label, not an authenticated identity.
3. The local `head.json` checkpoint is an unsigned `seq`/hash pair; it is not an origin checkpoint for a remote peer.
4. `SyncContext.import_batch` loops over `StateStore.emit` for pending events. That loop is not one transaction across all events. Each `emit` writes history, state projection and head checkpoint separately.
5. The existing persistence model is JSONL plus JSON projections, **not SQLite**. A true atomic transaction spanning event history, shared-memory state, inbox/deduplication and origin cursor cannot be asserted without a storage-boundary decision.
6. The current `authorize()` allowlist rejects `state.import`; do not bypass that policy. A future import action requires a separately reviewed least-privilege authorization contract.
7. `StateStore.emit(event_id=...)` returns an existing record when an event ID already exists, without comparing the incoming event's content. The sync implementation must not use this shortcut as the sole conflict detector.

## 3. Target architecture

The phone remains the only canonical state owner. Remote contexts are authenticated producers/replicas with narrowly scoped permissions; VPS1 can relay opaque authenticated envelopes but cannot become state authority; VPS2 remains disaster-recovery-only.

Proposed inbound path:

1. **Bounded transport intake:** cap envelope/batch bytes, event count, nesting/depth and string lengths; store as untrusted bytes in a quarantine/inbox.
2. **Canonical decode:** reject duplicate JSON keys, non-finite numbers, invalid UTF-8, unknown critical fields and non-canonical signed bytes. Use RFC 8785 JSON Canonicalization Scheme (JCS) or an equally precise, versioned wire format; current Python `canonical()` is not claimed to implement JCS.
3. **Peer authentication:** resolve `peer_id + key_id` through a local trust registry; verify the signature over the versioned envelope and domain-separated context; check key status, scope, product, audience and validity.
4. **Checkpoint verification:** verify a signed source checkpoint against the enrolled peer key and the previously accepted cursor; reject rollback, gaps, forks, epoch/key confusion and duplicate IDs with changed content.
5. **Authorization and data policy:** check peer capability, event type, data class, sharing consent/allowlist and schema migration.
6. **Conflict gate:** identify conflicts but do not choose an overwrite/merge winner until §11 policy is approved. Default is quarantine + no mutation.
7. **Atomic apply:** persist accepted events, deduplication IDs, per-peer cursor, memory changes and a commit receipt atomically within one canonical storage transaction.
8. **Evidence:** append an attributable result with batch hash, peer/key ID, checkpoint before/after, accepted/duplicate/quarantined counts, transaction ID and reason codes. Never log private keys or bearer tokens.

## 4. Proposed wire/API contract (design; no API exists yet)

All APIs below are proposed names, not implemented endpoints.

### 4.1 Peer and key lifecycle

- `PeerRegistry.enroll(peer_id, public_key, key_id, scopes, product_id, status)`
- `PeerRegistry.resolve(peer_id, key_id)`
- `PeerRegistry.rotate_key(peer_id, old_key_id, new_public_key, activation_checkpoint)`
- `PeerRegistry.revoke_key(peer_id, key_id, reason, effective_checkpoint)`
- `PeerRegistry.authorize(peer_id, action, data_class)`

Requirements:
- Peer IDs are stable, unique identifiers assigned by the phone owner; never trust an ID solely because the sender supplied it.
- Enrollment/trust-root changes require an explicit owner-authorized ceremony and audit event. No trust-on-first-use without an explicit, reviewed policy.
- Prefer Ed25519 signatures through a maintained, reviewed cryptographic implementation; pin/review the dependency and test supported platform wheels. This is a proposal, not an implementation choice already approved.
- On Android, investigate a native Android Keystore-backed signing provider and hardware/key attestation where available. Do not claim hardware backing from the OS name alone. If the Python/Termux path cannot access a suitable Keystore key, that limitation is a release blocker until an accepted key-custody alternative is approved.
- Define key activation, overlap during rotation, revocation propagation, compromise recovery, backup/recovery and device replacement before enrollment goes live.
- Use mTLS where the transport supports it, but keep application-level signatures for end-to-end integrity through relays. A shared bearer token alone does not satisfy peer identity.

### 4.2 Signed envelope

Proposed envelope schema: `HG_SYNC_ENVELOPE_V3`.

Required fields:
- `schema`, `product_id`, `audience`, `peer_id`, `key_id`, `source_epoch`
- `event_id`, `event_type`, `event_schema`, `data_class`
- `origin_seq`, `origin_prev_hash`, `origin_record_hash`
- `payload`, `payload_hash`
- `created_at`, `expires_at` (only if a trusted time policy is available)
- `signature_alg`, `signature`

Signature input must be precisely specified: domain-separation prefix such as `HG-T018-ENVELOPE-V3\0` concatenated with RFC 8785 JCS bytes of the object excluding the `signature` field. Reject unknown algorithms and algorithm/key mismatch. Do not sign a JSON string whose canonicalization rules are unspecified.

### 4.3 Signed origin checkpoint

Proposed checkpoint schema: `HG_ORIGIN_CHECKPOINT_V1`.

Fields:
- `schema`, `product_id`, `peer_id`, `key_id`, `source_epoch`
- `last_seq`, `head_hash`, `previous_checkpoint_hash`
- `issued_at`, `expires_at` (conditional on trusted time), `signature_alg`, `signature`

Rules:
- The phone persists the last accepted checkpoint/cursor for each `(peer_id, source_epoch)`.
- First-time enrollment must bind a starting checkpoint to an owner-authorized enrollment record, an independently verified peer key, or an explicitly approved out-of-band fingerprint ceremony. A checkpoint self-signed by an unknown peer is not a trust anchor.
- For an established peer, the next accepted chain must extend the stored head and sequence according to the selected batch policy. Reject lower sequence, forked predecessor, same sequence with different hash, gaps (unless a separately authenticated range-proof/recovery protocol is defined), stale epochs and revoked keys.
- Do not rely only on timestamps for replay protection; time may be absent or untrusted. Use persistent sequence/cursor state plus event deduplication.
- Merkle proofs (RFC 9162) may be considered for large history/range consistency, but a Merkle root is not a peer identity or trust root by itself.

### 4.4 Import API

Proposed interface:
- `PhoneRuntime.sync_status()`: report configured peers, local cursor, health and last outcome; never expose secrets.
- `PhoneRuntime.sync_ingest(raw_envelope_or_batch, authenticated_transport_context)`: bounded intake; returns a structured result.
- `SyncService.validate(raw, context) -> ValidatedBatch`: pure validation, no mutation.
- `SyncService.plan_merge(validated_batch, policy_snapshot) -> MergePlan`: detects conflicts and required policy, no mutation.
- `SyncService.apply(plan, expected_local_head) -> CommitReceipt`: applies only if all policy decisions are resolved and the local head has not changed.
- `SyncService.get_peer_cursor(peer_id)`: read-only cursor query.

The public runtime must not accept a caller-provided `authenticated=True` boolean as proof. Authentication must be established by a trusted verifier that returns a typed/immutable principal and verified claims. A direct filesystem spool remains local-only; it is not considered a transport between runtime contexts.

## 5. Storage and migration decision

### 5.1 Existing reality

`StateStore` persists `history.jsonl`, `head.json`, `state.json` and `runtime_id`. The current implementation has no transaction manager capable of atomically committing across those files and a separate sync inbox/cursor database.

### 5.2 Options that require explicit approval

**Option A — versioned SQLite state backend (preferred for true atomicity, but a migration):**
- Introduce `HG_STATE_V2_SQLITE` behind a new storage interface.
- In one SQLite transaction write canonical event, application projection, `sync_inbox` dedupe row, peer cursor/checkpoint and commit receipt.
- Keep V1 JSONL read-only during migration; validate V1 chain, head and projection before import; record source hashes and migration manifest.
- Verify V2 reconstruction against V1 read-only evidence before any owner-approved cutover. Never silently dual-write two authorities.
- Rollback means stop V2 writes and return to the frozen V1 snapshot only if no V2-only accepted writes occurred; otherwise require a reviewed reverse/export/reconciliation procedure. Do not automatically discard accepted events.

**Option B — retain V1 JSONL with a durable recovery journal:**
- Add a write-ahead import journal and deterministic recovery protocol for multi-file writes.
- This can provide recoverability and idempotent replay but must not be described as a single atomic transaction across the files unless crash-state analysis and tests prove the required semantics.
- Keep imports disabled until every crash point is recoverable and verified.

No option is selected by this document. Owner approval and independent review are required before implementation. SQLite is not currently the canonical backend in the inspected source.

### 5.3 Proposed SQLite logical schema (Option A only)

- `peer_registry(peer_id PRIMARY KEY, key_id, public_key, algorithm, status, scopes_json, enrolled_at, revoked_at, trust_record_hash)`
- `origin_cursor(peer_id, source_epoch, last_seq, head_hash, checkpoint_hash, key_id, updated_at, PRIMARY KEY(peer_id, source_epoch))`
- `sync_inbox(peer_id, source_epoch, event_id, origin_seq, origin_hash, payload_hash, status, received_at, applied_txid, PRIMARY KEY(peer_id, source_epoch, event_id), UNIQUE(peer_id, source_epoch, origin_seq))`
- `shared_memory(memory_key, data_class, schema_version, value_json, version, origin_peer_id, origin_event_id, updated_at, PRIMARY KEY(memory_key))` — only after the memory model and conflict semantics are approved.
- `sync_receipts(txid PRIMARY KEY, batch_hash, peer_id, checkpoint_before, checkpoint_after, accepted_count, duplicate_count, quarantined_count, committed_at)`
- `sync_audit(audit_id PRIMARY KEY, txid, peer_id, event_id, action, reason_code, record_hash, recorded_at)`

Store signatures and signed checkpoint bytes needed for independent verification, subject to retention policy. Do not put private keys or bearer tokens in these tables. Add foreign keys and uniqueness constraints; test SQLite foreign-key enforcement and chosen journal/synchronous settings on the actual target filesystem.

## 6. Transaction and idempotency algorithm

1. Bound and capture raw bytes; calculate a raw SHA-256 for forensic identification, not as authentication.
2. Parse strictly; reject duplicate keys, malformed types, non-finite numbers, unsupported schema and size-limit violations.
3. Canonicalize with the chosen versioned JCS contract and verify signature against the enrolled, non-revoked peer key.
4. Validate peer authorization, product/audience, epoch and data-sharing policy.
5. Validate signed checkpoint and the stored cursor. Detect event ID reuse with different signed content as a conflict.
6. Build a merge plan without changing canonical state. If a memory conflict exists and no approved resolution rule matches, quarantine the batch.
7. Start one transaction on the selected canonical backend. Recheck expected local head/cursor under transaction; insert inbox/dedup rows; apply the approved memory operations; advance origin cursor/checkpoint; write receipt/audit metadata; commit.
8. On any exception before commit, rollback all changes. After commit, retries return the existing receipt for an exact duplicate and never reapply side effects. A duplicate key with different hash is a security conflict, not a duplicate.
9. For the V1 JSONL option, stop and use its recovery journal protocol; do not pretend steps 7–8 are atomic across files.
10. Acknowledge only after durable commit. On crash/restart, derive status from durable transaction/receipt state, not from an in-memory success flag.

## 7. Runtime integration boundary

- Only `PhoneRuntime` may construct the sync service against the canonical store; the edge relay must not instantiate a second canonical `StateStore`.
- Add a dedicated, least-privilege authorization action only after policy review; do not silently add `state.import` to the current allowlist.
- The verifier supplies a typed authenticated principal, not a user-controlled flag.
- Runtime health should distinguish `sync_configured`, `peer_auth_ready`, `checkpoint_ready`, `storage_backend_ready`, `last_sync_status` and `last_sync_error_code`. No secrets in health output.
- Network retries must be bounded, backoff-controlled and idempotent. The phone remains usable offline; failed sync does not silently alter canonical state.
- Do not introduce an inbound listener on the phone by default. The phone-initiated outbound path and VPS1 relay-only boundary remain the architecture default unless separately approved.

## 8. Required tests

### Unit / contract
- Valid signature; wrong key; altered payload; altered signature; algorithm/key mismatch; unknown/revoked peer; unauthorized event type/data class.
- Wrong product/audience/schema; unknown critical field; duplicate JSON keys; invalid UTF-8; NaN/Infinity; canonicalization edge cases.
- Signed checkpoint from unknown trust root; checkpoint rollback; sequence gap; fork; same sequence/different hash; wrong epoch; stale key; key rotation overlap; revoked old key.
- Exact replay returns same receipt without a second memory mutation; same event ID with changed signed content is quarantined.
- Invalid final event causes no earlier event in that batch to be applied.
- Conflicting memory values trigger quarantine until policy explicitly resolves them.
- Concurrent imports serialize against expected local head; unique constraints reject duplicate races.

### Integration / failure injection
- End-to-end through `PhoneRuntime`, not just direct `SyncContext` calls.
- Two separately provisioned peer identities with test-only keys; never claim live peer verification from test fixtures.
- Crash/power-loss injection before, during and after every durable write/commit boundary; restart must recover a consistent state and cursor.
- Offline/retry/reorder/duplicate transport; oversized batch; slow/truncated input; relay tampering.
- Rotation/revocation while messages are queued; old key cannot authorize after effective revocation according to approved policy.
- Reconstruct state from canonical history and compare to stored projection.
- Reopen on the target Android/Termux environment; check durability, filesystem semantics and performance.
- Verify logs contain no secrets and every rejection/commit has attributable evidence.
- Independent clean-checkout run at the exact candidate SHA; preserve raw logs, normalized logs, environment, command, exit code and SHA-256 manifest.

## 9. Rollback and recovery

- Design/docs branch only: revert the documentation commit or abandon this branch; no runtime state touched.
- Implementation rollback: stop accepting new sync batches first; preserve inbox, checkpoint, trust registry, raw evidence and receipts read-only; do not delete or reset cursors to “fix” replay.
- If using SQLite, take a consistent backup and verify integrity before restore; replay only transactions whose commit status is proven. A rollback to V1 is allowed only if no accepted V2-only state would be lost or a reviewed export/reconciliation path is used.
- If using a journal over V1 files, preserve the journal and execute a deterministic, tested recovery procedure; do not manually edit history/checkpoint files.
- Key compromise: revoke key, quarantine pending events from that key, enroll replacement only through the approved trust ceremony, and require an explicit recovery checkpoint. Do not automatically trust a replacement key.
- Any failed integrity check, uncertain commit status, missing trust anchor or unresolved memory conflict stops import (fail-closed).

## 10. Acceptance gates

| Gate | Pass criteria | Evidence required |
|---|---|---|
| D0 Source fidelity | Base SHA and source blob SHAs match; canonical unchanged | Git refs + source manifest |
| D1 Protocol review | Envelope, JCS bytes, signature domain, checkpoint and key lifecycle specified | Independent design review |
| D2 Trust enrollment | Trust root provisioned independently; unknown keys fail closed | Enrollment/revocation evidence |
| D3 Replay/rollback | Replay, rollback, fork, gap and key-rotation counterproofs pass | Exact-SHA raw test logs |
| D4 Memory semantics | Owner-approved data model and conflict policy; no implicit overwrite | Decision record + conflict tests |
| D5 Atomicity | Chosen storage backend proves crash-safe all-or-none commit for state, inbox and cursor | Crash injection + recovery evidence |
| D6 Runtime integration | Actual `PhoneRuntime` path is tested with two separately provisioned contexts | Runtime logs + environment identity |
| D7 Provenance | SHA-256 manifests verify and evidence is bound to exact tested commit | Independent re-hash and commit binding |
| D8 Independent review | Reviewer other than author reviews exact SHA and records findings | Formal review on exact SHA |
| D9 Release authorization | All mandatory gates passed and owner explicitly authorizes next action | Signed/attributable gate decision |

Until D1–D8 are independently evidenced, release stays blocked. This design does not authorize release even if documentation checks pass.

## 11. Decisions that must not be guessed

The following remain **BLOCKING DECISIONS**:
1. **Conflict policy:** reject/quarantine, last-writer-wins, field-level merge, CRDT, or domain-specific resolution. No overwrite strategy is selected here.
2. **Memory model:** what is “shared memory”, which event types populate it, schema/versioning, data classes, retention and deletion semantics.
3. **Trust ceremony:** who authorizes first enrollment, how fingerprints are verified, whether multi-person/threshold approval is required, and where recovery trust material lives.
4. **Key storage:** native Android Keystore provider feasibility on the target Termux/Python stack; key custody for non-Android peers; revocation delivery and offline behavior.
5. **Canonical storage:** approve Option A (SQLite migration) or Option B (journal/recovery with weaker atomicity claims); no dual canonical writers.
6. **Sequence recovery:** whether gaps always block or a signed range-proof/reconciliation protocol is allowed.
7. **Trusted time:** whether time-based expiry is available and how clock rollback is detected; sequence/cursor remains the primary replay control.
8. **Data-sharing authorization:** which peers may export/import which event/data classes, and consent/retention boundaries.
9. **Dependency policy:** approved cryptographic package, versions, provenance and supported Android builds.
10. **Independent reviewer:** a reviewer and authority in a failure domain distinct from the implementation author must be available; self-review is not independent verification.

No implementation patch should begin until these decisions are recorded and the design is independently reviewed.

## 12. External normative/reference material

- RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens: https://www.rfc-editor.org/rfc/rfc8705.html
- RFC 9700 — Best Current Practice for OAuth 2.0 Security: https://www.rfc-editor.org/rfc/rfc9700.html
- RFC 9421 — HTTP Message Signatures: https://www.rfc-editor.org/rfc/rfc9421.html
- RFC 8785 — JSON Canonicalization Scheme (JCS): https://www.rfc-editor.org/rfc/rfc8785.html
- RFC 9162 — Certificate Transparency Version 2.0 (Merkle tree inclusion/consistency proof concepts): https://www.rfc-editor.org/rfc/rfc9162.html
- The Update Framework specification/security model: https://theupdateframework.github.io/specification/latest/ and https://theupdateframework.io/docs/security/
- Android Keystore system: https://developer.android.com/privacy-and-security/keystore
- CloudEvents specification: https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md
- SQLite atomic commit: https://www.sqlite.org/atomiccommit.html
- SQLite transaction control: https://www.sqlite.org/lang_transaction.html
- Microsoft Event Sourcing pattern: https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing
- AWS Transactional Outbox pattern: https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html

These references inform the design; citing a standard does not mean HG2 implements or conforms to it.
