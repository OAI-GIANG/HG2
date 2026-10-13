# T-018 Acceptance Criteria V2 — Signature-Free Local Spool Scope

**Status:** Proposed acceptance boundary; implementation remains BLOCKED.
**Applies to:** local, same-device/same-user file-spool exchange only.

## Classification

| Criterion | Classification | Acceptance rule |
|---|---|---|
| Digital signatures, signed envelopes and signed checkpoints | OBSOLETE | Must not be required to pass T-018. |
| Signature-specific peer/key registry and key lifecycle | OBSOLETE | Remove from scope; do not replace with another authentication mechanism. |
| Existing host-provided credential handling | REQUIRED | Preserve without redesign in this scope correction. |
| `context_id` and `runtime_id` | REQUIRED | Preserve existing context/runtime boundary. |
| Schema, source-record consistency and payload hash checks | REQUIRED | Invalid input fails closed. Hashes are not described as sender authentication. |
| Full-batch preflight | REQUIRED | Invalid later event must not result in earlier foreign payload application. |
| Idempotency and changed-content event-ID conflict detection | REQUIRED | Exact duplicate has no second effect; conflicting reuse is rejected. |
| Replay protection across restart | REQUIRED | Persisted accepted-event/cursor state is exercised by tests. |
| Rollback/fork checks against an accepted cursor | REQUIRED | Lower sequence, conflicting head and predecessor divergence fail closed. |
| Initial origin cursor/checkpoint policy | NEEDS_OWNER_DECISION | First-origin acceptance stays blocked until an explicit decision exists. |
| All-or-none persistence of event, dedupe, cursor and receipt | REQUIRED | Must be proven by fault injection; preflight alone is insufficient. |
| Storage backend or migration choice | NEEDS_OWNER_DECISION | SQLite or journal is not selected by this document. |
| Shared-memory schema, sharing, retention and conflict semantics | NEEDS_OWNER_DECISION | No automatic merge or overwrite until approved. |
| Phone-runtime integration through single canonical state owner | REQUIRED | Exact-commit integration evidence must show no second canonical store. |
| New network endpoint or cross-device sync | OBSOLETE for current scope | T-018 remains local spool only. |
| Exact-commit test evidence and SHA-256 manifest | REQUIRED | Hashes must recompute from the committed artifacts. |
| Independent review and provenance | REQUIRED | Release cannot be marked ready without it. |

## Test matrix

1. Valid batch passes schema, source-record and payload consistency checks.
2. Mutated payload, origin fields, hash, sequence or predecessor fails closed.
3. Exact duplicate is idempotent, including after process restart.
4. Reused event ID with changed content/provenance is rejected.
5. Sequence rollback, fork and gap are detected; first-origin import remains blocked while the initial cursor policy is unresolved.
6. Invalid batch does not apply any foreign event from that batch.
7. Injected persistence failure yields all-or-none behavior; if this cannot be proven, atomicity gate remains BLOCKED.
8. Existing authority denial is preserved; no unauthorized `state.import`.
9. Runtime integration does not create a second canonical state owner.
10. Tests and manifest identify the exact commit and environment.
11. A reviewer independent from the implementation author records findings on the exact candidate commit. A self-check or document consistency scan does not satisfy this gate.

## Stop conditions

Do not claim production readiness if initial cursor policy, memory semantics, storage boundary, runtime integration, atomicity proof, or independent review remains unresolved. Do not implement signature features or a replacement authentication scheme as part of this scope.
