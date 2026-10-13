# T-018 Design Gate — Internal Pre-Review Findings

**Review classification:** INTERNAL TECHNICAL PRE-REVIEW — NOT INDEPENDENT REVIEW  
**Exact design commit reviewed:** `6f636c5ebdf7363172fdd2cbda6d72258179589d`  
**Design branch at review start:** `design/t018-auth-checkpoint-memory-20261013`  
**Source baseline:** `4d97c34d8bb7c1091265330aef63dd78d0e72c49`  
**Canonical expected:** `hg-genesis@d11e71ed8b34338b8568664b39bc777c926826d5`  
**PR #8 expected:** OPEN / DRAFT / NOT MERGED  
**Disposition:** BLOCKED — no implementation patch recommended yet.

This report records a technical pre-review by the current assistant/tool session. It is not an independent reviewer submission, not a formal GitHub review, and not a release approval. The GitHub collaborator and contributor listing returned only `OAI-GIANG`; PR #8 had no reviews, review threads, or review requests. No independent reviewer was available from the observed repository access, so none is claimed.

## Evidence and scope

- GitHub commit readback confirms the exact commit and one-parent relationship: `6f636c5ebdf7363172fdd2cbda6d72258179589d` parent `4d97c34d8bb7c1091265330aef63dd78d0e72c49`.
- GitHub compare reports exactly four added files and no modifications/deletions: implementation design, threat model, SHA256SUMS, manifest.
- The source blob IDs in the design manifest were checked against Git objects at the source baseline and matched:
  - `hg/phone_runtime.py`: `75fa6bcda1e29bf08aeb5341dbe8f0e124684199`
  - `hg/sync.py`: `f5c706348de6b2364fe2286a4121594d08e74a22`
  - `hg/history.py`: `acb466e8a4c2b8882db58b783028b59804ecc812`
  - `hg/authority.py`: `a9fb1ddae181944e2e87decb806368e916ac6379`
  - `hg/edge.py`: `8a018ac5a7fd6113d979f4f0e2a65bb5ae192f91`
  - `hg/identity.py`: `58df90a6b7d69d87df75bead52a3b3435a88f23f`
  - `contract/ARCHITECTURE_V1.md`: `7defc59985b2ea291b614a63de0a3152b64d064d`
  - `docs/T-018-SYNC-V2-CONTRACT.md`: `35aba35631b8a74b0366d52f9f4c381ffc2c2a4b`
  - `manifest.json`: `f30da194e246dba2773125d074488a30912635eb`
- `sha256sum -c evidence/T-018-DESIGN-20261013/SHA256SUMS.txt` passed.
- GitHub readback at review time: canonical ref remained `d11e71ed8b34338b8568664b39bc777c926826d5`; feature ref remained `4d97c34d8bb7c1091265330aef63dd78d0e72c49`; PR #8 was OPEN/DRAFT, not merged, with no reviews/review requests.
- No runtime code, audit log, canonical ref, PR #8 or deployment was changed by this pre-review.

## Findings

### F-01 — BLOCKER: SQLite schema does not define the canonical event log

**Locations:** design §5.2–§5.3 (approximately lines 126–157); design §6 step 7.  
**Source evidence:** `hg/history.py:28–30` defines `history.jsonl`, `head.json`, `state.json`; `hg/history.py:129–137` appends the canonical history record and then writes state/head projections. The proposed SQLite schema lists peer registry, origin cursor, sync inbox, shared memory, receipts and sync audit, but no canonical event-history table, despite §5.2 saying the canonical event is written in the transaction.

**Impact:** The design does not identify the authoritative event history that replaces or wraps the current JSONL chain. It is therefore not yet possible to prove one atomic commit covers canonical history, projection, deduplication, cursor and receipt, or to specify deterministic reconstruction of state.

**Required remediation:** Add a versioned canonical event table/schema with local sequence, event ID, event type, payload/canonical bytes, recorded metadata, predecessor hash and record hash; define how a received origin event is represented as a local canonical event without importing a foreign sequence into the local chain; specify projection rebuild and migration verification. Or explicitly define a transactional storage abstraction whose authoritative event log and transaction semantics are concrete. Re-review the complete schema before implementation.

**Reproduction/evidence:** Compare design §5.3 table list with source `hg/history.py:28–30, 117–137`; no canonical event table appears in the proposed schema.

### F-02 — HIGH: peer registry cannot represent key rotation overlap

**Locations:** design §4.1; §5.3 `peer_registry` schema; threat model T10.  
**Evidence:** proposed schema is `peer_registry(peer_id PRIMARY KEY, key_id, public_key, ...)`, which permits only one row per peer. Design §4.1 requires key overlap during rotation and §8 requires queued-message rotation/revocation tests.

