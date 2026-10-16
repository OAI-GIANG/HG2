# HG2 Authoritative Monotonic Anchor Contract V1

**Status:** DESIGN CONTRACT / PRODUCTION GATE BLOCKED
**Applies to:** OAI-GIANG/HG2 candidate branch only
**Canonical branch:** hg-genesis remains unchanged
**Rule:** absence, mismatch, timeout, unverifiable evidence, or untrusted authority means DENY.

## 1. Verified environment facts

The inspected phone reports Android 16 / SDK 36 / ARM64 and Termux CPython 3.14.6. The following capability probes were non-mutating:

- termux-keystore is absent from PATH.
- The Termux API companion app is not installed; only com.termux and com.termux.boot were listed.
- A Java 21 process in Termux failed KeyStore.getInstance("AndroidKeyStore") with java.security.KeyStoreException: AndroidKeyStore not found.
- adb devices -l reported no connected device/emulator; an ADB shell could not be used to invoke Keystore2.
- Android's service list exposed a Keystore2 Binder service name, but this does not mean a Termux JVM has the Android application framework provider or permission to use it. This is an environment observation, not an acceptance gate.
- Runtime PhoneRuntime.health() reports network_integration=false. Authenticated sync is opt-in and is not wired into the live entry point.
- KeyManagementInterface and CursorAnchorInterface are protocols. The repository's anchor and key-provider implementations in tests are in-memory test doubles, not production trust services.
- The current authenticated batch code imports idempotent event envelopes before advancing the anchor, then writes the local cursor after anchor advancement. This recovery ordering is only as trustworthy as the injected anchor implementation.

The Keystore/KeyMint probe is retained as an environment note only. Android Keystore availability, hardware-backed keys, and hardware attestation are not HG2 product acceptance requirements and must not appear as blockers. The sync authentication mechanism is selected and evaluated by peer identity, key provisioning, replay resistance, and the in-scope threat model; it need not use digital signatures.

## 3. Threat model and authority boundary

Protect against:
- restoration of an older phone filesystem or SQLite backup;
- replay of previously accepted batches and reuse of sequence numbers with a different hash;
- crash between import, remote anchor advancement, and local cursor persistence;
- duplicated, reordered, forked, or concurrently submitted batches;
- stale or rolled-back anchor replicas;
- peer/key substitution, revoked keys, malformed authentication tags, and ambiguous timeouts;
- source/runtime mismatch and unauthorized peer/key substitution.

Out of scope unless separately designed: a fully compromised OS/kernel, a malicious authorized peer, or compromise of the authoritative service's trust root.

A file or SQLite database on the phone is durable local state only, never the independent anti-rollback authority. VPS2 remains disaster-recovery only and must not become a runtime dependency. If a remote authority is selected, its role, host, trust domain, authenticated authority identity, data durability and failure policy must be explicitly established; do not assume VPS1 or any existing endpoint is already an authority.

## 4. Required authoritative anchor protocol

### 4.1 State

For each authorized tuple (receiver_id, peer_id, key_id, anchor_epoch), the authority stores:
- current monotonic seq;
- current origin-chain hash;
- authority epoch / generation;
- last accepted request id and its resulting receipt digest;
- previous transition digest and append-only audit reference;
- peer-key status and revocation version.

The trust policy and initial checkpoint must be provisioned independently of the batch being accepted. An incoming peer cannot choose its own initial checkpoint.

### 4.2 Compare-and-advance

The only state-changing operation is an atomic compare-and-advance request:
- request_id is globally unique and idempotent;
- expected = (epoch, seq, hash) must exactly equal current authoritative state;
- proposed = (epoch, seq + N, final_hash) must be a validated descendant of expected;
- concurrent/stale updates fail with ANCHOR_CONFLICT;
- same request id and identical bytes returns the original authenticated receipt;
- same request id with different bytes fails with ANCHOR_IDEMPOTENCY_CONFLICT;
- sequence regression, epoch regression, or same-sequence/different-hash is always denied.

The authority returns an authenticated receipt binding receiver, peer, key id, epoch, old state, proposed state, request id, challenge/nonce, authority identity and audit-log reference. The receipt must be verifiable using the selected authenticated channel or approved MAC/key-management mechanism; this contract does not require a digital signature.

If a request times out after possibly committing, the client must query the authority by request id and reconcile the original receipt. It must not blindly retry a different proposal. An unauthenticated HTTP success response is not evidence.

### 4.3 Anti-rollback of the authority itself

A remote service backed by a single restorable database is not automatically rollback-proof. Before production acceptance, authority state must be protected from restoration to an earlier snapshot by an independently protected monotonic witness or an append-only transparency log with consistency proofs and an independent verification path. Backups must be restore-tested against the witness; restoring an old backup must cause the service to fail closed rather than serve a stale high-water mark.

The witness must be independent of the phone's ordinary filesystem and not be merely another file or SQLite database under the same restore authority. If the independent witness cannot be reached or consistency cannot be verified, sync is denied.

### 4.4 Import/crash state machine

