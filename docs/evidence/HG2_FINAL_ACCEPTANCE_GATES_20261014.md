# HG2 Four-Source Absorption — Corrected Acceptance Gate Status

Date: 2026-10-14
PR: https://github.com/OAI-GIANG/HG2/pull/15
Branch: fix/hg2-code-intelligence-coverage-failclosed-20261014

## Current disposition

**SOURCE_PROVENANCE_VERIFIED / MERGE_DEPLOY_HOLD.**

The four supplied ZIP archives have now been mapped to immutable upstream commits and tree IDs by checking each ZIP comment, resolving that exact commit through GitHub's API, and comparing all included paths and Git blob IDs against the commit tree. The one partial archive (Public APIs) omits only paths matched by the upstream .gitattributes export-ignore rules. No source-provenance blocker remains on the evidence recorded below. PR #15 remains OPEN/DRAFT by instruction; no merge, deploy, release, or canonical-ref mutation is authorized. This finding does not claim overall product acceptance.

## Runtime reconnection and state recovery

Remote Desktop Commander reconnected to the Android device. The earlier benchmark process PID 23697 was absent from the current process list. The existing pinned repository directories were inspected before retrying; both repositories were already present, clean, and at the registered commits, so no duplicate clone was performed.

## Real-repository ground-truth benchmark

### V1 — failed and preserved

- Registration SHA-256: fa8739c0a6664acad1cfa6af3f66fd8d394e84c18c8911c10a956147eaee1606
- Result SHA-256: 99e65e5fbc18b047213520b5f3aa388111b2a929389f804381169786abbd99a2
- Result: 2/2 cases failed exact edge-set checks; overall edge precision 0.50 and edge recall 1.00. Dependent sets and coverage/impact states matched. V1 remains an immutable failed run and is not counted as passing.

### V2 — preregistered and passing

V2 is a separate registration committed before execution. After V1 exposed omissions, expected edges were manually re-audited against the pinned source import statements. This is not represented as a blind benchmark. V1 remains failed and unchanged; V2 thresholds were not lowered.

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

Both corpora correctly reported incomplete repository-wide coverage. iniconfig: 5/5 Python files parsed, 5 unsupported source/config files and 6 unclassified files. tomli: 14/14 Python files parsed, 982 unsupported source/config files and 14 unclassified files; one dynamic import site was observed. These results validate the bounded static-import/known-impact contract for two pinned repositories only; they do not establish runtime call graphs, semantic correctness, broad repository coverage, or all-language support.

## Synthetic benchmark and regression

- Synthetic preregistered benchmark V2: 8/8 cases passed the registered thresholds. Registration SHA-256 f0b0ba7ab1b4c176149ad0f72f08b0e9ab2582acc2a839b79a9d65d01874940b; result SHA-256 658645faa6a67f8b6eab02c01d55cdb7911d2304b61ced4dd9ba8875fc363bd5.
- Full regression: PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests — 35 tests PASS, exit 0. Existing ResourceWarning messages from baseline test paths were visible and did not fail the suite.
- The real-repository V2 result records candidate HEAD 457519cf7df6ac5a0ca576e60f2dea544b0710b2; it was run before the evidence-only result/report commit. The candidate analyzer hash was verified by the runner.

## Latest hosted CI and branch state

- Last candidate HEAD verified before this provenance-evidence-only change: f77bfb33101a6121203505b55e7707bbb7893849.
- CircleCI ci/circleci: verify on that exact HEAD: SUCCESS, run #93 — https://circleci.com/gh/OAI-GIANG/HG2/93.
- The provenance verifier and this report/evidence are documentation-only additions. The resulting new HEAD must be checked separately; do not transfer the prior CI result to a later commit.
- PR #15 was observed OPEN/DRAFT; no merge/deploy action was taken.

## Archive integrity and source provenance

All four supplied ZIP files were rehashed and passed unzip -tq CRC checks without extraction or code execution:

| Archive | SHA-256 | Byte integrity |
|---|---|---|
| codebase-memory-mcp-main.zip | 9f537d98fdcc1e6e9f5b9f834cc49ca8c097dc130bc88a83c4b2f5b9e3ef35c4 | PASS |
| awesome-mcp-servers-3-main.zip | a2f620afa4e41dc33689c3cef9d46fd17fb9fe7cdaf7bc18bed33a82197d7b78 | PASS |
| public-apis-master.zip | e4cfb5a7593bcde80448c72f4cab7d1366bc87bc16a19e9f32732f805d202127 | PASS |
| myopenvdp-master.zip | 964b23fc6e87bbf48cb178e732270984380583ee1e88c9d0f182c6e28aa40f45 | PASS |

**Source provenance result: VERIFIED for all four supplied archives.** The ZIP comment in each file contained a 40-character commit SHA-1. That exact SHA was resolved via GitHub's commit API, and the immutable tree was fetched through the Git Trees API. The verifier compared every included archive path and computed Git blob SHA-1 against that tree. No included file had a blob mismatch; there were no unexplained missing or extra paths.

