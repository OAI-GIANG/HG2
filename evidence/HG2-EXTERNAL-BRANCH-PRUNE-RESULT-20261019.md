# HG2 External Branch Prune — Final Result — 2026-10-19

## Result

**Remote ref inventory verified: exactly five branches remain.** Eighteen non-canonical remote refs were removed after preserving their exact source deltas and ref metadata in the Genesis archive plus verified local Git bundles. No force push was used.

## The five retained branches

| Functional role | Remote branch | HEAD after prune |
|---|---|---|
| Brain / central command | `hg-genesis` | `1dca305b4d6e9442e259442486efb5127cc0cb09` |
| Memory / knowledge / history | `stt/hg2-single-system-20261017` | `644972deef5921817e6b2d048112330530f72f45` |
| Creative / research / experiments | `stt/hg2-voice-tools-design-20261018` | `53e4afe5c338c1fce49e5077181c7de4c175f696` |
| Tools / tasks / automation | `stt/hg2-gap-integration-20261018` | `d2ba34485164e3526c3e411fcf09bd1de4c7353e` |
| Security / policy / verification / sync | `stt/hg2-circulatory-architecture-20261018` | `5ec19702bab09d87e67c46506098deb56f304c9c` |

## Archived and removed external refs

| Deleted remote branch | Exact source SHA archived before deletion |
|---|---|
| `ci/deep-strict-verify-pr1-20261013` | `12e71cf0c93742cd7f8afef5a2b7c763e8f90674` |
| `ci/deep-strict-verify-pr2-20261013` | `e1c503a80e62e761621c2c46d3d2b2734367c704` |
| `ci/hg2-circleci-external-20261013` | `0c71e400a6510fbe06b6fa9fe2bdff414fcb2ef8` |
| `ci/verify-pr1-snapshot-20261013` | `f5e618d5815714eb31e0e00b56f63fdab2d87c7c` |
| `ci/verify-pr2-snapshot-20261013` | `6c95e2f8987bffd59a351014f7f4ebd89ec587ff` |
| `design/t018-auth-checkpoint-memory-20261013` | `6f636c5ebdf7363172fdd2cbda6d72258179589d` |
| `docs/t018-remove-signature-scope-20261013` | `a296abb3016a1cf771d3db1c870dad8e3fdb9adb` |
| `feat/hexis-edge-schema-guard-20261013` | `fa53a5768145279f54f182e8c5cc3c73976fda42` |
| `feat/hg-t018-cross-context-sync-20261013` | `4d97c34d8bb7c1091265330aef63dd78d0e72c49` |
| `fix/hg2-p0-v3-integrity-20261013` | `b38afe04d9d71b3b605d2745091731c1860bb359` |
| `fix/hg2-resourcewarning-20261015` | original archived head `93ace2bf4b55ee1b3e4285529a4e65405fedc91f`; later helper head `32e9bf998677ff6eeb162d01678ca42f4dc9ca1b` is an ancestor of the Genesis PR #28 merge |
| `fix/hg2-single-product-readiness-20261013` | `63942520602108f6aa172a9d419822033271e2b2` |
| `fix/hg2-test-resource-warning-20261013` | `6b3fa49367fa68d15409b043b789f3160dae0830` |
| `main` | `dc29622fce50b328fca5673b1d0385be884ec132` |
| `remediation/t018-base-reconcile-20261013` | `da3d055201357923f7fab079654d39962e87ccd5` |
| `review/t018-design-pre-review-20261013` | `fa90faacb4a47492121480455c1747535ab5817c` |
| `stt-p0-integration-20261013` | `e334ede66670b876d745536c7faa553798d98bd2` |
| `stt/hg2-unification-p0-20261016` | `a64e49d1619f5d83b5741d13c92961df9b07c79a` |

The redundant brain candidate `stt/hg2-brain-consolidation-20261018` was separately integrated into `hg-genesis` via PR #27 (merge commit `4a39be3ee1f58c05f22c00fee87b5fc9bc78e1ba`) and deleted after ancestry verification. PR #28 added the archival data to `hg-genesis` (merge commit `1dca305b4d6e9442e259442486efb5127cc0cb09`).

## Preservation / equivalence evidence

- Durable canonical archive: `hg-genesis:evidence/source-ref-archive/20261019/`.
- Archive manifest: 18 source refs, source SHA, merge base, commit chain, changed paths, tree IDs, patch IDs, patch SHA-256, recovery-ref mapping and disposition for every non-canonical source branch.
- Archive payload: 15 deduplicated binary-capable Git diffs preserve 17 source branch deltas; the unrelated `main:.bootstrap` file is preserved exactly as a standalone file. Every stored patch/file SHA-256 was recomputed against the manifest after the archive landed on Genesis.
- Pre-prune recovery bundle: `$HOME/.cache/hg2-five-branch-evidence-c5b27193baa95e741c0082cae81656a630e24d8d/hg2-final-pre-prune-20261019.bundle`, SHA-256 `c0f9ba9001d1919893046cae3ac7e0467c6cf1a5ca4d39e88d64f0e7582ab94c`; `git bundle verify` passed before deletion and every then-live external ref was checked against the bundle. The original source preservation bundle is also retained with SHA-256 `ad9611f91b11c97dda1c7b4a8b826801c6ea2e16d0836899774cf1d3c7ff0b7e`.
- Deletion method: normal `git push origin :refs/heads/<exact-ref>`; every removal in the deletion batch was immediately followed by `git ls-remote --heads origin refs/heads/<exact-ref>` to verify absence.
- Final independent `git ls-remote --heads origin` returned exactly the five rows above; the exact five-name set was asserted against the expected set.
- Genesis strict unit suite after archive merge: `PYTHONDONTWRITEBYTECODE=1 python -W error::ResourceWarning -m unittest discover -s tests -v` — 219 tests passed. HNIF V2.1 static validator passed and all `SHA256SUMS-V2.1.txt` checks passed.

## T-018 boundary

T-018 branches were archived and deleted as source refs, but their prototypes/design are **not activated as production sync** and T-018 remains a separate unfinished engineering task. Pruning source branch names is not a claim that T-018 is completed. Its historic code, tests, contracts, review notes and evidence are retrievable from the archive patches and preservation bundle.

## Final gate

`EXTERNAL_BRANCH_DISPOSITION = COMPLETE`
`REMOTE_BRANCH_COUNT = 5`
`CANONICAL_BRANCH_SET = PASS`
`SOURCE_ARCHIVE_HASHES = PASS`
`RECOVERY_BUNDLE_VERIFICATION = PASS`
`T018_PRODUCTION_COMPLETION = NOT_CLAIMED`
