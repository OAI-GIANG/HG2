# HG2 malformed history record-shape guard — 2026-10-15

## Scope

Clean-room change based directly on canonical `hg-genesis` commit
`cdebaeed014371f033f14352f552c6d0d4e69198` (tree
`fa986a20e8c5c091f930f66a653f4a41611c76b2`). No candidate branch was cherry-picked.

## Reproduced defect

On Android/ARM64 Termux with Python 3.14.6, `StateStore.verify()` and
`StateStore(...)` raised raw `AttributeError` for valid JSON values that were
not objects (`[]`, `null`, a JSON string, or a number). `verify()` should return
an explicit failed verification result, and initialization should fail closed
with `HistoryError` rather than leaking an implementation exception.

## Change

- Validate that each history line decodes to a JSON object.
- Require the record fields used by integrity verification and replay.
- Reject invalid types (including boolean `seq`, which Python otherwise treats
  as an integer) before hash/chain processing.
- Keep the verifier fail-closed with explicit line-scoped reason codes.
- Add four counter-test methods covering non-object values, missing fields,
  invalid field types, and initialization behavior.

This is deliberately separate from open PR #4's missing artifact/checkpoint and
state-projection checks, and PR #11's test-resource cleanup. No merge or deploy.

## Verification evidence

- Device: Android/ARM64, Termux; Python 3.14.6.
- Focused malformed-shape tests: 4/4 passed with `ResourceWarning` treated as an error.
- Full test suite: 27 tests passed, exit code 0.
- Full-suite warnings: 48 `ResourceWarning` lines from existing test helpers and
  HTTP error response cleanup; these remain visible and are not represented as
  resolved by this change.
- Python compile check: passed.
- `git diff --check`: passed.
- Canonical branch remains unchanged; no merge/deploy performed.

File SHA-256 values are recorded by the final Termux command output for the
implementation and counter-test files. This report is evidence of local tests,
not independent review or release certification.
