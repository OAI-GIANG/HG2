# T-018 Threat Model V1 — Authenticated Cross-Context Sync

**Status:** DESIGN ONLY — REVIEW REQUIRED
**Design base:** `4d97c34d8bb7c1091265330aef63dd78d0e72c49`
**Canonical:** `hg-genesis@d11e71ed8b34338b8568664b39bc777c926826d5` — must not change
**PR #8:** OPEN / DRAFT / NOT MERGED
**Release:** BLOCKED

## 1. Security objective

Only an enrolled and authorized peer may submit correctly signed events that extend a trusted origin history. The phone remains the sole canonical state owner. An event is reflected in shared memory only after schema, identity, checkpoint, authorization, data-sharing and conflict checks pass, and only as part of a durable all-or-none commit with inbox/deduplication and cursor advancement.

## 2. Assets and trust boundaries

### Assets
- Phone canonical event history, projections and runtime identity.
- Shared-memory values and their provenance/retention rules.
- Peer registry, public keys, key statuses and trust-root records.
- Per-peer epoch, accepted sequence, head hash and signed checkpoint.
- Inbox/deduplication records, transaction receipts and append-only audit evidence.
- Availability and integrity of the phone-primary runtime.
- Confidential payloads, secrets and any personal/sensitive data carried by events.

### Trust boundaries
1. Remote peer → transport/relay → phone runtime.
2. Untrusted raw batch → strict parser/canonicalizer → signature verifier.
3. Verified identity → authorization/data-sharing policy.
4. Validated events → conflict planner → canonical storage transaction.
5. Runtime process → persistent storage and Android key provider.
6. Implementation author → independent reviewer and release authority.

VPS1 is a relay, not a trust root or canonical state owner. VPS2 is disaster recovery, not an independent primary. Local spool files are untrusted input unless protected by a verified local boundary and still pass all envelope checks.

## 3. Adversaries and assumptions

Consider: a network attacker; a malicious or compromised peer; a compromised relay; an attacker who can copy/rewrite spool files; a stale/replayed batch; a peer with a revoked/rotated key; local file tampering; process crash/power loss; clock rollback; concurrent import; malformed/oversized JSON; a compromised signing key; and an authorized peer sending data outside its allowed scope.

Do not assume:
- SHA-256 proves authorship.
- A claimed `origin_context` identifies a peer.
- TLS alone proves which event bytes a peer authored after relaying.
- a signed checkpoint from an unknown key is trusted.
- a timestamp is reliable without a time policy.
- two separate files or a sequence of file writes commit atomically.
- a passing unit test proves runtime integration or independent review.

Residual assumptions to document: phone OS/runtime not fully compromised; trusted enrollment action is protected; cryptographic implementation is correct; storage and key provider satisfy their stated guarantees. If any assumption is outside observed evidence, mark it UNVERIFIED.

## 4. Threats, mitigations and proof obligations

