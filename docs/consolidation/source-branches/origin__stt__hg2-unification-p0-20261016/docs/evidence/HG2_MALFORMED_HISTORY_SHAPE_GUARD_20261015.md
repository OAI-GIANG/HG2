# HG2 malformed history and checkpoint guard — 2026-10-15

## Scope and baseline

Clean-room remediation on the isolated branch `stt/cleanroom-gap-closure-20261015`, based on canonical `hg-genesis` commit `cdebaeed014371f033f14352f552c6d0d4e69198` and tree `fa986a20e8c5c091f930f66a653f4a41611c76b2`. No candidate branch was cherry-picked. No canonical mutation, merge, or deployment is authorized.

## Findings reproduced

On Android/ARM64 Termux with Python 3.14.6, tests reproduced acceptance of structurally incomplete records when the record hash and checkpoint were recalculated, blank history lines, and a final record without a newline. Invalid UTF-8 raised `UnicodeDecodeError`. Non-object checkpoint JSON could cause an attribute error when `.get()` was used.

## Schema derived from the canonical emitter

`StateStore.emit()` writes `seq`, `event_id`, `event_type`, `recorded_at`, `correlation_id`, `causation_id`, `product_id`, `runtime_id`, `schema`, `payload`, `prev_hash`, and `record_hash`. The validator now requires these keys; validates non-empty IDs/event type, integer sequence excluding booleans, finite floating-point timestamps, nullable/string causation IDs, HG product/schema identity, object payload, hash-field types, and runtime identity. The hash chain and sequence checks remain in place. Unknown additional fields are not categorically rejected, preserving room for hashed extension fields.

## Remediation

- One shared record-shape validator is used by loading and verification.
- Malformed lines, blank lines, and incomplete final lines fail closed.
- Invalid UTF-8 in history is reported as `history_unreadable`; initialization raises `HistoryError`.
- Checkpoint JSON must decode to an object matching the exact expected sequence/hash pair.
- Added regression tests for missing fields, invalid field values even after hash recomputation, blank lines, missing final newline, invalid UTF-8, non-object checkpoint JSON, and valid history restart compatibility.

## PR overlap analysis

- PR #4 (`fix/history-integrity-v2`) addresses missing/corrupt artifacts, checkpoint/projection integrity and overlaps with some record-shape cases. Its declared base is `d11e71ed8b34338b8568664b39bc777c926826d5`, not the current canonical SHA.
- PR #11 (`stt-p0-integration-20261013`) addresses stricter history validation and test-resource cleanup on canonical base `cdebaeed014371f033f14352f552c6d0d4e69198`; it overlaps with blank-line, interrupted-line, identity and structure checks. Its code was not copied into this remediation.
- This patch is limited to malformed record shape/line handling and non-object checkpoint handling; it does not claim to close the broader artifact/projection, resource cleanup, production E2E, or provenance gates.

## Verification

- Focused malformed-history tests: 10 tests passed with `ResourceWarning` treated as an error.
- Full Termux suite: 33 tests passed, exit code 0.
- Full-suite warnings: 48 `ResourceWarning` lines remain; not claimed fixed here.
- Python compile check and `git diff --check`: passed.
- Compatibility test: canonical genesis and a `session.created` event verify and replay after restart.

This is implementation and test evidence only; it is not release certification or CLOSED_VERIFIED status. Under contract/ACCEPTANCE_POLICY_V1.md, independent review and signatures are not acceptance gates. Candidate acceptance depends on exact-source tests, provenance, data integrity, backup/rollback and runtime evidence.
