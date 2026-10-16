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
- Android's service list exposed a Keystore2 Binder service name, but this does not mean a Termux JVM has the Android application framework provider or permission to use it.
- Runtime PhoneRuntime.health() reports network_integration=false. Authenticated sync is opt-in and is not wired into the live entry point.
- KeyManagementInterface and CursorAnchorInterface are protocols. The repository's anchor and key-provider implementations in tests are in-memory test doubles, not production trust services.
- The current authenticated batch code imports idempotent event envelopes before advancing the anchor, then writes the local cursor after anchor advancement. This recovery ordering is only as trustworthy as the injected anchor implementation.

These facts do not prove that the device lacks hardware-backed KeyMint. They prove that this Termux process currently has no demonstrated Android Keystore integration and no verified hardware attestation.

## 2. Android Keystore / KeyMint boundary

Android Keystore is accessed through Android application APIs. A normal OpenJDK process inside Termux is not an Android app process and the AndroidKeyStore provider is not present in the tested JVM. Installing the Termux:API companion alone is not evidence that a Keystore/KeyMint API is exposed; the official Termux:API project describes a separate Android add-on and same-signing-key requirement.

A future Android bridge must be a minimal, auditable Android application component that:
1. generates an asymmetric signing key through AndroidKeyStore with explicit purposes and digests;
2. exports only the public key and certificate chain, never private key material;
3. requests a fresh server-provided attestation challenge;
4. returns the certificate chain and key characteristics;
5. has the chain verified off-device against trusted Android attestation roots and current revocation/status policy;
6. reports HARDWARE_BACKED_VERIFIED only when the verified attestation's security level and enforced authorizations meet policy. Software-only, missing, stale, malformed, or unverifiable attestation is BLOCKED.

**KeyMint rollback resistance is not a general monotonic counter.** Android's documented rollback-resistance property prevents a deleted rollback-resistant key from being restored and used again. It does not provide an arbitrary application-owned peer_id -> (sequence, hash) counter. A rollback-resistant signing key can sign stale cursor state if the state is stored in a rollbackable file; therefore it is not, by itself, an authoritative cursor anchor.

References:
- Android key attestation: https://source.android.com/docs/security/features/keystore/attestation
- KeyMint rollback resistance: https://source.android.google.cn/docs/security/features/keystore/implementer-ref?hl=en
- Termux API app boundary/signing: https://github.com/termux/termux-api

## 3. Threat model and authority boundary

Protect against:
- restoration of an older phone filesystem or SQLite backup;
- replay of previously accepted batches and reuse of sequence numbers with a different hash;
- crash between import, remote anchor advancement, and local cursor persistence;
- duplicated, reordered, forked, or concurrently submitted batches;
- stale or rolled-back anchor replicas;
- peer/key substitution, revoked keys, malformed signatures, and ambiguous timeouts;
- a CI artifact whose local hash is intact but whose source builder is not authenticated.

Out of scope unless separately designed: a fully compromised OS/kernel, a malicious authorized peer, compromise of the authoritative service's trust root, and compromise of the external attestation provider itself.

A file or SQLite database on the phone is durable local state only, never the independent anti-rollback authority. VPS2 remains disaster-recovery only and must not become a runtime dependency. If a remote authority is selected, its role, host, trust domain, signing identity, data durability and failure policy must be explicitly established; do not assume VPS1 or any existing endpoint is already an authority.

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
- same request id and identical bytes returns the original signed receipt;
- same request id with different bytes fails with ANCHOR_IDEMPOTENCY_CONFLICT;
- sequence regression, epoch regression, or same-sequence/different-hash is always denied.

The authority returns a signed receipt binding receiver, peer, key id, epoch, old state, proposed state, request id, challenge/nonce, authority identity and audit-log reference. The phone verifies the signature against a pinned authority identity and checks all fields before treating the update as accepted.

If a request times out after possibly committing, the client must query the authority by request id and reconcile the signed receipt. It must not blindly retry a different proposal. An unsigned HTTP success response is not evidence.

### 4.3 Anti-rollback of the authority itself

A remote service backed by a single restorable database is not automatically rollback-proof. Before production acceptance, authority state must be protected from restoration to an earlier snapshot by an independently protected monotonic witness or an append-only transparency log with consistency proofs and an independent verification path. Backups must be restore-tested against the witness; restoring an old backup must cause the service to fail closed rather than serve a stale high-water mark.

The witness must be independent of the phone's ordinary filesystem and not be merely another file or SQLite database under the same restore authority. If the independent witness cannot be reached or consistency cannot be verified, sync is denied.

### 4.4 Import/crash state machine

