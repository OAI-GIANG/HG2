# T-018 Local Spool Sync and Shared-Memory Boundary — Corrected Design V1

**Status:** DOCUMENTATION CORRECTION — DESIGN ONLY — NOT IMPLEMENTED
**Repository:** `OAI-GIANG/HG2`
**Source design reference:** `4d97c34d8bb7c1091265330aef63dd78d0e72c49`
**Canonical boundary:** `hg-genesis` is read-only for this task
**Release:** `BLOCKED`

## 1. MTC-1.0 task contract

- **OBJECTIVE:** align T-018 contract, threat model and acceptance criteria with the owner's decision to remove the signature feature.
- **SCOPE:** documentation-only correction on a separate branch; source/runtime code is unchanged.
- **INPUT:** existing T-018 contract, implementation design, threat model and inspected source facts.
- **OUTPUT:** corrected contract/design/threat model, explicit acceptance criteria, diff and SHA-256 manifest.
- **ACCEPTANCE:** no signature requirement remains as a gate; no substitute authentication mechanism is introduced; replay/idempotency, rollback, atomicity and runtime integration remain visible gates; owner decisions are not silently resolved; canonical branch, merge and deployment remain untouched.
- **EVIDENCE:** exact source and branch refs, diff checks, targeted test results, document hashes and final branch head.
- **RISKS:** an unkeyed hash is not sender authentication; replay/rollback; partial writes; split-brain; unintended disclosure; unresolved memory conflicts.
- **STOP CONDITION:** do not implement runtime changes while the initial cursor policy, memory semantics or storage boundary remains undecided.
- **NEXT ACTION:** independent review of the corrected documents and explicit owner decisions for unresolved gates.

## 2. Observed implementation boundary

The original read-only inspection was tied to design-base commit `4d97c34d8bb7c1091265330aef63dd78d0e72c49`. The following source facts were recorded there and must be reverified before any implementation claim:

| File | Recorded blob SHA | Recorded fact |
|---|---|---|
| `hg/phone_runtime.py` | `75fa6bcda1e29bf08aeb5341dbe8f0e124684199` | Instantiates `StateStore`; does not import or instantiate `SyncContext`; no sync API is exposed. |
| `hg/sync.py` | `f5c706348de6b2364fe2286a4121594d08e74a22` | Spool-based V2; checks unkeyed hashes/in-batch continuity; stores foreign payloads as `sync.received`; no application-state merge. |
| `hg/history.py` | `acb466e8a4c2b8882db58b783028b59804ecc812` | JSONL history plus JSON projections/checkpoints; no proven multi-record transaction boundary. |
| `hg/authority.py` | `a9fb1ddae181944e2e87decb806368e916ac6379` | Existing allowlist does not authorize `state.import`; do not bypass that rule. |
| `contract/ARCHITECTURE_V1.md` | `7defc59985b2ea291b614a63de0a3152b64d064d` | Phone is sole canonical state owner; relay/DR must not become a second primary. |

These facts describe the recorded design-base inspection, not a live deployment or independent reinspection by this review.

The source hash checks are consistency checks. They do not establish authorship. The signature feature and its supporting key-management design are removed from this task's acceptance scope; this does not authorize a replacement authentication design.

## 3. Fixed scope

- Local, same-device/same-user file-spool exchange only.
- Preserve existing host-provided credential handling and `context_id` / `runtime_id` boundary.
- No new network endpoint, cross-device protocol, signature, signed checkpoint, peer key registry, or signature key lifecycle.
- No substitute authentication mechanism is selected or introduced.
- The phone remains the single canonical state owner.
- No source/runtime implementation change is part of this documentation correction.

## 4. Required behavioral properties

### 4.1 Integrity and batch preflight

Validate schema and required fields; recompute payload and origin hashes using the existing canonical serializer; verify envelope-to-origin-record consistency; enforce one origin per batch and in-batch sequence/predecessor continuity. Preflight the complete batch before applying any foreign event. State explicitly that unkeyed hashes cannot establish sender identity.

### 4.2 Idempotency and replay

