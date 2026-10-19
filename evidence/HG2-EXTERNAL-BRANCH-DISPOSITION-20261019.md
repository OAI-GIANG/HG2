# HG2 External Branch Disposition — 2026-10-19

Scope: `OAI-GIANG/HG2`; Termux checkout; read-only inventory and evidence gate.

## Protected refs

- KEEP `hg-genesis` — `9d83a113ccdf1aeda656e494593fa55b9078c803`
- KEEP `stt/hg2-brain-consolidation-20261018` — `51336d7122990723175695e473e2d6b489a629fa`
- KEEP `stt/hg2-circulatory-architecture-20261018` — `5ec19702bab09d87e67c46506098deb56f304c9c`
- KEEP `stt/hg2-gap-integration-20261018` — `d2ba34485164e3526c3e411fcf09bd1de4c7353e`
- KEEP `stt/hg2-single-system-20261017` — `644972deef5921817e6b2d048112330530f72f45`
- KEEP `stt/hg2-voice-tools-design-20261018` — `53e4afe5c338c1fce49e5077181c7de4c175f696`

## External refs — current disposition

Deletion policy: no deletion unless the exact remote SHA is present in the verified recovery bundle and unique content is shown absorbed or safely dispensable. T-018 refs are held for the later T-018 phase. `main` is held because `.bootstrap` is unique.

- `ci/deep-strict-verify-pr1-20261013` — remote `12e71cf0c93742cd7f8afef5a2b7c763e8f90674` — recovery_bundle_exact_ref=YES — **HOLD_UNIQUE_CONTENT_OR_INCOMPLETE_EQUIVALENCE_AUDIT**
- `ci/deep-strict-verify-pr2-20261013` — remote `e1c503a80e62e761621c2c46d3d2b2734367c704` — recovery_bundle_exact_ref=YES — **HOLD_UNIQUE_CONTENT_OR_INCOMPLETE_EQUIVALENCE_AUDIT**
- `ci/hg2-circleci-external-20261013` — remote `0c71e400a6510fbe06b6fa9fe2bdff414fcb2ef8` — recovery_bundle_exact_ref=YES — **HOLD_UNIQUE_CONTENT_OR_INCOMPLETE_EQUIVALENCE_AUDIT**
- `ci/verify-pr1-snapshot-20261013` — remote `f5e618d5815714eb31e0e00b56f63fdab2d87c7c` — recovery_bundle_exact_ref=YES — **HOLD_UNIQUE_CONTENT_OR_INCOMPLETE_EQUIVALENCE_AUDIT**
- `ci/verify-pr2-snapshot-20261013` — remote `6c95e2f8987bffd59a351014f7f4ebd89ec587ff` — recovery_bundle_exact_ref=YES — **HOLD_UNIQUE_CONTENT_OR_INCOMPLETE_EQUIVALENCE_AUDIT**
- `design/t018-auth-checkpoint-memory-20261013` — remote `6f636c5ebdf7363172fdd2cbda6d72258179589d` — recovery_bundle_exact_ref=YES — **HOLD_T018_PHASE_DEFERRED**
- `docs/t018-remove-signature-scope-20261013` — remote `a296abb3016a1cf771d3db1c870dad8e3fdb9adb` — recovery_bundle_exact_ref=YES — **HOLD_T018_PHASE_DEFERRED**
- `feat/hexis-edge-schema-guard-20261013` — remote `fa53a5768145279f54f182e8c5cc3c73976fda42` — recovery_bundle_exact_ref=YES — **HOLD_UNIQUE_CONTENT_OR_INCOMPLETE_EQUIVALENCE_AUDIT**
- `feat/hg-t018-cross-context-sync-20261013` — remote `4d97c34d8bb7c1091265330aef63dd78d0e72c49` — recovery_bundle_exact_ref=YES — **HOLD_T018_PHASE_DEFERRED**
- `fix/hg2-p0-v3-integrity-20261013` — remote `b38afe04d9d71b3b605d2745091731c1860bb359` — recovery_bundle_exact_ref=YES — **HOLD_UNIQUE_CONTENT_OR_INCOMPLETE_EQUIVALENCE_AUDIT**
- `fix/hg2-resourcewarning-20261015` — remote `93ace2bf4b55ee1b3e4285529a4e65405fedc91f` — recovery_bundle_exact_ref=YES — **HOLD_UNIQUE_CONTENT_OR_INCOMPLETE_EQUIVALENCE_AUDIT**
- `fix/hg2-single-product-readiness-20261013` — remote `63942520602108f6aa172a9d419822033271e2b2` — recovery_bundle_exact_ref=YES — **HOLD_UNIQUE_CONTENT_OR_INCOMPLETE_EQUIVALENCE_AUDIT**
- `fix/hg2-test-resource-warning-20261013` — remote `6b3fa49367fa68d15409b043b789f3160dae0830` — recovery_bundle_exact_ref=YES — **HOLD_UNIQUE_CONTENT_OR_INCOMPLETE_EQUIVALENCE_AUDIT**
- `main` — remote `dc29622fce50b328fca5673b1d0385be884ec132` — recovery_bundle_exact_ref=YES — **HOLD_UNIQUE_BOOTSTRAP**
- `remediation/t018-base-reconcile-20261013` — remote `da3d055201357923f7fab079654d39962e87ccd5` — recovery_bundle_exact_ref=YES — **HOLD_T018_PHASE_DEFERRED**
- `review/t018-design-pre-review-20261013` — remote `fa90faacb4a47492121480455c1747535ab5817c` — recovery_bundle_exact_ref=YES — **HOLD_T018_PHASE_DEFERRED**
- `stt-p0-integration-20261013` — remote `e334ede66670b876d745536c7faa553798d98bd2` — recovery_bundle_exact_ref=YES — **HOLD_UNIQUE_CONTENT_OR_INCOMPLETE_EQUIVALENCE_AUDIT**
- `stt/hg2-unification-p0-20261016` — remote `a64e49d1619f5d83b5741d13c92961df9b07c79a` — recovery_bundle_exact_ref=YES — **HOLD_UNIQUE_CONTENT_OR_INCOMPLETE_EQUIVALENCE_AUDIT**

## Verified recovery artifact

- Bundle: `/data/data/com.termux/files/home/.cache/hg2-five-branch-evidence-c5b27193baa95e741c0082cae81656a630e24d8d/hg2-source-preservation-36refs.bundle`
- SHA-256: `f694e2e11cf895b868135f2e6a52989216ff625aa4553ecba81038fa712cf933`
- Bundle validation: `git bundle verify` completed successfully; bundle advertises 72 refs.

## Important limitation

The branch comparison showed that several CI/fix refs share patch-identical commits, but also retain branch-specific CI snapshots or tests. Patch identity alone does not prove every ref is safe to delete. No external refs were deleted during this inventory pass. Some refs are not represented in the local 36-ref evidence bundle at their current SHA; those are ineligible for deletion until a verified recovery copy is produced.

## Next gate

For each candidate, produce a per-file/commit equivalence record against the five functional refs, validate bundle SHA and exact ref SHA, then delete only candidates passing every gate using a normal non-force ref deletion with expected-SHA lease. Re-fetch and verify remote absence afterward. T-018 refs remain held.