**Impact:** The schema cannot naturally retain old and new key records concurrently with activation/revocation intervals, and cannot independently verify queued events signed by a previously valid key under a documented overlap policy.

**Required remediation:** Use a composite identity such as `(peer_id, key_id)`; define immutable key versions, algorithm, public-key fingerprint, status, activation sequence/checkpoint, revocation effective point, permitted scopes and retention. Specify how a cursor/checkpoint binds to the key valid at that point and how queued events are treated during overlap. Add rotation/revocation state-machine tests.

### F-03 — HIGH: signed checkpoint cryptographic and transition semantics are incomplete

**Locations:** design §4.3; §6 steps 4–8; threat model T06–T09.  
**Evidence:** checkpoint fields include `head_hash` and `previous_checkpoint_hash`, but unlike the envelope in §4.2, the design does not define the exact checkpoint signature input/domain separator, the checkpoint's own hash calculation, the exact meaning of `head_hash`, or a complete before/after cursor transition algorithm.

**Impact:** Independent implementations could interpret the same checkpoint differently. A reviewer cannot yet establish exactly which source record is represented by `head_hash`, which bytes are signed, or when a batch may advance a cursor without accepting a fork, gap or stale epoch.

**Required remediation:** Specify a versioned canonical checkpoint object; domain-separation string; signature field exclusion; checkpoint hash algorithm; binding between `last_seq` and the final origin record hash; `previous_checkpoint_hash` semantics; trusted bootstrap checkpoint; and a deterministic transition table for first enrollment, contiguous batch, exact duplicate, gap, fork, epoch reset, key rotation and revocation. Include golden signature/checkpoint vectors and negative tests.

### F-04 — HIGH: Option B recovery-journal proposal lacks a recoverable state machine

**Locations:** design §5.2 Option B and §9 rollback/recovery.  
**Source evidence:** current V1 writes history, state projection and head checkpoint through separate file operations (`hg/history.py:129–137`). Import then loops over individual `StateStore.emit` calls (`hg/sync.py:205–211`).

**Impact:** The design correctly warns not to call V1 file writes atomic, but the Option B proposal does not specify journal records/states, durability ordering, recovery decisions for every crash point, or how a partially appended JSONL record is reconciled. It is not an implementable crash-recovery protocol yet.

**Required remediation:** Either choose the SQLite option after owner approval and define the canonical event table (see F-01), or specify a complete journal state machine, durable ordering/fsync requirements, crash-point matrix, idempotent recovery algorithm and proof that no event/cursor can advance inconsistently. Do not implement or claim all-or-none semantics until tested.

### F-05 — HIGH: audit durability semantics conflict between transaction-coupled and rejected operations

**Locations:** design §3 step 8; §5.3 `sync_audit`; §6 step 7; threat model T20.  
**Evidence:** the design calls for append-only attributable audit evidence, but places audit metadata in the same transaction as successful application and does not define how rejected or rolled-back attempts are durably recorded. The SQLite table schema also does not itself enforce append-only behavior.

**Impact:** If a transaction rolls back, its in-transaction audit row rolls back too. Conversely, writing a rejection record outside the transaction cannot be assumed atomic with the failed application. The threat model currently promises auditability without defining these distinct failure semantics.

**Required remediation:** Separate (a) commit receipts that must commit atomically with successful state changes and (b) rejection/security-attempt evidence recorded through a separately specified durable append-only path. Define failure behavior if that evidence path is unavailable; specify tamper detection/anchoring and retention. Enforce append-only at the storage/application boundary and test update/delete/tamper attempts.

### F-06 — HIGH: source epoch, key rotation and cursor lifecycle are not fully connected

**Locations:** design §4.1–§4.3; §5.3 `origin_cursor`; threat model T06, T08, T10–T11.  
**Evidence:** `origin_cursor` is keyed by `(peer_id, source_epoch)` and stores a single `key_id`, while the key registry schema has a single key per peer. The document says to reject stale epochs and define revocation behavior but does not define who may advance an epoch or how a legitimate source reset/device replacement is authenticated.

**Impact:** A restart, restore, replacement device or key compromise could create ambiguity about whether a new epoch is legitimate or an attempt to reset sequence history and bypass anti-rollback checks.

**Required remediation:** Define epoch creation/rotation/recovery authorization, how the new epoch is linked to the last trusted checkpoint, who signs it, how old epochs are retired, how backups restore cursor state, and how events from old keys/epochs are treated. No automatic epoch reset or cursor reset.

### F-07 — MEDIUM: API trust boundary for the authenticated principal needs an enforceable contract

