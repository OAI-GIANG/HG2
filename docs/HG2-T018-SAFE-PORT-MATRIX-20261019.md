# T-018 Safe Port Audit — 2026-10-19

## Provenance and variant identity

- `design/t018-auth-checkpoint-memory-20261013` `hg/sync.py` SHA-256 `56f53b78754ff2999d5662d0ddb61246e90ac3aedd767a60f03f53b4c486ac82`, 12807 bytes, identical to common variant: `True`.
- `docs/t018-remove-signature-scope-20261013` `hg/sync.py` SHA-256 `56f53b78754ff2999d5662d0ddb61246e90ac3aedd767a60f03f53b4c486ac82`, 12807 bytes, identical to common variant: `True`.
- `feat/hg-t018-cross-context-sync-20261013` `hg/sync.py` SHA-256 `56f53b78754ff2999d5662d0ddb61246e90ac3aedd767a60f03f53b4c486ac82`, 12807 bytes, identical to common variant: `True`.
- `remediation/t018-base-reconcile-20261013` `hg/sync.py` SHA-256 `56f53b78754ff2999d5662d0ddb61246e90ac3aedd767a60f03f53b4c486ac82`, 12807 bytes, identical to common variant: `True`.
- `review/t018-design-pre-review-20261013` `hg/sync.py` SHA-256 `56f53b78754ff2999d5662d0ddb61246e90ac3aedd767a60f03f53b4c486ac82`, 12807 bytes, identical to common variant: `True`.

## API / behavior matrix

| Area | T-018 source references | Current target references | Finding |
|---|---|---|
| API/state ownership | hg/sync.py:41–89 | hg/sync.py:16–22 | INCOMPATIBLE AS DROP-IN; do not add SyncContext as a parallel state authority |
| Authentication/authority | docs/T-018-SYNC-V2-CONTRACT.md:11–25 | hg/sync.py:24–29, 47–52, 61–73 | Different trust model and transport scope; preserve both as distinct contracts, do not claim T018 auth equivalence |
| Checkpoint/cursor | hg/sync.py:128–186 | hg/sync.py:31–45 and 89–108 | T018 lacks authenticated durable initial cursor policy; not safe to port import path without design decision |
| Spool/atomic publication | hg/sync.py:73–84 | hg/sync.py:47–117 | Different transport adapter; can be added only as SyncTransport adapter over existing dispatcher if it obeys current ACK and transaction contract |
| Idempotency/replay | hg/sync.py:93–191 | hg/sync.py:89–117; hg/sqlite_state.py (outbox methods) | Import-side dedup/replay protection is a missing capability, but must be modeled in canonical SQLite store first |
| Reject/quarantine/audit | hg/sync.py:217–222 | hg/sync.py:75–88, 103–109 | Quarantine/reporting can be adapter concern, but audit events must use canonical store and raw batch privacy controls |
| Recovery/transaction atomicity | docs/T-018-SYNC-V2-CONTRACT.md:33–51 | hg/sync.py:61–110; hg/sqlite_state.py (transactional outbox) | Keep SQLite transaction authority; T018 import loop is unsafe to port as-is |
| Runtime integration | docs/T-018-SYNC-V2-CONTRACT.md:48 | hg/phone_runtime.py (must inspect exact runtime call sites at final implementation) | Not production/runtime-integrated |

## Decision

Do not port legacy SyncContext wholesale. Its foreign-event import, durable cursor policy and all-or-none multi-event transaction are unresolved and its separate StateStore would violate single canonical state ownership. Safe next slice is adapter design that uses SyncDispatcher/SQLiteStateStore as the only authority; requires an explicit transport contract and import-side SQLite schema before runtime implementation.

Source branches remain untouched. This matrix records source code locations and a safe-port decision; it does not claim T-018 is production-ready.
