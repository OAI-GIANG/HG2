# HG2 Final Source Ref Disposition — 2026-10-19

## Decision

**BLOCKED — NO SOURCE REF DELETED.** The live remote has 25 branch refs: five functional target refs, protected `hg-genesis`, and 19 source/auxiliary refs. The required retained set is six refs if genesis is preserved separately from the five functional targets. Deletion is not authorized by this audit; final deletion requires explicit owner confirmation after the individual disposition review.

## Canonical invariants

- Repository: `OAI-GIANG/HG2` only.
- `hg-genesis`: `9d83a113ccdf1aeda656e494593fa55b9078c803` (live remote SHA verified).
- Functional targets and live remote SHAs are recorded in `evidence/HG2-FINAL-SOURCE-REF-DISPOSITION-20261019.json`.
- No new branch, force push, or source-ref deletion occurred in this operation.

## Recovery/provenance

- `hg2-source-preservation-36refs.bundle` passes `git bundle verify`; SHA-256: `f694e2e11cf895b868135f2e6a52989216ef625aa4553ecba81038fa712cf933`.
- Its advertised refs contain the exact recorded SHA for every one of the 19 current source/auxiliary refs, plus historic refs. This verifies Git-object recoverability, not that all source functionality has been integrated.
- `HG2-CONSOLIDATION-pre-20261019.bundle` passes `git bundle verify`; SHA-256: `a5e30627b72f22d9038e46e8b8475437a66f68a4676e0ca8509e3f7452930b52`.
- `hg-legacy-branches-before-retirement.bundle` passes `git bundle verify`; SHA-256: `458061e58e6f8a3a34dbb3c2a53a4bcbda712f593c7be7a7e8e359ad3064f51c`.
- The older source manifest is stale relative to live origin: it lists 36 historical refs and old target SHAs. It must not be used as the current remote inventory. The preservation bundle itself still advertises the exact SHAs for the 19 live source refs.

## Per-ref tree/ancestry crosswalk

`exact` means an identical path/blob/mode appears in at least one of the five target trees. `missing` means the source path does not occur in any target tree. `different` means the path occurs in targets but no target has the same blob/mode. Counts are conservative tree comparisons, not proof of functional equivalence; a path/blob difference blocks deletion pending semantic review.

| Source ref | Exact files | Missing paths | Differing blobs | Disposition |
|---|---:|---:|---:|---|
| `ci/deep-strict-verify-pr1-20261013` | 7/11 | 0 | 4 | Retain; snapshot/provenance review |
| `ci/deep-strict-verify-pr2-20261013` | 7/11 | 0 | 4 | Retain; snapshot/provenance review |
| `ci/hg2-circleci-external-20261013` | 7/12 | 1 | 4 | Retain; missing independent-review checklist |
| `ci/verify-pr1-snapshot-20261013` | 7/11 | 0 | 4 | Retain; snapshot/provenance review |
| `ci/verify-pr2-snapshot-20261013` | 7/11 | 0 | 4 | Retain; snapshot/provenance review |
| `design/t018-auth-checkpoint-memory-20261013` | 25/54 | 24 | 5 | Retain; T-018 security design conflict |
| `docs/t018-remove-signature-scope-20261013` | 26/58 | 27 | 5 | Retain; contract/evidence gaps |
| `feat/hexis-edge-schema-guard-20261013` | 18/45 | 18 | 9 | Retain; product-scope/evidence gaps |
| `feat/hg-t018-cross-context-sync-20261013` | 25/50 | 20 | 5 | Retain; incompatible inbound API |
| `fix/hg2-code-intelligence-coverage-failclosed-20261014` | 63/66 | 0 | 3 | Retain pending complete blob/provenance review; source is ancestor of creative target |
| `fix/hg2-p0-v3-integrity-20261013` | 7/10 | 0 | 3 | Retain pending patch-equivalence review |
| `fix/hg2-resourcewarning-20261015` | 22/24 | 0 | 2 | Retain pending commit/diff equivalence review |
| `fix/hg2-single-product-readiness-20261013` | 18/45 | 18 | 9 | Retain; product-scope/evidence gaps |
| `fix/hg2-test-resource-warning-20261013` | 7/10 | 0 | 3 | Retain pending test-patch equivalence review |
| `main` | 0/1 | 1 | 0 | Retain `.bootstrap`; target union does not contain it |
| `remediation/t018-base-reconcile-20261013` | 39/63 | 20 | 4 | Retain; T-018 evidence gaps |
| `review/t018-design-pre-review-20261013` | 25/56 | 26 | 5 | Retain; pre-review evidence gaps |
| `stt-p0-integration-20261013` | 21/24 | 0 | 3 | Retain pending commit/diff equivalence review |
| `stt/hg2-unification-p0-20261016` | 172/216 | 23 | 21 | Retain; multiple unique modules/contracts/evidence remain |

The tree crosswalk is conservative and compares against the **union** of target trees. It can overstate integration where a matching file exists in the wrong functional target, and it does not replace review of commit ancestry, test intent, provenance, runtime integration, or evidence meaning. Only one live source ref is an ancestor of a functional target (`fix/hg2-code-intelligence-coverage-failclosed-20261014` → creative target). All 19 live source refs are exactly recoverable from the source-preservation bundle.

## T-018 gate

The current contract explicitly says `PROTOTYPE_ONLY`. It identifies unresolved first-peer checkpoint trust, absent authenticated peer identity, no runtime integration, and no production transport contract. The design branch's authenticated checkpoint assumptions conflict with the later contract's stated boundary. Do not port inbound sync or mark this gate resolved until the authority approves a single security model, bootstrap trust anchor, peer-scoped checkpoint/replay policy, and atomic batch+checkpoint transaction with restart/tamper tests. No source ref related to T-018 is eligible for deletion.

## Final gate

- Five functional target refs exist: **PASS**.
- Protected `hg-genesis` SHA unchanged: **PASS**.
- Source bundle verification and exact live-source SHA recoverability: **PASS**.
- Every source semantically integrated or safely superseded: **NOT PROVEN**.
- T-018 contract resolved for inbound production sync: **BLOCKED**.
- Source deletion confirmation: **NOT REQUESTED / NOT AUTHORIZED**.
- Final disposition: **BLOCKED; retain all 19 source/auxiliary refs**.