**Locations:** design §4.4 and §7.  
**Evidence:** `sync_ingest` accepts an `authenticated_transport_context` argument, while the prose says a caller-provided `authenticated=True` flag is not proof and requires a typed immutable principal.

**Impact:** Without a precise construction/ownership rule, a caller may construct or spoof the context object, or code may confuse a transport-authenticated connection with authorization to import a particular event/data class.

**Required remediation:** Define the verifier-owned principal type, provenance of construction, verified key/peer/audience/claims, action/data-class scopes, and binding of the principal to the signed envelope. Public entry points should not trust caller-asserted identity fields. Add tests for forged context objects and valid identity with insufficient scope.

### F-08 — MEDIUM: cited standards are not mapped to explicit conformance choices

**Locations:** design §4.2, §4.4, §12; threat model §5.  
**Evidence:** the design links RFC 8705, RFC 9700, RFC 9421, TUF and CloudEvents, but the proposed wire protocol is a custom application envelope and does not define a standards-to-control mapping. No CloudEvents field mapping/profile is specified; RFC 9421 concerns HTTP message signatures and is not by itself a definition of the proposed signed JSON envelope.

**Impact:** Reviewers may mistakenly infer compliance or miss which security properties come from the custom signature protocol versus HTTP/mTLS/OAuth or update metadata.

**Required remediation:** Add a standards matrix: each reference → exact control/field/protocol used, normative section, implementation test, and explicit “not used/not claiming conformance” where applicable. Decide whether CloudEvents is the event envelope or merely a conceptual reference; specify how RFC 8705/9700 apply if OAuth/mTLS is actually used; keep application-level signatures separate from HTTP signature semantics. Treat TUF as an explicit key/policy metadata update mechanism only if that is intended.

### F-09 — MEDIUM: SQLite append-only audit claim is not enforced by the proposed schema

**Locations:** design §5.3 `sync_audit`; threat model §2 and T20.  
**Evidence:** the proposed table defines columns and a primary key but no immutability policy, triggers, database authorizer boundary, or externally verifiable chain/anchor.

**Impact:** A table named `sync_audit` is not inherently append-only; an ordinary database writer could update/delete prior rows.

**Required remediation:** Define a threat-appropriate immutability control, tamper-evident chaining and independent verification/export. Explain the limits if the phone process/database owner is compromised. Do not call the audit store append-only until the enforcement and tamper tests are specified.

### F-10 — MEDIUM: storage transaction durability profile is deferred without a decision gate detail

**Locations:** design §5.3 and §8 integration/failure tests.  
**Evidence:** design says to test SQLite journal/synchronous settings on target filesystem but does not state a minimum durability profile or how the owner chooses between performance and power-loss durability.

**Impact:** A transaction can be logically atomic while its durability after power loss depends on SQLite configuration and filesystem/device behavior.

**Required remediation:** Add an owner-approved durability target, required SQLite settings, directory/filesystem assumptions, expected behavior under sudden power loss, and evidence criteria for the actual Android/Termux device. Do not treat unit tests on another host as target-device durability evidence.

## Decisions intentionally left unresolved

The following are correctly treated as owner decisions and must remain unresolved rather than guessed: shared-memory conflict policy; memory schema/data classes/retention/deletion; trust enrollment ceremony; accepted key custody; SQLite migration vs journal approach; sequence-gap recovery; trusted time; data-sharing scopes; crypto dependency policy; and independent reviewer.

## Gate decision

- `SOURCE_BLOB_MATCH=PASS` for all nine source entries listed in the design manifest.
- `DESIGN_HASH_VERIFICATION=PASS`.
- `DESIGN_SCOPE_DIFF=PASS`: only the four expected documentation/evidence files were added relative to the design base.
- `INDEPENDENT_REVIEW=BLOCKED`: repository collaborators and contributors read back only `OAI-GIANG`; PR #8 has no reviews or requests; no independent reviewer handle was provided.
- `DESIGN_REVIEW=BLOCKED`: this pre-review found unresolved blocking design issues F-01 through F-06; medium findings F-07 through F-10 also require resolution before implementation planning is accepted.
- `IMPLEMENTATION=NOT_AUTHORIZED`.
- `CANONICAL=UNCHANGED`.
- `PR_8=OPEN/DRAFT/NOT_MERGED`.
- `DEPLOYMENT=NOT_AUTHORIZED`.
- `RELEASE=BLOCKED`.

**Required next action:** nominate or grant access to an independent reviewer; resolve the design blockers in a revised design commit; then have that reviewer assess the exact revised SHA and submit formal review findings. No implementation patch should be proposed before that gate passes.
