# HG2 Source Candidate Equivalence Gate — 2026-10-19

Scope: OAI-GIANG/HG2, Termux checkout ~/HG2-CONSOLIDATION.
Mode: READ-ONLY with respect to Git refs, code, remote, and runtime. No ref deleted, no push, no code patch.
Canonical invariants: hg-genesis must remain 9d83a113ccdf1aeda656e494593fa55b9078c803; five functional targets retained.

## Evidence method
- Refreshed remote-tracking refs using git fetch origin --prune.
- Read remote heads via git ls-remote --heads origin.
- For each candidate, compared ancestry against all five functional targets, enumerated commits reachable from candidate but not ancestors of any target, computed patch IDs for non-merge commits, enumerated changed paths, and compared candidate tip blobs against each target tree.
- Verified exact source SHA is present in hg2-source-preservation-36refs.bundle; bundle verification succeeded. SHA-256: f694e2e11cf895b868135f2e6a52989216ef625aa4553ecba81038fa712cf933.
- Patch-ID absence does not prove behavior absent/present; blob and test intent checks remain decisive.

## Candidate results

| Ref | Remote SHA | Evidence result | Disposition |
|---|---|---|---|
| ci/deep-strict-verify-pr1-20261013 | 12e71cf0c93742cd7f8afef5a2b7c763e8f90674 | Not ancestor of any functional target. Unique commits include integrity fix 60390b2, malformed-history fix b38afe0, and CI config commit. hg/history.py and tests/test_core.py tip blobs do not match any target; .circleci/config.yml absent from all target trees. | HOLD — not eligible |
| ci/deep-strict-verify-pr2-20261013 | e1c503a80e62e761621c2c46d3d2b2734367c704 | Not ancestor of any target. Includes integrity fix, malformed-history fix, response/file-handle test fix, and CI config. Target blobs differ; CI config absent from target trees. | HOLD — not eligible |
| ci/verify-pr1-snapshot-20261013 | f5e618d5815714eb31e0e00b56f63fdab2d87c7c | Not ancestor of any target. Includes integrity and malformed-history fixes; snapshot CI config absent from targets; source test blob differs from all target test blobs. | HOLD — not eligible |
| ci/verify-pr2-snapshot-20261013 | 6c95e2f8987bffd59a351014f7f4ebd89ec587ff | Not ancestor of any target. Includes integrity, malformed-history and resource-warning test commits; CI config absent from targets; source test blob differs from target test blobs. | HOLD — not eligible |
| fix/hg2-p0-v3-integrity-20261013 | b38afe04d9d71b3b605d2745091731c1860bb359 | Not ancestor of any target. Unique commits 60390b2 and b38afe0; tip hg/history.py and tests/test_core.py blobs do not match any target. Target test evidence is not patch-equivalent. | HOLD — not eligible |
| fix/hg2-test-resource-warning-20261013 | 6b3fa49367fa68d15409b043b789f3160dae0830 | Not ancestor of any target. Unique commits include malformed-history and test resource cleanup; candidate tests/test_core.py blob differs from all target trees. | HOLD — not eligible |
| fix/hg2-resourcewarning-20261015 | 93ace2bf4b55ee1b3e4285529a4e65405fedc91f | Not ancestor of any target. Its unique commit changes tests/test_core.py; resulting blob is not identical in any target. Resource-warning intent is not proven preserved. | HOLD — not eligible |
| stt-p0-integration-20261013 | e334ede66670b876d745536c7faa553798d98bd2 | Not ancestor of any target; merge commit with two parents. Resulting hg/history.py and tests/test_core.py blobs differ from all target blobs. Merge resolution and test intent not proven equivalent. | HOLD — not eligible |
| fix/hg2-code-intelligence-coverage-failclosed-20261014 | b64aaf52233dc643f06c9dd9932baf48223447d3 | Exact tip is an ancestor of origin/stt/hg2-voice-tools-design-20261018. No candidate-reachable commit exists outside target ancestry. Exact SHA present in preservation bundle. | ELIGIBLE_FOR_OWNER_CONFIRMATION |

## Test intent finding
test_duplicate_json_keys_in_history_fail_closed and test_duplicate_json_keys_in_checkpoint_fail_closed were found on origin/stt/hg2-circulatory-architecture-20261018. The other four target branches did not expose those exact test names in this check. Searches for resource-warning cleanup markers did not establish equivalence of the source resource-warning test patches in any target. Consequently all integrity/resource-warning branches remain held.

## Remote deletion completed under the latest explicit authorization
- Ref: fix/hg2-code-intelligence-coverage-failclosed-20261014
- Expected remote SHA: b64aaf52233dc643f06c9dd9932baf48223447d3
- Basis: candidate tip is an ancestor of the Creative target, no unique reachable commit outside target ancestry, exact SHA is present in verified preservation bundle.
- Recovery bundle: ~/.cache/hg2-five-branch-evidence-c5b27193baa95e741c0082cae81656a630e24d8d/hg2-source-preservation-36refs.bundle
- Recovery bundle SHA-256: f694e2e11cf895b868135f2e6a52989216ef625aa4553ecba81038fa712cf933
- Execution: remote ref was deleted with an expected-SHA lease after checking the remote SHA, bundle verification, exact bundle head, genesis SHA, and all five functional target SHAs. A fresh git ls-remote confirmed the ref is absent.
- Residual risk: the remote named pointer is gone; recovery remains possible from the Creative target and verified bundle.

## Stop conditions
- Exactly one source ref was deleted: fix/hg2-code-intelligence-coverage-failclosed-20261014 at the expected SHA. No other source ref was deleted.
- hg-genesis and all five functional target refs are retained.
- T-018 inbound synchronization remains blocked and is not eligible for source deletion.
- All five functional target test suites passed on the checked-out target refs with PYTHONDONTWRITEBYTECODE=1 python -W error::ResourceWarning -m unittest discover -s tests -v: Brain 219, Memory 112, Creative 328, Tools 92, Security 340 (1,091 total). Brain was re-run on current remote SHA 2255999bac2832e4eec396e8ac9dd4679150b1c0; result 219 OK.
- External references consulted: GitHub protected branch documentation (https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches), Git bundle documentation (https://git-scm.com/docs/git-bundle), and Python unittest documentation (https://docs.python.org/3/library/unittest.html).
- Overall status remains BLOCKED; not CLOSED_VERIFIED, because T-018 still has no approved inbound bootstrap trust policy and production atomic import/runtime evidence is absent.
