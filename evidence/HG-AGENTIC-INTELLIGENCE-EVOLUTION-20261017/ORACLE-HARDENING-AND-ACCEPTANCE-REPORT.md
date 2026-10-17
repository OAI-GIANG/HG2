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
- SLSA build provenance specification: https://slsa.dev/spec/v1.2/provenance
- SLSA artifact provenance verification: https://slsa.dev/spec/v1.2/verifying-artifacts

These references guide evidence collection; they do not themselves attest this HG runtime.


## 10. Follow-up read-only provenance and recovery rehearsal (2026-10-17)

### Runtime source provenance — refined finding

The top-level `~/hg` directory is not a Git root, but a nested repository exists at `~/hg/core`. Its observed HEAD is `03409311f184f2c3f110274a10cf1ac0afbc1b1a`, branch `fix/hg-p0-library-vision-20261010`, with 77 worktree status entries. The live `runtime/hg_runtime.py` is tracked in that repository but dirty:

- Committed HEAD blob SHA-256: `77062620e3490a77510fbf3dec74288869a22e26fab8845d5ea577320bafb8a1`.
- Current worktree/live-disk file SHA-256: `e02f344c11f0e513e4e874fdc35eb6c28ea76d8aa541da7bbde19a1427f10a83`.
- Diff against HEAD: 547 insertions and 43 deletions (590 changed lines); file mtime 2026-10-16 02:36:52 +0700.
- Live process PID 10809 command path: `~/hg/core/runtime/hg_runtime.py`.
- Backend source `~/hg/backend/hg_backend.py` and entrypoint `~/hg2-service/entry.py` are not inside Git repositories at their respective source paths. The latter's cwd repository `~/hg2-phone` is detached at `4d97c34d8bb7c1091265330aef63dd78d0e72c49` with 17 worktree status entries.
- Runtime source digest endpoint is behind a PHONE-local bearer capability whose value was intentionally not read. Therefore, the digest of the source loaded by the live process is not independently attested here.

This refines, rather than clears, the previous finding: disk files and their source-control relationships are now better mapped, but the loaded runtime is still not bound to the approved candidate or to a clean, approved source commit. Runtime provenance remains `BLOCKED_MISMATCH`.

### Isolated recovery lab — limited PASS

A consistent SQLite online backup was created from the phone-local backend database using a read-only source connection. The source database path was derived by reading only the non-secret `HG_BACKEND_DATA` path variable from the running process; no other environment values were inspected. The snapshot and restore rehearsal remained inside the private Termux cache.

- Snapshot SHA-256: `5e20def72cd36fe3209fc48dce9a12e55e806a87eb2f27a167d52e439c2d17df`.
- Snapshot `PRAGMA integrity_check`: `ok`; seven application tables.
- Snapshot-to-lab-restore SHA-256: identical; byte-for-byte comparison PASS.
- A separate eight-file source/launcher snapshot excluded environment files, keys, credentials, tokens and database content; all source-copy and restore-copy SHA-256 comparisons PASS.
- Evidence manifests are stored locally, not committed, under `~/.cache/hg-evidence-first-20261017/recovery-lab/`. Directory mode is 0700 and snapshot/evidence files are 0600.

Evidence manifest digests:
- `snapshot-restore-evidence.json`: `cf521d86a18990fe721a1f7593dbf598d4ee310589f8e5a566d97bbd06f50065`.
- `source-snapshot-restore-evidence.json`: `ee60f1cecba742115d677f00b643949cd5fe050b03599ef4b7c74e81a81d38bc`.

This is a **database and source-file integrity rehearsal only**. It is not proof of full service restoration, credential/key restoration, loaded-process provenance, end-to-end recovery, or production rollback. No service restart, production database write, cutover or deployment was performed.

### Trust root and CP0 follow-up

The runtime plugin trust implementation reads a local registry mapping plugin IDs to SHA-256 manifest digests. The inspected code contains no independent signature-verification path, public-key identity, registry expiry/freshness check, or revocation/anti-rollback protocol. A configured registry is not equivalent to an authenticated trust root. Secret registry contents were not read.

The local HNIF2-18 fixture explicitly states that the historical 26-criteria source is unresolved and that a native draft is not historical. Repository search and public web search did not yield a verifiable primary source. CP0 remains `BLOCKED_INPUT`; the fixture is evidence of the missing-source condition, not proof of historical equivalence.

### Live model E2E decision

The candidate provider has a credential loader that enforces a private regular file and a fixed official HTTPS host, but the configured credential contents were not inspected and no provider call was made. The runtime source is not bound to an approved commit, and the current provider interface does not preserve sufficient independent request/response attestation for a full HG runtime E2E. Therefore live model E2E remains `NOT_ACCEPTED / NOT_RUN` rather than producing an incomplete or misleading pass.

### Updated recovery/closure gate

- Local SQLite snapshot + isolated restore hash rehearsal: `PASS_LIMITED_SCOPE`.
- Source/launcher snapshot + isolated restore hash rehearsal: `PASS_LIMITED_SCOPE`.
- Full service/system recovery and rollback proof: `BLOCKED`.
- Runtime provenance: `BLOCKED_MISMATCH`.
- Trust root / authority / revocation: `BLOCKED`.
- CP0: `BLOCKED_INPUT`.
- Live model E2E: `NOT_RUN`.
- PR #21: remain OPEN Draft; no merge, deployment, release or close.
