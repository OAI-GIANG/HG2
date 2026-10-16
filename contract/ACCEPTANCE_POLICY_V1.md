# HG2 Acceptance Policy V1

Status: ACTIVE FOR THE FULL-PRODUCT-UNIFICATION CANDIDATE.

## Acceptance basis

Acceptance is determined by the applicable technical evidence listed below. A hash is used for artifact integrity and provenance comparison; it must not be represented as proof of identity or authorization.

## Source and runtime identity

Use exact commit/tree identifiers, SHA-256 manifests, test-run records, and process-local module identity as evidence appropriate to the claim. A disk hash proves byte consistency only; it does not by itself prove sender identity, authorization, or loaded-module identity. Loaded-code fingerprints are diagnostic and do not prove complete memory integrity.

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

Close only when applicable, in-scope technical acceptance criteria have passing evidence. Authentication and authorization required by a product capability remain required and must be tested using the selected mechanism.
