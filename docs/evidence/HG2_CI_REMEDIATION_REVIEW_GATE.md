> **T-018 policy correction (2026-10-14):** This file is retained as historical evidence for the earlier PR #14 CI/config incident, not as an active acceptance gate. Independent review, independent reviewer, independent security review, independent approval, and equivalent gates are excluded from HG2 acceptance. No substitute gate is created. Do not use the historical review-related statements below as current blockers; apply the corrected PR #15 acceptance report instead.

# HG2 Code Intelligence — Coverage Fail-Closed Remediation

## Scope
Isolated remediation for the bounded, read-only code intelligence candidate. No canonical baseline, manifest, phone-runtime, identity, history, or edge changes are included.

- Subject commit: `ce10fb4533921c79bd7c0e1479119792094c5a95`
- Branch: `fix/hg2-code-intelligence-coverage-failclosed-20261014`
- Canonical baseline reference recorded for this task: `d11e71ed8b34338b8568664b39bc777c926826d5` (local repository remote ref currently names `hg-genesis` at `cdebaeed014371f033f14352f552c6d0d4e69198`; do not silently reconcile this ref drift)

## Safety behavior
- Disclose every discovered non-secret regular file outside the recognized source/config allowlist.
- Hash unclassified inputs when within configured bounds, so byte changes stale the snapshot.
- Mark oversized unclassified inputs explicitly without pretending their contents are covered.
- Keep repository-wide source coverage incomplete for unclassified/unsupported files, parser/encoding errors, oversized files, dynamic imports, duplicate module identities, excluded secret-shaped paths, and skipped symlinks.
- Regression tests cover unrecognized extensions and stale detection, analyzer-version staleness, output containment, duplicate module names, invalid encoding, oversized unclassified files, symlink/secret exclusion, no-execution behavior and limits.

## Local evidence
- Preregistered mandatory cases: 27/27 PASS.
- Full regression suite rerun on Android/ARM64 Termux / Python 3.14.6: 35 tests PASS; exit 0.
- Python compilation: PASS; `git diff --check`: PASS.
- Candidate module SHA-256: `bee7216245f01491c111d43e1c11efae131a0be5757e6f9e910b5e263eb92342`.
- Preregistration SHA-256: `72cac07baf173a750f6a32af06025751af3012caab05231f07484007fe7fbc3a`.
- Raw benchmark result SHA-256: `ae64c43fde1d17d3c3c7cdb5963e07c162e20f21139d1291358840722535af52`.
- Frozen regression log SHA-256: `53e1bd60487cf04c5b65ecd96a743ff5cfd1329df95cf32ae7c2320988553b65`.
- Rerun log SHA-256: `2e87b3864c606a5f5b696c17776030a939ffaeb5ba5b24450883de3a2b2b5036`.
- Gate decision SHA-256 (before adding hosted CI root cause): `3b00e16ff19c3bc28dd8b82a83da1c18fbdb7d1e14f0b0fb3f9627b74d54092a`.

## Hosted CI root cause evidence
GitHub API status for PR #14 head `9ebd4687b0ff1af7c0652907f787158ce3cadee3` returns CircleCI context `ERROR` with exact description: “No configuration was found in your project.” The CircleCI pipeline URL is `https://app.circleci.com/pipelines/gh/OAI-GIANG/HG2/71`.

Read-only `git ls-tree` / GitHub Contents API checks established:
- `origin/feature/hg2-code-intelligence-absorb-20261014`: `.circleci/config.yml` absent.
- `origin/fix/hg2-code-intelligence-coverage-failclosed-20261014`: `.circleci/config.yml` absent.
- `origin/hg-genesis`: `.circleci/config.yml` present in the observed remote tree; CircleCI's pipeline-71 error proves project config resolution nevertheless failed for the PR head. The missing config on the candidate/remediation heads is the actionable, branch-scoped cause. The remote base ref drift (`local d11e71e…` vs remote `cdebaee…`) is a separate unresolved provenance issue and must not be silently normalized.
- `origin/ci/hg2-circleci-external-20261013`: `.circleci/config.yml` exists, but that separate branch does not supply configuration to PR #14's feature head by itself. This is not evidence that PR #14 CI passed.

CircleCI docs state the normal config source is `.circleci/config.yml` in the same repository, and that config must be committed/pushed to the tracked branch. References:
- https://circleci.com/docs/guides/orchestrate/pipelines/
- https://circleci.com/docs/guides/getting-started/introduction-to-yaml-configurations/

## Gate status
- Local evidence: PASS.
- Hosted CI: FAIL/ERROR, because config is absent on both the feature and remediation heads and CircleCI reports no configuration.
- Canonical refs: unresolved remote-vs-local drift; no attempt to reconcile/force push.
- Merge/deploy: NO-GO for this historical PR #14 incident because hosted CI was ERROR at that time; do not use this historical note as a current review/approval gate.

## Remediation follow-up — 2026-10-14

The isolated remediation branch is reachable again. A read-only status check confirmed the working tree was clean before this addendum and the remote branch head matched the local head. The missing `.circleci/config.yml` was added on the remediation branch only; its shell `printf` newline escapes were normalized before commit.

- CI config commit: `43d4122218c0941a6e98193969518fc262edff4d` (`ci: add isolated code intelligence verification config`).
- Push result: PASS; remote branch `fix/hg2-code-intelligence-coverage-failclosed-20261014` resolved to the same SHA.
- GitHub combined status for that exact SHA: `ci/circleci: verify = success`.
- CircleCI pipeline: https://circleci.com/gh/OAI-GIANG/HG2/68.
- Local verification on Android/ARM64 Termux / Python 3.14.6: `py_compile` PASS; full suite 35 tests PASS, exit 0. Existing `ResourceWarning` messages are from unchanged `tests/test_core.py`/existing HTTP error handling; they did not fail the suite.
- `git diff --check origin/hg-genesis...HEAD`: PASS.
- Four source archives rehashed and fully CRC-tested in place, without extraction or code execution: all SHA-256 values, byte counts, entry counts and uncompressed sizes matched the inventory above; all ZIP CRC checks PASS.
- Canonical `manifest.json` SHA-256: `748649af5d45e10d7df322e430aa01240a6f303c5f2bcb6a363aa5cf8c221abf`, identical to the compared base file. `manifest.json`, phone runtime, authority, history, identity and edge paths are unchanged in the candidate diff.
- Candidate module SHA-256 remains `bee7216245f01491c111d43e1c11efae131a0be5757e6f9e910b5e263eb92342`.

This resolves the missing-config root cause for the tested commit; it does not erase the historical failures on earlier commits. The evidence addendum itself is documentation-only and will be pushed as a subsequent commit, whose own hosted status must be checked separately.

## Remaining gates — still open

- Representative ground-truth benchmark for coverage and patch-impact quality: NOT RUN.
- Exact upstream source commit/tree provenance for all four ZIP archives: UNKNOWN.
- Component-level license/compliance audit of the upstream Codebase Memory archive: NOT COMPLETE; no upstream implementation code was copied.
- Canonical reference drift remains unresolved: task-recorded baseline `d11e71ed8b34338b8568664b39bc777c926826d5`; remote-tracking `origin/hg-genesis` is `cdebaeed014371f033f14352f552c6d0d4e69198`. No attempt was made to reconcile or force-push either ref.

**Disposition:** source inventory, clean-room candidate, local regression and hosted CI for commit `43d4122` are verified. Keep merge/deploy on HOLD only for unresolved technical gates explicitly listed above; independent review/approval is not an acceptance gate under T-018. Canonical refs and runtime remain unchanged.
