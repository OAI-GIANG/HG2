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
- Independent review: NOT SATISFIED (no submitted reviews, no reviewer requests).
- Independent security review: NOT SATISFIED.
- Canonical refs: unresolved remote-vs-local drift; no attempt to reconcile/force push.
- Merge/deploy: NO-GO. Keep PR #14 OPEN/DRAFT and canonical baseline/release state unchanged until CI and independent review/security gates are independently satisfied.