| Archive | Upstream repository | Exact commit | Tree SHA-1 | Included files / tracked blobs | Result |
|---|---|---|---|---:|---|
| codebase-memory-mcp-main.zip | DeusData/codebase-memory-mcp | bb636d1ff7a47f70bccfc6d6e5d0e43e92ce7a0c | 3c9cfb82f2125bf0ebe32d2a0c6485272bee91ce | 3537 / 3537 | PASS |
| awesome-mcp-servers-3-main.zip | appcypher/awesome-mcp-servers | 70acc2194806cd47878737bb41a958f6958b388c | 76ee292e2fa651083c65a6f7f23bd924e463ab40 | 11 / 11 | PASS |
| public-apis-master.zip | public-apis/public-apis | 73035eafdb7e15a078afb7d8b8487f53d5104e9a | d4ab700098d9417c77d490b79a861e09d5352d01 | 12 / 23 | PASS — export-ignore |
| myopenvdp-master.zip | yeswehack/myopenvdp | 03e90e225cb8aee90bd36c5684b97b5298dcbbbb | 13a0c8cbd312feb11d21aaec2025f14d709428e8 | 141 / 141 | PASS |

The Public APIs tree has 11 paths intentionally absent from the archive: nine under .github plus README.md and scripts/README.md. The archived .gitattributes contains the rules /.github export-ignore and README.md export-ignore; the missing paths match those rules exactly. The archive therefore matches the commit's Git-archive export, rather than being evidence of a wrong or incomplete upstream revision.

Reproducible evidence:
- Verifier: docs/evidence/scripts/verify_hg2_source_archive_provenance.py; SHA-256 2402fe9288b00dddd5919cb431ab33625e256cc2ddf0aebccaa56c298f2d81dc
- Result JSON: docs/evidence/HG2_SOURCE_PROVENANCE_RESULT_20261014.json; SHA-256 6f254a59dd18e86ba721fd7b08923214921a4df038e48477386e5edc7598cebb
- Captured run log: docs/evidence/HG2_SOURCE_PROVENANCE_VERIFICATION_LOG_20261014.txt; SHA-256 1c78bc6b276a7cdcc8b86f7ec0804564feb69b1f174fa47851a9c93a99523266
- Hash receipt: docs/evidence/HG2_SOURCE_PROVENANCE_RECEIPT_20261014.json (binds the report, verifier, result/log and unchanged benchmark registration/result hashes).
- Detailed provenance/license audit: docs/evidence/HG2_SOURCE_PROVENANCE_LICENSE_AUDIT.md; SHA-256 19d8274d031b75678fa8076fc28c271ffcb29907592c6b963ff2a6d5dd4afd94.
- The verifier reads ZIP members in place; it does not extract or execute archive content. Each archive member was read successfully, triggering ZIP CRC validation.
- All four original archive SHA-256 values remain unchanged and are recorded in the result JSON.
- Codebase Memory's third-party component license closure has not been exhaustively audited. No implementation or dependency from any supplied archive was copied into the candidate; this is a separate license-scope limitation, not an unresolved source-commit identity.

## Canonical invariants

- manifest.json SHA-256: 748649af5d45e10d7df322e430aa01240a6f303c5f2bcb6a363aa5cf8c221abf.
- git diff hg-genesis...HEAD -- manifest.json is empty.
- No canonical ref was modified, force-pushed, or reconciled.
- The task-recorded baseline commit d11e71ed8b34338b8568664b39bc777c926826d5 and observed remote hg-genesis commit cdebaeed014371f033f14352f552c6d0d4e69198 have different commit identities, but their tree contents compare equal in the inspected repository. Record this identity difference; do not silently rewrite either ref.

## Corrected gate decision

| Gate | State | Evidence / disposition |
|---|---|---|
| Android process/worktree recovery | PASS | Existing corpus inspected before retry; no duplicate clone |
| Real-repository benchmark V2 | PASS, limited scope | 2/2 pinned repositories, all registered thresholds met |
| Synthetic benchmark V2 | PASS, limited scope | 8/8 registered cases |
| Regression | PASS | 35 tests, exit 0 |
| Hosted CI | PASS on pre-provenance-evidence HEAD f77bfb3… | CircleCI run #93; latest evidence commit checked separately |
| Archive SHA-256 and ZIP CRC | PASS | Four local archives rehashed and CRC-tested |
| Canonical manifest/ref non-mutation | PASS | Manifest hash unchanged; no canonical ref mutation |
| Exact archive source commit/tree provenance | PASS for all four archives | ZIP comment commit resolved through GitHub API; included paths/blob IDs match immutable trees; Public APIs exclusions explained by export-ignore |
| Merge/deploy | HOLD | Preserve user instruction; PR #15 remains OPEN/DRAFT |

**Disposition: SOURCE_PROVENANCE_VERIFIED / MERGE_DEPLOY_HOLD.** The source-provenance blocker is cleared by the recorded commit/tree and blob-level evidence. Keep PR #15 OPEN/DRAFT under the user's explicit instruction. Do not merge, deploy, alter canonical refs, or claim overall product acceptance from source provenance alone.