1. Validate the provisioned peer identity/key, batch authentication tag, full batch chain, sequence and previous hash.
2. Preflight the complete batch before any write.
3. Append accepted event envelopes idempotently to the phone's canonical state; never advance the remote anchor before event import is durable.
4. Atomically compare-and-advance the authoritative anchor and obtain an authenticated receipt.
5. Persist the local cursor only after the receipt and its bound state are verified.
6. On restart, read and verify the remote anchor; reconcile a local cursor that is behind. A local cursor ahead of the authority, same sequence with different hash, or missing/invalid receipt is denied.
7. Redelivery after partial import must deduplicate by (origin_context, event_id) and compare all provenance fields; a conflicting duplicate is a hard rejection.

The current interface does not yet provide a production authenticated-receipt type or an authoritative implementation. That interface gap must be closed before a real backend adapter is accepted. Digital signatures and external attestation are not required for acceptance.

## 5. Peer identity and key exchange

Before sync can be enabled, both endpoints must have an explicit identity binding:
- stable peer id, key id, public-key fingerprint or pre-shared-key identifier and authorized role;
- trust source and authorization version;
- fresh nonces from both endpoints;
- an authenticated transcript binding protocol version, both identities, fresh nonces, selected algorithms, and key identifiers;
- either authenticated key agreement, or an explicitly approved pre-shared-key provisioning process with verified fingerprints; the chosen mechanism must resist peer substitution and replay without introducing a digital-signature gate;
- replay cache, key expiry/rotation, revocation and re-enrollment behavior.

The current code uses an injected HMAC-SHA256 key, but the provider used by tests is not a production provisioning service. Do not describe the deployed system as mutually authenticated until the real peer identity binding, key provisioning, and authenticated transcript are implemented and verified. No key may be generated or provisioned for an unidentified peer. Digital signatures are not required.

## 6. Required verification matrix

Every test below must run against the production adapter and authoritative backend, not only an in-memory test double:

| Test | Required evidence |
|---|---|
| Valid peer handshake | both peer identities, key fingerprints, nonce/transcript and selected key-authentication mechanism verified |
| Valid batch | authenticated origin chain, authenticated authority receipt, exact state/cursor result |
| Wrong peer/key/revoked key | deny before event writes |
| Replay / duplicate | exact duplicate is idempotent; different content at same sequence is rejected |
| Concurrent compare-and-advance | exactly one conflicting proposal commits |
| Crash before first event | no cursor or anchor advancement |
| Crash mid-import | retry deduplicates committed event envelopes and completes once |
| Crash after import before anchor | retry advances anchor only after import is complete |
| Timeout after remote CAS | request-id query returns original authenticated receipt; no second transition |
| Crash after anchor before local cursor | restart verifies anchor and repairs local cursor |
| Restore old phone backup | stale local cursor cannot lower authority state; sync fails closed until repaired |
| Restore old authority backup | independent witness detects regression and denies service |
| Backup/restore | restored state, cursor and anchor agree; hashes and receipts verify |
| Source/runtime identity | exact candidate revision and tested runtime/source correspondence are recorded; hashes are integrity evidence, not identity proof by themselves |

## 7. Reason codes and acceptance policy

- HG2_TRUST_MONOTONIC_ANCHOR_NOT_IMPLEMENTED
- HG2_TRUST_AUTHORITY_ROLLBACK_WITNESS_MISSING
- HG2_TRUST_AUTHORITY_IDENTITY_UNVERIFIED
- HG2_TRUST_PEER_IDENTITY_NOT_PROVISIONED
- HG2_TRUST_PEER_AUTHENTICATION_NOT_VERIFIED
- HG2_TRUST_REAL_PEER_E2E_NOT_RUN
- HG2_TRUST_PRODUCTION_FAULT_RECOVERY_NOT_RUN
- HG2_TRUST_RESTORE_E2E_NOT_PROVEN
- HG2_TRUST_CANONICAL_OR_BASELINE_MISMATCH

PASS is allowed only when all in-scope production adapter tests pass against the configured authoritative backend, peer identity and the selected authentication/key-provisioning mechanism are verified, crash/replay/rollback/restore evidence passes, and the canonical branch and frozen baseline are unchanged. Digital signatures, external attestations, and independent review are not acceptance gates. Missing evidence for an in-scope technical requirement remains a blocker.

## 8. Current decision

HG2_TRUST_MONOTONIC_ANCHOR_NOT_IMPLEMENTED
HG2_TRUST_AUTHORITY_ROLLBACK_WITNESS_MISSING
HG2_TRUST_PEER_IDENTITY_NOT_PROVISIONED
HG2_TRUST_PEER_AUTHENTICATION_NOT_VERIFIED
HG2_TRUST_REAL_PEER_E2E_NOT_RUN
HG2_TRUST_PRODUCTION_FAULT_RECOVERY_NOT_RUN
HG2_TRUST_RESTORE_E2E_NOT_PROVEN

Overall: BLOCKED_TECHNICAL_ACCEPTANCE.

Do not merge to hg-genesis, enable authenticated sync, or change the frozen baseline while any applicable production technical gate remains open. Do not reinstate signature, external-attestation, or independent-review gates.
