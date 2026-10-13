# HG2 Four-Source Absorption — Final Acceptance Gate Status

Date: 2026-10-14
PR: https://github.com/OAI-GIANG/HG2/pull/15
Branch: `fix/hg2-code-intelligence-coverage-failclosed-20261014`
Current upstream head before this evidence commit: `252f0c4d58db8d83646ad85f6a3e8bc774cbf296`.

## Executive disposition

**`TECHNICALLY_VERIFIED_FOR_BOUNDED_SYNTHETIC_SCOPE / BLOCKED_EXTERNAL_REVIEW / MERGE_DEPLOY_HOLD`.** The isolated clean-room candidate passes unit tests, the V2 preregistered synthetic ground-truth suite passes all registered thresholds, four archive integrity checks pass, and canonical manifest/runtime paths are unchanged. This is not production certification and the whole task is not eligible for closure while independent review/security review and exact archive provenance remain unsatisfied/unknown.

PR #15 must remain OPEN/DRAFT. No merge, deployment, release or canonical ref mutation is authorized by this evidence.

## Preregistered V2 ground-truth benchmark

V2 is distinct from V1. V1's expected values and recall threshold were amended during development after seeing results; therefore V1 is preserved only as an exploratory trail and is explicitly not acceptance evidence (`HG2_CI_BENCHMARK_V1_RELIABILITY_NOTE.md`). V2 expected static edges/dependents, coverage/impact states, all 28 fixture-file hashes, scoring formulas and 1.0 acceptance thresholds were committed to the registration artifact before the first V2 scorer run. The scorer verifies the fixture hashes before analyzing them. No V2 expected results or thresholds were edited after the V2 run.

- Registration: `HG2_CI_GROUND_TRUTH_REGISTRATION_V2.json`; SHA-256 `f0b0ba7ab1b4c176149ad0f72f08b0e9ab2582acc2a839b79a9d65d01874940b`.
- Result: `HG2_CI_GROUND_TRUTH_RESULT_V2.json`; SHA-256 `658645faa6a67f8b6eab02c01d55cdb7911d2304b61ced4dd9ba8875fc363bd5`.
- Scorer: `tools/run_code_intelligence_benchmark.py`; SHA-256 `e32bc8be0e658923aceab7dcfd9986b1f2de351bacbaf81be113ba8c41c03046`.
- Candidate analyzer: `tools/hg_code_intelligence.py`; SHA-256 `bee7216245f01491c111d43e1c11efae131a0be5757e6f9e910b5e263eb92342`.
- Receipt binding all four identities and environment: `HG2_CI_GROUND_TRUTH_RECEIPT_V2.json`; SHA-256 `f7dd26298a226fa34792e6de7e7fa0498623aa8fa0541bbf88694e9bee527d49`.
- Command: `PYTHONDONTWRITEBYTECODE=1 python tools/run_code_intelligence_benchmark.py`.
- Environment: Android/ARM64 Termux, Python 3.14.6 (see machine-generated V2 result for full platform text).

| Metric | Observed | Registered threshold | Result |
|---|---:|---:|---|
| Registered cases | 8/8 | At least 8 | PASS |
| Case expectations passed | 8/8 | All cases | PASS |
| Overall static edge precision / recall | 1.00 / 1.00 | 1.00 / 1.00 | PASS |
| Overall known-dependent precision / recall | 1.00 / 1.00 | 1.00 / 1.00 | PASS |
| Clean-case edge precision / recall | 1.00 / 1.00 | 1.00 / 1.00 | PASS |
| Clean-case known-dependent precision / recall | 1.00 / 1.00 | 1.00 / 1.00 | PASS |
| Coverage-state accuracy | 1.00 | 1.00 | PASS |
| Impact-status accuracy | 1.00 | 1.00 | PASS |
| Fail-closed recall over five incomplete cases | 1.00 | 1.00 | PASS |

Scope limit: eight small synthetic fixtures with 28 files, hand-authored to test the bounded static-import contract. A pass is not evidence of broad real-world repository quality, language-complete dependency discovery or production safety. A representative real-repository ground-truth corpus remains unrun.

## Regression, archive, and baseline verification