Persist enough accepted-event identity/provenance to distinguish an exact duplicate from an event-ID conflict. Exact duplicates must not cause duplicate effects. Reusing an event ID with different content/provenance must fail closed. Replay checks must survive process restart and must not rely solely on wall-clock timestamps.

### 4.3 Rollback and initial cursor

Reject sequence/head rollback and chain divergence relative to a previously accepted durable cursor. The policy for establishing the first cursor/checkpoint is **NEEDS_OWNER_DECISION**. Do not treat an untrusted first batch as a trusted checkpoint, and do not invent a new trust ceremony in this design. Until the decision is recorded, first-time origin import remains blocked.

### 4.4 Atomic apply and storage boundary

The desired acceptance property is all-or-none behavior across accepted event records, deduplication state, origin cursor and any commit receipt. Current sequential file writes do not prove this property. A storage migration or journal design is **not selected**. Evaluate options and fault-injection evidence, then obtain owner approval before implementation. Do not claim transactional atomicity based only on preflight validation or atomic replacement of a spool file.

### 4.5 Memory integration and conflicts

Current `sync.received` records retain foreign payload and provenance; they do not implement shared-memory merge. Memory schema, permitted data classes, retention, deletion/tombstones and conflict resolution remain **NEEDS_OWNER_DECISION**. Default behavior for unresolved application-state conflicts is quarantine/no mutation. Do not choose overwrite, last-write-wins, merge winner, or a memory model in this document correction.

### 4.6 Runtime and authority

Integrate only through the existing canonical phone runtime and a single state owner. Do not instantiate another `StateStore` over the same canonical directory. Do not bypass the existing `state.import` authorization denial. Runtime integration requires a separately reviewed authorization contract and explicit evidence.

## 5. Failure and recovery requirements

The eventual implementation test plan must include:

- exact duplicate import and repeated replay across restart;
- same event ID with changed payload/provenance;
- sequence gap, fork, predecessor mismatch and rollback below the persisted cursor;
- first-origin import while the initial cursor policy is unresolved;
- malformed, truncated and unsupported-schema batches;
- failure injected between every persistence step;
- process restart and offline recovery;
- concurrent duplicate imports;
- verification that a rejected batch causes no foreign payload application;
- verification that no second canonical state owner is created.

These are requirements for later implementation evidence, not claims that these scenarios have already passed.

## 6. Decisions and gates

| Decision / gate | Status | Rule |
|---|---|---|
| Signature feature and signature-specific acceptance gates | OBSOLETE | Remove from scope; do not substitute another authentication scheme. |
| Existing host credential and context/runtime identifiers | REQUIRED | Preserve; do not silently redesign. |
| Idempotency and durable replay detection | REQUIRED | Must be tested across restart. |
| Rollback against accepted cursor | REQUIRED | Initial cursor policy remains unresolved. |
| Initial cursor/checkpoint trust policy | NEEDS_OWNER_DECISION | Block first-origin acceptance until resolved. |
| Atomic apply boundary | REQUIRED | Evidence required; implementation/storage choice not selected. |
| Shared-memory model and conflict policy | NEEDS_OWNER_DECISION | No automatic merge/overwrite. |
| Storage migration (including SQLite) | NEEDS_OWNER_DECISION | No migration is authorized by this design. |
| Phone-runtime integration | REQUIRED | Exact-SHA integration evidence required. |
| Network/cross-device sync | OBSOLETE for current scope | Local spool only. |
| Independent review and provenance | REQUIRED | Release remains blocked until complete. |

## 7. Non-goals

This correction does not implement sync, select a cryptographic or non-cryptographic replacement for signatures, establish sender authenticity against arbitrary spool-file tampering, choose a memory conflict policy, select a storage backend, alter the canonical branch, merge, or deploy.

## 8. Review decision

**Current decision: DOCUMENTS CORRECTED; IMPLEMENTATION BLOCKED.**

The corrected documents must be checked for internal consistency and hashed. Existing tests may be run to detect regressions, but passing unit tests cannot establish runtime integration, a trusted initial cursor, atomic persistence or independent review.
