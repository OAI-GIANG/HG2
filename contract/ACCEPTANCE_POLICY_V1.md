# HG2 Acceptance Policy V1

Status: ACTIVE FOR THE FULL-PRODUCT-UNIFICATION CANDIDATE.

## Explicit exclusions

- Independent review is not a required acceptance gate.
- Commit signatures, reviewer signatures, signed attestations, and signature-based approval are not required acceptance gates.
- Absence of an independent reviewer or signature must not block a candidate or product acceptance.
- A hash is used for artifact integrity and provenance comparison; it must not be represented as proof of identity or authorization.

## Required technical evidence

1. Source and exact commit/tree provenance for candidate and live runtime.
2. Tests executed against the exact candidate, including clean checkout and relevant negative/fault-injection cases.
3. SHA-256 manifests and reproducible linkage to logs/results.
4. Data integrity and compatibility evidence, including backup and tested rollback before risky migration/deployment.
5. Runtime identity, state authority, authorization behavior and end-to-end checks appropriate to the capability.
6. Explicit classification of unverified or blocked technical requirements.

## Change/deployment safety

Do not modify canonical or deploy over a live runtime until source provenance, data inventory, a recoverable backup, and rollback steps have been verified. This is a technical safety gate, not a review or signature gate.

## Closure

Close only when the applicable technical acceptance gates above have passing evidence. Do not introduce reviewer identity, independent-review or signature requirements.
