# HG2 Four-Source Absorption — Final Acceptance Gate Status

Date: 2026-10-14
PR: https://github.com/OAI-GIANG/HG2/pull/15
Branch: fix/hg2-code-intelligence-coverage-failclosed-20261014

## Disposition

**BLOCKED_EXTERNAL_REVIEW / MERGE_DEPLOY_HOLD.** PR #15 must remain OPEN/DRAFT. No merge, deploy, release, canonical-ref mutation, or closure is authorized by these results.

The Android Remote Desktop Commander reconnected successfully. The previously launched benchmark PID 23697 was absent from the process list; the existing pinned corpus directory was inspected before any benchmark retry. Both checkouts were already present, clean, and at the preregistered commits; no duplicate clone was performed.

## Real-repository ground-truth benchmark

### V1 — failed and preserved

- Registration SHA-256: fa8739c0a6664acad1cfa6af3f66fd8d394e84c18c8911c10a956147eaee1606
- Result SHA-256: 99e65e5fbc18b047213520b5f3aa388111b2a929389f804381169786abbd99a2
- Result: 2/2 cases failed exact edge-set checks; overall edge precision 0.50, edge recall 1.00. Dependent sets and coverage/impact states matched. V1 is retained as a failed run; it is not overwritten or counted as passing.

### V2 — preregistered and passing

V2 is a separate registration committed before its execution. It followed a manual re-audit of the pinned source import statements after V1 exposed omissions in the initial expected graph. This is not represented as a blind benchmark; V1 remains failed and unchanged. The V2 thresholds were not lowered.

- Registration commit: 457519cf7df6ac5a0ca576e60f2dea544b0710b2
- Registration SHA-256: 3a45021fb91d21b3ee371b0296e1138e7c36100d81a8fd66a4e6750731b62109
- Result SHA-256: c14daf21499347017c8b7403f563a9321fc7657979ebf9086efe6bd9a474a2af
- Runner SHA-256: 66c72f47f85666dc07fcbf21f6e488d0b72d1d010b9a2886584cfeb1473e5c19
- Analyzer SHA-256: bee7216245f01491c111d43e1c11efae131a0be5757e6f9e910b5e263eb92342
- Command: PYTHONDONTWRITEBYTECODE=1 python tools/run_real_repo_benchmark_v2.py
- Environment: Android/ARM64 Termux, Python 3.14.6.
- Corpus A: pytest-dev/iniconfig, commit 316fbfaf2752d89326e1e75b45cd070f5b5ace9a, tree aa54aaecaf1b811eb342ec0ca68ce3b71756d26c, archive SHA-256 c4e96b4921aeebcd2b590c2645017ae7c8873104db4d7f228197f89f94249306.
- Corpus B: hukkin/tomli, commit 43a86ade8b795c6ef9b4ec53372a607cd1ed426f, tree 45107c0973cfef7355190d03de3dd44a7a02fac0, archive SHA-256 52b135977f2d7a94058232d53466674d3e8b0163326c9cd67bde61d82a995110.

| Metric | Observed | Threshold | Result |
|---|---:|---:|---|
| Cases passed | 2/2 | 2/2 | PASS |
| Static edge precision / recall | 1.00 / 1.00 | 1.00 / 1.00 | PASS |
| Known-dependent precision / recall | 1.00 / 1.00 | 1.00 / 1.00 | PASS |
| Coverage-state accuracy | 1.00 | 1.00 | PASS |
| Impact-status accuracy | 1.00 | 1.00 | PASS |

Both corpora correctly reported incomplete repository-wide coverage. iniconfig: 5/5 Python files parsed, 5 unsupported source/config files and 6 unclassified files. tomli: 14/14 Python files parsed, 982 unsupported source/config files and 14 unclassified files; one dynamic import site was observed. The benchmark confirms bounded static import and known-impact behavior on these two pinned repositories only; it does not prove runtime call graphs, semantic correctness, broad repository coverage, or all-language support.

## Regression, archives, diff, and manifest

- Full regression: PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests — 35 tests PASS, exit 0. Existing ResourceWarning output from baseline test paths remains visible; it did not fail the suite.
- git diff --check: PASS at inspection.
- manifest.json SHA-256: 748649af5d45e10d7df322e430aa01240a6f303c5f2bcb6a363aa5cf8c221abf; identical to hg-genesis:manifest.json, and git diff hg-genesis...HEAD -- manifest.json is empty.
- All four ZIP files were rehashed and passed unzip -tq CRC checks without extraction or execution:
  - codebase-memory-mcp-main.zip: 9f537d98fdcc1e6e9f5b9f834cc49ca8c097dc130bc88a83c4b2f5b9e3ef35c4
  - awesome-mcp-servers-3-main.zip: a2f620afa4e41dc33689c3cef9d46fd17fb9fe7cdaf7bc18bed33a82197d7b78
  - public-apis-master.zip: e4cfb5a7593bcde80448c72f4cab7d1366bc87bc16a19e9f32732f805d202127
  - myopenvdp-master.zip: 964b23fc6e87bbf48cb178e732270984380583ee1e88c9d0f182c6e28aa40f45
- The local archive bytes are intact. Exact archive-to-upstream commit/tree provenance remains UNKNOWN for all four; ZIP filenames/current branch tips are not proof of immutable source revision. The supplied Public APIs ZIP remains incomplete/mismatched to the intended full catalog. Codebase Memory's third-party license closure has not been exhaustively audited, but no implementation or dependency from the supplied archives was copied.

## Hosted CI and review gates

CircleCI ci/circleci: verify was SUCCESS on the preregistration commit 457519cf7df6ac5a0ca576e60f2dea544b0710b2, run #90: https://circleci.com/gh/OAI-GIANG/HG2/90. This is not proof of CI on any later evidence commit; the final pushed HEAD must be queried separately.

Read-only GitHub inspection returned only OAI-GIANG in the repository collaborator list, zero requested reviewers/teams, and zero submitted reviews. No independent reviewer or independent security reviewer is presently established in the accessible collaborator/request list. The owner/PR author and STT cannot count as independent. No arbitrary users were invited. Both external review gates remain BLOCKED pending an authorized owner identifying and granting suitable repository read access to independent reviewers.

## Canonical reference and final decision

Task-recorded baseline: d11e71ed8b34338b8568664b39bc777c926826d5. Remote hg-genesis observed: cdebaeed014371f033f14352f552c6d0d4e69198. This discrepancy remains a preserved blocker; neither ref was force-pushed or reconciled.

- Real repository benchmark V2: PASS for its registered two-repository scope.
- Synthetic benchmark V2: PASS for its registered eight-fixture scope.
- Regression suite: PASS, 35 tests.
- Archive byte integrity / CRC: PASS.
- Canonical manifest invariant: PASS.
- Final-head hosted CI: must be verified against the final pushed commit.
- Independent human review: BLOCKED.
- Independent security review: BLOCKED.
- Exact upstream archive provenance: UNKNOWN.
- Merge/deploy/closure: HOLD.

**Do not mark the task closed. Keep PR #15 OPEN/DRAFT and retain BLOCKED_EXTERNAL_REVIEW / MERGE_DEPLOY_HOLD until all external gates are evidenced.**