- Python compilation: PASS for candidate, unit tests and benchmark scorer.
- Full repository regression suite: **35 tests PASS**, exit 0 (Android/ARM64 Termux, Python 3.14.6). Existing `ResourceWarning` messages arise from unmodified baseline tests/error-handling paths and did not fail the run.
- `git diff --check origin/hg-genesis...HEAD`: PASS at the inspected candidate revision.
- All four supplied ZIPs were rehashed and their ZIP CRC checked in-place without extraction or code execution. SHA-256, byte count, entry count, uncompressed totals and CRC all matched the existing inventory in `ABSORPTION_SOURCE_DECISIONS.md`.
- `manifest.json` SHA-256 remains `748649af5d45e10d7df322e430aa01240a6f303c5f2bcb6a363aa5cf8c221abf`.
- Canonical runtime/authority/history/identity/edge paths and manifest remain unchanged in the scoped candidate diff. No dependency added, no third-party source implementation reused, no production wiring or deployment.

The next commit modifies only isolated benchmark/evidence material and the existing remediation-branch CircleCI config. The config now runs the full test suite, then runs this V2 benchmark and asserts the recorded `benchmark_pass` boolean; the new commit's exact hosted CircleCI result must be checked after push.

## Upstream provenance / license review

`HG2_SOURCE_PROVENANCE_LICENSE_AUDIT.md` records the observed archive content metadata, source URLs and current branch tips where available. Current branch tips are references only; they do not prove which immutable commits generated the four ZIP files.

- All four local ZIP byte identities/CRCs: PASS.
- Exact ZIP-to-upstream commit/tree equivalence: UNKNOWN for all four; no `.git` commit or authoritative archive-attestation record was present.
- `public-apis-master.zip`: no README/populated catalog, unlike the intended public-apis repository; full catalog equivalence is not established and the archive is not used.
- Codebase Memory upstream license closure: not exhaustively audited because its `THIRD_PARTY.md` and vendored component licenses cover numerous distinct terms. No Codebase Memory implementation, dependency, grammar or binary was copied. Component-level review becomes mandatory before any future reuse.
- Current source adoption remains clean-room concepts only; archive URL similarity or MIT root LICENSE is not treated as proof of entire archive license/provenance.

## Independent review and security review gate

Current read-only PR inspection reports `OPEN`, `DRAFT`, no review requests, and no submitted reviews. `gh api repos/OAI-GIANG/HG2/collaborators` returned only `OAI-GIANG` (the repository owner/PR author) as a collaborator. No other user or team with repository read access is available in the returned collaborator list, so a legitimate independent human reviewer cannot currently be selected/requested from the known access list. The PR author cannot count as independent; STT's own assessment is not independent review. No arbitrary user was invited or requested.

GitHub's documented prerequisites for reviewer requests include repository write access for the requester and read access for the requested person/team: https://docs.github.com/en/pull-requests/how-tos/create-pull-requests/requesting-a-pull-request-review. An authorized repository owner must add/identify an independent reviewer and security reviewer with appropriate access before those gates can be satisfied.

## Canonical reference drift

Task-recorded baseline: `d11e71ed8b34338b8568664b39bc777c926826d5`.
Remote-tracking / GitHub `hg-genesis` observed during this work: `cdebaeed014371f033f14352f552c6d0d4e69198`.

The discrepancy is preserved as a blocker. Neither ref was force-pushed or reconciled. PR #15 targets the current GitHub `hg-genesis` ref, while review evidence retains the original task-recorded baseline and explains the difference.

## Closure decision

- Candidate and limited synthetic benchmark: technically verified.
- Hosted CI: prior current head `252f0c4d58db8d83646ad85f6a3e8bc774cbf296` was SUCCESS at https://circleci.com/gh/OAI-GIANG/HG2/69; final acceptance commit must be checked separately.
- External human independent review: BLOCKED.
- External independent security review: BLOCKED.
- Exact upstream ZIP provenance: UNKNOWN.
- Production-representative ground-truth benchmark: NOT RUN.
- Merge/deploy: HOLD.

**Final status remains `BLOCKED_EXTERNAL_REVIEW / MERGE_DEPLOY_HOLD`; do not mark task closed.**
