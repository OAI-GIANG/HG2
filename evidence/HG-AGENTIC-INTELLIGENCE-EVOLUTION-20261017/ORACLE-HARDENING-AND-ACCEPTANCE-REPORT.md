# HG Agentic Intelligence Evolution — Oracle Hardening and Acceptance Report

**Observation date:** 2026-10-17 (Termux / Android)
**Scope:** candidate-only quantitative oracle hardening, regression tests, CI evidence, read-only runtime provenance/trust investigation.
**Disposition:** `TECHNICAL_CANDIDATE_IMPROVED / PRODUCTION_ACCEPTANCE_BLOCKED / NOT_RELEASED`.

## 1. Candidate and authority boundary

- Repository: `OAI-GIANG/HG2`
- Branch: `stt/hg-agentic-intelligence-g1-20261017`
- Previous HEAD: `480e70a1dcb50f8865e11222ed2191350b29e5bd`
- Oracle hardening commit: `4a372575db4aecc403fc0505129371cd6a8d49cc`
- Canonical base: `9d83a113ccdf1aeda656e494593fa55b9078c803`
- PR #21 remains OPEN and Draft; no merge, deployment, release, or cutover.

Only the candidate branch was modified. Canonical branch and running services were not changed. The local `hg-genesis` ref remains stale at `d11e71ed8b34338b8568664b39bc777c926826d5`; remote canonical remains `9d83a113ccdf1aeda656e494593fa55b9078c803`. No fetch/reset/ref update was performed.

## 2. Finding and root cause

The deterministic oracle evaluated its fixed dataset but did not fail closed on dataset tampering/inventory loss and accepted several invalid quantitative domains (empty Brier events, out-of-range probability, zero denominators, invalid error counts, and empty repeatability samples). A passing synthetic oracle alone also does not establish live-model quality or production behavior.

## 3. Change implemented

In `scripts/hg-native-oracle`:
- Pin expected dataset SHA-256, dataset/schema identity, classification, CP0 historical-equivalence declaration, and exact OR-01..OR-20 inventory.
- Validate case schema and predeclared metric presence before evaluation.
- Reject empty/out-of-domain Brier inputs, invalid pass/error denominators and counts, invalid critical-failure counts, and empty repeatability inputs.
- Convert invalid dataset/evaluation input into a bounded `BLOCKED_INVALID_ORACLE_INPUT` result; do not expose raw exception details or filesystem paths.

In `tests/test_native_oracle.py`:
- Add independent negative regression cases for dataset tampering, case inventory loss, Brier domain errors, zero denominators, invalid error counts, and empty repeatability samples.
- Assert the output digest matches the pinned dataset digest.

## 4. Verification evidence

- Termux full unit suite after patch: **182 tests PASS** (`python -W error::ResourceWarning -m unittest discover -s tests -v`).
- Quantitative oracle: **20/20 PASS**, dataset SHA-256 `cfeb9b2cbdc05ce7238f236e942a167b1d40549af2678d1f879b67253fde9916`.
- Synthetic benchmark: `SYNTHETIC_CONTROL_POLICY_COMPARISON_NOT_LIVE_MODEL`; `observed_model_runs=0`; delta pass rate `0.75`; 15 paired cases improved; no listed regressions; `production_acceptance=NOT_ESTABLISHED`.
- HNI fixture validator: PASS; 26 unique fixtures, 26/26 oracle specs, HNIT 30/30, XN 6/6; arithmetic/digest/aggregation checks PASS.
- HNI package tests: 12/12 PASS; package SHA-256 manifest checks PASS.
- `git diff --check`: PASS before commit.
- CircleCI #143: success on exact revision `4a372575db4aecc403fc0505129371cd6a8d49cc`; full strict unit step exit code 0, oracle step exit code 0, benchmark step exit code 0. GitHub commit status context `ci/circleci: verify` = success.
- Sanitized CircleCI #143 log and metadata are stored locally under `~/.cache/hg-evidence-first-20261017/ci-after-push/`. Raw step output was fetched in memory, hashed, and not saved. Sanitized log SHA-256: `99bcf469f8ad428e71510dbbdf0216f0fa324125033134bea37616f071acef5d`. Sanitized JSON SHA-256: `c5027852f20e4148a07a17f48d85a74f3d36121f95fb09f8f87b7198b8e63551`.

## 5. Runtime provenance — BLOCKED_MISMATCH

Read-only inspection found active processes:
- PID 10805: `/data/data/com.termux/files/home/hg/backend/hg_backend.py`, SHA-256 `2b6127e26beff90c2cb304b8bee94043d58208507586baa79400291c64f20905`.
- PID 10809: `/data/data/com.termux/files/home/hg/core/runtime/hg_runtime.py`, SHA-256 `e02f344c11f0e513e4e874fdc35eb6c28ea76d8aa541da7bbde19a1427f10a83`.
- PID 10804: `/data/data/com.termux/files/home/hg2-service/entry.py`; its `hg2-phone` worktree is detached at `4d97c34d8bb7c1091265330aef63dd78d0e72c49` and dirty.

`~/hg` is not a Git working tree. The candidate's `hg/phone_runtime.py` SHA-256 is `4a788efdbe0427ca36f8d497073dcdbab55b87c70b418dafa7a8373345751b22`, which differs from the live runtime file hash above. Several candidate modules have no corresponding files in the live runtime path. File digests describe bytes on disk; they do not prove which source was loaded into a process or bind the runtime to an approved commit.

## 6. Trust roots — BLOCKED

The live plugin contract loads a private local JSON registry mapping plugin IDs to manifest SHA-256 values. A configured hash allowlist is not, by itself, an independently authenticated trust root: it does not establish who authorized the mapping, signed update provenance, key rotation, revocation freshness, or anti-rollback guarantees. The candidate capability registry explicitly leaves records UNVERIFIED unless a trusted runtime bootstrap supplies a verifier. No trust configuration contents or secret values were read/exported.

## 7. Recovery and live model evidence

- Recovery plan: DESIGN ONLY. No production snapshot, restore rehearsal, or rollback rehearsal was performed.
- Live model E2E: NOT_ACCEPTED. Synthetic tests report zero observed model runs and do not prove provider identity, request/response provenance, repeatability, or model quality.
- CP0 historical source: `BLOCKED_INPUT`; original criteria provenance/equivalence remains unverified.
- Runtime/canonical remain unchanged. No restart, deploy, cutover, merge, or release.

## 8. Required gates before closure

1. Bind live source files and loaded runtime to a verifiable approved source commit/build attestation; reconcile the dirty detached `hg2-phone` process separately without altering it during this investigation.
2. Establish an independently authenticated trust root and documented authority, rotation, revocation, freshness, and anti-rollback policy.
3. Obtain verifiable CP0 historical source provenance or explicitly retain CP0 as blocked; do not infer equivalence from synthetic fixtures.
4. Conduct authorized live-model E2E with recorded model/provider identity, exact dataset/config/oracle digests, raw evidence custody, independent scoring, and regression thresholds.
5. Produce a consistent approved snapshot, isolate restore rehearsal, and tested rollback proof before any cutover.
6. Re-run required gates on the exact final candidate and verify CI, PR, canonical base, and runtime state again.

## 9. External methodology references

- CircleCI official documentation on retrieving job step output and metadata: https://circleci.com/docs/guides/orchestrate/analyze-pipelines-during-an-incident/
- SLSA build provenance specification: https://slsa.dev/spec/v1.0/provenance

These references guide evidence collection; they do not themselves attest this HG runtime.
