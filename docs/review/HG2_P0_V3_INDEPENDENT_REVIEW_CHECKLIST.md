# HG2 P0 V3 — Independent Review Checklist

Scope: review the proposed changes in PR #1 and PR #2 without merging or deploying. The reviewer must be a real person independent of the author of the changes. The author must not submit or simulate the independent approval.

## Reviewer identity and provenance
- [ ] Record GitHub username and confirm the person is not the author of the changes being reviewed.
- [ ] Record PR URL, base SHA, head SHA, review timestamp, and review outcome.
- [ ] Review the exact current head SHA; repeat review if the head changes materially.
- [ ] Submit review through GitHub using the reviewer's own account; do not share credentials.

## PR #1 — Integrity fail-closed behavior
- [ ] Verify missing head/checkpoint/projection/history fail closed and do not silently recreate trusted state.
- [ ] Verify history replay is compared against checkpoint and state projection.
- [ ] Verify malformed/non-object records, invalid sequence values, and empty event types are rejected.
- [ ] Review adversarial tests for tampering, truncation, reordering, duplication, rollback, and interrupted append.
- [ ] Check for unintended behavior changes, compatibility risks, exception leakage, and filesystem race/partial-write risks.
- [ ] Confirm tests cover both expected failure and successful recovery/normal operation.

## PR #2 — Test resource lifecycle
- [ ] Confirm opened test files are closed deterministically, including exceptional paths.
- [ ] Confirm HTTPError response bodies are consumed/closed without masking the original assertion.
- [ ] Run `PYTHONDONTWRITEBYTECODE=1 python -W default -m unittest discover -s tests -v`.
- [ ] Confirm all tests pass and no `ResourceWarning` appears.
- [ ] Confirm the change is test-only and does not alter production/runtime behavior.

## Acceptance and disposition
- [ ] Review comments and requested changes are resolved or explicitly accepted by the reviewer.
- [ ] CI result is tied to the exact head commit and is successful; local test logs alone are not CI.
- [ ] Any CI waiver is documented by an authorized decision-maker and is permitted by the project's acceptance policy.
- [ ] Do not approve based solely on the author's evidence summary; independently inspect the diff and relevant tests.
- [ ] Do not merge or deploy as part of this review task.

Record outcome: `APPROVED` / `CHANGES_REQUESTED` / `COMMENTED` / `BLOCKED`.