1. Validate the peer identity/key, signature, full batch chain, sequence and previous hash.
2. Preflight the complete batch before any write.
3. Append accepted event envelopes idempotently to the phone's canonical state; never advance the remote anchor before event import is durable.
4. Atomically compare-and-advance the authoritative anchor and obtain a signed receipt.
5. Persist the local cursor only after the signed receipt is verified.
6. On restart, read and verify the remote anchor; reconcile a local cursor that is behind. A local cursor ahead of the authority, same sequence with different hash, or missing/invalid receipt is denied.
7. Redelivery after partial import must deduplicate by (origin_context, event_id) and compare all provenance fields; a conflicting duplicate is a hard rejection.

The current interface does not yet provide a production signed-receipt type or an authoritative implementation. That interface gap must be closed before a real backend adapter is accepted.

## 5. Peer identity and key exchange

Before sync can be enabled, both endpoints must have an explicit identity binding:
- stable peer id, key id, public-key fingerprint and authorized role;
- trust source and authorization version;
- fresh nonces from both endpoints;
- a signed transcript binding protocol version, both identities, both nonces, ephemeral public keys and selected algorithms;
- authenticated ephemeral key agreement and HKDF-derived session keys, or an explicitly approved pre-shared-key provisioning process with independently verified fingerprints;
- replay cache, key expiry/rotation, revocation and re-enrollment behavior.

The current code uses an injected HMAC-SHA256 key and does not perform a real key exchange. It must not be described as mutual peer authentication until the real key provider and peer transcript are implemented and verified. No key may be generated or provisioned for an unidentified peer.

## 6. Required verification matrix

Every test below must run against the production adapter and authoritative backend, not only an in-memory test double:

| Test | Required evidence |
|---|---|
| Valid peer handshake | both peer identities, key fingerprints, nonce/transcript and key agreement verified |
| Valid batch | signed origin chain, authoritative receipt, exact state/cursor result |
| Wrong peer/key/revoked key | deny before event writes |
| Replay / duplicate | exact duplicate is idempotent; different content at same sequence is rejected |
| Concurrent compare-and-advance | exactly one conflicting proposal commits |
| Crash before first event | no cursor or anchor advancement |
| Crash mid-import | retry deduplicates committed event envelopes and completes once |
| Crash after import before anchor | retry advances anchor only after import is complete |
| Timeout after remote CAS | request-id query returns original signed receipt; no second transition |
| Crash after anchor before local cursor | restart verifies anchor and repairs local cursor |
| Restore old phone backup | stale local cursor cannot lower authority state; sync fails closed until repaired |
| Restore old authority backup | independent witness detects regression and denies service |
| Backup/restore | restored state, cursor and anchor agree; hashes and receipts verify |
| Provenance | signed attestation matches exact commit, candidate-manifest SHA-256, trusted builder identity, repository and ref |

## 7. Reason codes and acceptance policy

- HG2_TRUST_ANDROID_KEYSTORE_UNAVAILABLE_FROM_TERMUX_JVM
- HG2_TRUST_HARDWARE_ATTESTATION_UNVERIFIED
- HG2_TRUST_MONOTONIC_ANCHOR_NOT_IMPLEMENTED
- HG2_TRUST_AUTHORITY_ROLLBACK_WITNESS_MISSING
- HG2_TRUST_AUTHORITY_IDENTITY_UNVERIFIED
- HG2_TRUST_PEER_IDENTITY_NOT_PROVISIONED
- HG2_TRUST_KEY_EXCHANGE_NOT_VERIFIED
- HG2_TRUST_REAL_PEER_E2E_NOT_RUN
- HG2_TRUST_PRODUCTION_FAULT_RECOVERY_NOT_RUN
- HG2_TRUST_RESTORE_E2E_NOT_PROVEN
- HG2_TRUST_EXTERNAL_ATTESTATION_MISSING
- HG2_TRUST_EXTERNAL_ATTESTATION_INVALID
- HG2_TRUST_CANONICAL_OR_BASELINE_MISMATCH

PASS is allowed only when the exact candidate is attested by the expected builder, all production adapter tests pass against the authoritative backend, peer identity/key exchange is verified, crash/replay/rollback/restore evidence passes, and the canonical branch and frozen baseline are unchanged. No missing evidence can be downgraded to a warning.

## 8. Current decision

HG2_TRUST_ANDROID_KEYSTORE_UNAVAILABLE_FROM_TERMUX_JVM
HG2_TRUST_MONOTONIC_ANCHOR_NOT_IMPLEMENTED
HG2_TRUST_AUTHORITY_ROLLBACK_WITNESS_MISSING
HG2_TRUST_PEER_IDENTITY_NOT_PROVISIONED
HG2_TRUST_KEY_EXCHANGE_NOT_VERIFIED
HG2_TRUST_REAL_PEER_E2E_NOT_RUN
HG2_TRUST_PRODUCTION_FAULT_RECOVERY_NOT_RUN
HG2_TRUST_RESTORE_E2E_NOT_PROVEN
HG2_TRUST_EXTERNAL_ATTESTATION_PENDING

Overall: BLOCKED_TECHNICAL_ACCEPTANCE.

Do not merge to hg-genesis, enable authenticated sync, or change the frozen baseline while any listed production gate remains open.
