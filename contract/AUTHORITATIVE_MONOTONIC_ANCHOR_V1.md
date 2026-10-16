# HG2 Authoritative Monotonic Anchor Contract V1

**Status:** Design contract; production implementation not present.
**Applies to:** HG2 candidate only. The canonical branch and frozen baseline remain unchanged.

## Purpose

Prevent event replay, sequence regression, conflicting origin histories, and stale cursor restoration when sync is enabled. A local file or SQLite database on the phone is durable state, not an independent anti-rollback authority. VPS2 remains disaster-recovery only and is not a runtime dependency.

## Required authority state

For each authorized receiver, peer, key identifier, and epoch, the authority stores the current sequence and chain hash, authority generation, last request identifier and result, prior transition digest, audit reference, and key status/revocation version. The initial checkpoint must be provisioned independently of the incoming batch.

## Compare-and-advance

The only state-changing operation is an atomic compare-and-advance request. The expected state must exactly equal the current authority state. The proposed state must be a validated descendant with no sequence or epoch regression. Request identifiers are idempotent: repeating the same request returns the same result; reusing an identifier for different content is rejected. Concurrent stale proposals fail with `ANCHOR_CONFLICT`.

The authority returns a verifiable receipt binding receiver, peer, key identifier, epoch, prior and proposed states, request identifier, nonce, authority identity, and audit reference. The receipt is checked using the configured authenticated channel and key-management mechanism. If a request times out after possibly committing, the client queries by the original request identifier and reconciles that result rather than submitting a different proposal.

## Authority rollback protection

A restorable remote database alone is not sufficient. Production use requires an independently protected monotonic witness or append-only log with consistency proofs and an independent verification path. Restoring an older authority backup must be detected and must deny sync. If witness state or consistency cannot be verified, sync is denied.

## Import and crash recovery

1. Validate the provisioned peer/key, batch authentication tag, full chain, sequence, and previous hash.
2. Validate the complete batch before writes.
3. Import event envelopes idempotently and durably before advancing the authority cursor.
4. Compare-and-advance the authority state and verify the returned receipt.
5. Persist the local cursor only after receipt/state verification.
6. On restart, reconcile a local cursor behind the authority. A cursor ahead of the authority, same sequence with a different hash, or invalid receipt is denied.
7. Deduplicate by origin context and event ID; reject conflicting duplicates.

## Peer identity and key provisioning

Each peer needs a stable identifier, key identifier/fingerprint, authorized role, trust source, authorization version, fresh nonces, and a transcript binding both identities and the selected protocol parameters. Key agreement or pre-shared-key provisioning must be explicit, resist peer substitution and replay, and define rotation, expiry, revocation, and re-enrollment. Test doubles do not prove production key provisioning.

## Required production tests

- Valid and invalid peer/key, revoked key, and malformed authentication tag.
- Exact duplicate, conflicting duplicate, replay, sequence gap, and fork.
- Concurrent compare-and-advance with exactly one conflicting proposal accepted.
- Crash before import, during import, after import, after authority advance, and before local cursor persistence.
- Restore of an old phone backup and an old authority backup.
- Backup/restore consistency across data, cursor, and authority state.
- Exact source/runtime correspondence for the capability under test.

## Current decision

The candidate has no production authority adapter, independent rollback witness, provisioned real peer, or production end-to-end fault/recovery/restore evidence. Authenticated sync therefore remains disabled until those technical requirements are implemented and tested. These requirements are about the sync capability itself.