| ID | Threat | Required mitigation | Counterproof / acceptance |
|---|---|---|---|
| T01 | Forged `peer_id` / spoofed origin | Registry-bound key and signature over canonical envelope | Unknown peer/key rejected; claimed ID alone has no authority |
| T02 | Payload tampering | Signature covers payload hash and all security-relevant metadata; recompute payload hash | Flip payload/metadata/signature independently; all rejected |
| T03 | Entire batch rewritten and re-hashed | Asymmetric signature and trusted key binding | Recompute all SHA-256 fields without signing key; rejected |
| T04 | Replay of a valid event | Persistent unique inbox key + cursor; return prior receipt for exact duplicate | Same event replayed repeatedly; one mutation only |
| T05 | Event ID reuse with changed content | Unique ID + stored content/provenance hash comparison | Same peer/epoch/event ID, different hash → quarantine and alert |
| T06 | Checkpoint rollback | Compare signed checkpoint with durable previously accepted cursor/epoch | Lower seq/head or old checkpoint rejected |
| T07 | Fork / same-sequence conflict | Bind seq to one origin hash and predecessor; detect branch divergence | Two different hashes for same peer/epoch/seq → no apply |
| T08 | Gap / omitted history | Strict next-sequence policy; separately review any range-proof recovery | Missing sequence blocks until approved recovery proof |
| T09 | Unknown first checkpoint | Out-of-band/owner-authorized enrollment checkpoint | Self-signed unknown peer checkpoint cannot establish trust |
| T10 | Key rotation or revocation race | Versioned key status/effective checkpoint, explicit overlap and revocation semantics | Old key after effective revocation rejected; queued events follow documented policy |
| T11 | Compromised signing key | Revocation, narrow scope, rotation, audit, quarantine and recovery checkpoint | Revoked-key test; no silent trust-root replacement |
| T12 | Unauthorized data import | Typed principal + action/data-class allowlist; no caller-controlled boolean | Peer with read-only scope cannot import/write; policy default deny |
| T13 | Memory overwrite/conflict | Explicit owner-approved conflict policy; default quarantine | Divergent values never silently overwrite |
| T14 | Partial batch apply | One canonical transaction for state + inbox + cursor + receipt | Inject failure at every step; either all commit or none |
| T15 | Crash between file writes | SQLite transaction or tested durable recovery journal | Process/power-loss fault injection and restart reconstruction |
| T16 | Concurrent duplicate imports | Transaction isolation, uniqueness constraints, expected-head compare-and-swap | Concurrent same batch yields one mutation/receipt |
| T17 | Malformed/oversized input | Strict parser, body/count/depth limits, timeouts, resource caps | Fuzz malformed JSON, duplicate keys, huge nesting/body, non-finite numbers |
| T18 | Canonicalization ambiguity | Versioned RFC 8785 JCS contract; reject duplicate keys and unsupported values | Cross-implementation golden vectors and signature equivalence tests |
| T19 | Relay compromise / MITM | End-to-end envelope signature; mTLS where available; relay has no signing key | Relay changes/reorders/replays envelope; signature/cursor gate rejects |
| T20 | Audit forgery or missing evidence | Append-only attributable receipt with exact hashes; protect audit writer; external anchoring only if approved | Tamper test and manifest rehash; missing evidence blocks gate |
| T21 | Secret leakage | Never log private keys/tokens; redaction and least privilege | Scan logs/fixtures for secrets; test rejection messages |
| T22 | Split-brain / second primary | Phone is sole canonical owner; relay/DR never accepts canonical writes | Verify no second writer/store is instantiated in integration test |
| T23 | Dependency compromise | Pinned, reviewed crypto dependency, provenance and update policy | Lockfile/SBOM/hash evidence and clean reproducible install |
| T24 | Clock rollback/freeze | Sequence/cursor primary; time expiry only with trusted-time policy | Roll clock backward and replay old envelope; cursor still rejects |
| T25 | Data deletion/retention conflict | Explicit deletion/tombstone/retention semantics and authorization | Deletion replay, restore and retention tests per approved policy |

## 5. Security controls required before any implementation is accepted

- Domain-separated signature over a versioned canonical envelope.
- Independently enrolled peer trust roots and key lifecycle.
- Signed checkpoints chained to previously accepted state.
- Durable event identity and cursor with uniqueness constraints.
- Explicit peer action/data-class authorization.
- A defined memory schema and conflict policy; unresolved conflicts quarantine.
- Single canonical writer and transaction boundary.
- Crash recovery and exact-SHA test evidence.
- Append-only, attributable audit evidence with a verifiable manifest.
- Independent review by a reviewer other than the author.

## 6. Residual risks and non-goals

- Cryptography cannot protect against a fully compromised phone OS/process that can use the signing key and alter the canonical database.
- Signatures prove control of an enrolled key, not that a peer's payload is factually true.
- Availability can still be denied by withholding messages, disconnecting a peer or corrupting a relay.
- A Merkle proof demonstrates inclusion/consistency relative to a root; it does not identify who is entitled to set that root.
- A compromised authorized peer can send malicious but correctly signed payloads within its scope; schema validation, policy and conflict controls remain necessary.
- This design does not establish compliance certification, deployment readiness, production key custody, or live synchronization.

## 7. Review decision

**Current decision: BLOCKED — design review and owner decisions pending.**

No implementation patch, runtime change, audit rewrite, canonical mutation, merge or deployment is authorized by this threat model. A reviewer must assess the threat coverage and exact design-base facts independently before implementation is proposed.
