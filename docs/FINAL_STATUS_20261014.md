# HG/HG2 execution status — 2026-10-14

## Work actually performed on PHONE
- Added a narrow, standard-library connector `github_hg2_readonly.py` under the live HG runtime directory and a fixed `GET /api/hg2/read` route in `hg_runtime.py`.
- Added a separate local capability `github_hg2_public_read` for only `OAI-GIANG/HG2@hg-genesis`, actions `commit.read`/`manifest.read`, `write_enabled=false`. The older broad `github_access` remains `REVOKED` and was not modified.
- Pre-deploy backup and rollback assets were preserved under `~/hg/quarantine/hg2-readonly-20261014/`. No `.pth` hook was installed/reinstalled; historical hook remains quarantined.
- Corrected audit verifier semantics so it no longer misreports the legacy prefix as individual hash mismatches. No audit history records were rewritten.

## Verified success (historical, not current active state)
- Live HG runtime requests succeeded at `2026-10-14T03:17:53.962874Z`, three repeated requests in the following minute window, and again at `2026-10-14T03:25:25.629301Z` after verifier restart.
- Successful responses returned commit `cdebaeed014371f033f14352f552c6d0d4e69198`, tree `fa986a20e8c5c091f930f66a653f4a41611c76b2`, and manifest blob `f30da194e246dba2773125d074488a30912635eb`.
- Runtime source SHA-256: `29e2f3cf7caac6d3d5b3820ab118a40a93ae44dc878ab6b50f4cc93cedf16253`.
- Connector source SHA-256: `96872852a0b89da8cdd7c912eaa687fa58d47e9fc2a4a8512c39777af1347bb1`.
- Eight negative/method gates passed; relevant HG state hash before/after remained `392ce5f66c81ef7402bbc0992da2151dcc0b5db2ab822052058309f034481ecc`.
- Connector unit tests: 9/9 PASS with `ResourceWarning` treated as error. Audit verifier contract tests: 4/4 PASS under the same strict warning setting.

## Current operational status — BLOCKED_CREDENTIAL
At `03:28:32Z` and `03:28:41Z`, the live route returned HTTP 502 with safe error `GITHUB_CREDENTIAL_REJECTED`, meaning GitHub rejected the credential sent by the connector. Runtime health remained HTTP 200. No further upstream retries were made after this. The narrow capability was then locally changed to `credential_state=UPSTREAM_REJECTED_401`, `runtime_state=BLOCKED`; an endpoint check confirmed HTTP 403 `CAPABILITY_NOT_AUTHORIZED` locally without calling upstream. The broad `github_access` remains `REVOKED`.

Current state is not a stable working connector; the earlier E2E pass remains valid historical evidence only. Cause of the upstream rejection and exact remote credential/revocation state are not independently known. To resume, a valid authorized PHONE-local, read-only credential must be provided/reissued through a supported account security path. No credential value is included in this report or sent to VPS. The route remains fail-closed.

## Audit finding
Snapshot SHA-256 `6701cfa9d1bfeabe3ae538c3e1d2127d3c1695528ded2913b220abc8e346d88a`, 2,179 records. Lines 1–669 are legacy unchained records and cannot be proven tamper-evident. The chain starts at line 670 with `prev=GENESIS`; all 1,510 chained records verify with no hash/prev errors. Updated verifier reports `chain_ok=true`, `bad=[]`, `legacy_prefix_records=669`, while whole-file `ok=false` remains deliberately conservative. No audit entries were rewritten.

## GitHub artifacts / CI
- Red-team report PR #16: https://github.com/OAI-GIANG/HG2/pull/16 — OPEN DRAFT; latest reviewed CI status `ci/circleci: verify = success` for head `9c89c77c8880d505c75da078bf8d5972e7579911`.
- Connector/evidence PR #17: https://github.com/OAI-GIANG/HG2/pull/17 — OPEN DRAFT; latest reviewed CI status `ci/circleci: verify = success` for head `42ce22d6ecbf245c34b3366a61a2486c9b156fe7`.
- Both PRs target canonical `hg-genesis` at `cdebaeed014371f033f14352f552c6d0d4e69198`. No merge was performed; PRs have no independent reviewer assigned.

## Current gate decision
- `HG runtime health = PASS`
- `HG → HG2 read-only E2E = HISTORICAL PASS, CURRENTLY BLOCKED_CREDENTIAL`
- `AUDIT_CHAIN = PARTIAL (chained suffix verifies; legacy prefix unchained)`
- `OLD_CREDENTIAL_REVOCATION = NOT_VERIFIED`
- `REBOOT/POWER_LOSS_RECOVERY = NOT_RUN`
- `INDEPENDENT_HUMAN_REVIEW = NOT_OBTAINED`
- `HG → HG2 = BLOCKED_PENDING_CREDENTIAL_SECURITY_REVIEW`
- `RELEASE = BLOCKED`

No merge, release, deletion or canonical branch update was performed. The work cannot honestly be reported fully closed/stable until credential authority is resolved, recovery validation is completed and an independent reviewer signs the exact commits.

## Final hardening and CI update — 2026-10-14T03:39Z

- Added local bearer authentication for the loopback route. Route token is phone-local, mode 0600; unauthenticated call returns HTTP 401 `LOCAL_CAPABILITY_AUTH_REQUIRED`. The correct-bearer test after last restart was NOT_RUN because the permitted tool path was blocked; do not mark that gate PASS.
- The connector adds a process-local six-requests/minute rate limit; 10/10 tests pass with ResourceWarning treated as error. Audit verifier contract tests 4/4 pass.
- Active runtime PID 24729 health HTTP 200; anonymous route call HTTP 401. HG state SHA unchanged: `392ce5f66c81ef7402bbc0992da2151dcc0b5db2ab822052058309f034481ecc`. Registry SHA: `3275baf0a0d45c1ac0ba7a49cc8277af3df7fa5b7212bc1690b0f9ea1125dfa0`. Audit log SHA remains `6701cfa9d1bfeabe3ae538c3e1d2127d3c1695528ded2913b220abc8e346d88a`.
- Current runtime SHA `c9ce1337373007950b05c353bea14d2f2888d08ee5e7f34c5ca4003967c053ae`; connector SHA `913f23f4ecc41cf730cfa0484427c717ae9c3c1cefb55bc3ffa980ad11c6425d`; verifier SHA `9d1ff9cb744cab3d0257e59c1cf95fdfbf23e8af7bcf9dc5c0d70ea823ed217c`; rollback script SHA `5bf023d9f73d440b464715c4cdb6c03a9c46ad232274032a59f4e4132747cf5b`.
- PR #17 head `1564df97f6c9e1fc2e7ca66eecbf47b4eab4d497` CI `ci/circleci: verify = success` (CircleCI run 84); PR is draft, no reviewer assigned. PR #16 remains draft with no reviewer. No merge made.
- Local clone `/home/hg2-phone` HEAD `4d97c34d8bb7c1091265330aef63dd78d0e72c49` differs from remote `hg-genesis` `cdebaeed014371f033f14352f552c6d0d4e69198`. Treat as clone drift/branch tracking discrepancy; neither was changed by this task.

Current status remains `BLOCKED_CREDENTIAL`: GitHub returned `GITHUB_CREDENTIAL_REJECTED` on two requests and the narrow capability is still blocked. Historical E2E success is not current availability. Broad capability remains REVOKED. Old possibly exposed credential revocation, reboot recovery and independent human review remain outstanding.
