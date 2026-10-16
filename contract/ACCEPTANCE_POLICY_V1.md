# HG2 Acceptance Policy V1

Status: ACTIVE FOR THE FULL-PRODUCT-UNIFICATION CANDIDATE.

## Acceptance basis

Acceptance is determined by the applicable technical evidence listed below. A hash is used for artifact integrity and provenance comparison; it must not be represented as proof of identity or authorization.

## Provenance binding

Apply `contract/PROVENANCE_CONTRACT_V1.md` to candidate snapshots, manifests, test-run records, artifacts, and process-local module identity. Local records are `LOCAL_UNATTESTED` until the exact candidate/run is corroborated by an authenticated external builder/attestor. Disk hashes do not prove loaded-module identity; loaded-code fingerprints do not prove complete memory integrity or external attestation.

## Required technical evidence

1. Source and exact commit/tree provenance for candidate and live runtime.
2. Tests executed against the exact candidate, including clean checkout and relevant negative/fault-injection cases.
3. SHA-256 manifests and reproducible linkage to logs/results.
4. Data integrity and compatibility evidence, including backup and tested rollback before risky migration/deployment.
5. Runtime identity, state authority, authorization behavior and end-to-end checks appropriate to the capability.
6. Explicit classification of unverified or blocked technical requirements.

## Change/deployment safety

Do not modify canonical or deploy over a live runtime until source provenance, data inventory, a recoverable backup, and rollback steps have been verified. This is a technical safety gate.

## Closure

Close only when the applicable technical acceptance gates above have passing evidence.
