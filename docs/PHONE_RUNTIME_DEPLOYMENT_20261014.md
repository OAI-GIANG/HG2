# PHONE HG → HG2 Read-Only Connector — Deployment Evidence

Date: 2026-10-14 (UTC)
Target: Android/Termux PHONE, local HG runtime on loopback only.

## Deployment scope
- Runtime service: runit service `hg-runtime`; HTTP bind reported by the running process is `127.0.0.1:8787`.
- Runtime source: `/data/data/com.termux/files/home/hg/core/runtime/hg_runtime.py`.
- Connector source: `/data/data/com.termux/files/home/hg/core/runtime/github_hg2_readonly.py`.
- Capability registry: `/data/data/com.termux/files/home/.config/hg/capabilities/registry.json`.
- Backup/rollback directory: `/data/data/com.termux/files/home/hg/quarantine/hg2-readonly-20261014/` (mode 0700; backup files mode 0600; `ROLLBACK.sh` mode 0700).
- Original runtime source SHA-256: `697b3d03f523d70b4a83e9adff346d31045a8876c1ed9717a2afcbe37366fcd9`.
- Current runtime source SHA-256: `29e2f3cf7caac6d3d5b3820ab118a40a93ae44dc878ab6b50f4cc93cedf16253`.
- Current connector source SHA-256: `96872852a0b89da8cdd7c912eaa687fa58d47e9fc2a4a8512c39777af1347bb1`.
- Current capability registry SHA-256: `cd6ab3ba4d74266fc923cdcb3ad8dde9beb0e9a5df0e106bab30f0da049addf1`.
- Existing HG runtime state SHA-256 before and after all read tests: `392ce5f66c81ef7402bbc0992da2151dcc0b5db2ab822052058309f034481ecc` (unchanged).
- Active process observed during E2E: PID `7449`; the runtime reports module source SHA at startup and connector module SHA at import in the response.

## Capability scope
A new separate local record `github_hg2_public_read` was added. It permits only `commit.read` and `manifest.read` for `OAI-GIANG/HG2@hg-genesis`. `write_enabled=false`. Existing broad `github_access` record remains `REVOKED` and was not changed. The token was never included in output or evidence files.

## Production E2E evidence
At `2026-10-14T03:17:53.962874Z`, a request through the actual running HG service returned outer HTTP 200 and upstream commit/manifest HTTP 200. Commit SHA: `cdebaeed014371f033f14352f552c6d0d4e69198`; tree SHA: `fa986a20e8c5c091f930f66a653f4a41611c76b2`; manifest blob SHA: `f30da194e246dba2773125d074488a30912635eb`.

Three repeated E2E requests succeeded through the same PID with identical commit SHA, manifest blob SHA and source hashes. Detailed secret-free responses are in `docs/evidence/20261014/PHONE_RUNTIME_E2E_PROOF.json` and `PHONE_RUNTIME_STABILITY.json`.

Eight negative/method tests passed: wrong repo/ref, missing/duplicate query, POST/PATCH/DELETE (405) and PUT (501); relevant state SHA before/after was identical. Detailed results are in `PHONE_RUNTIME_NEGATIVE_GATES.json`.

Before adding the narrow grant, the same live route correctly returned HTTP 403 `CAPABILITY_NOT_AUTHORIZED`. After grant, it returned real GitHub metadata. Health after the controlled restart returned HTTP 200 and runit reported service running.

## Current status update — credential rejected / grant blocked (2026-10-14T03:29Z)

After earlier successful E2E requests, two subsequent calls returned HTTP 502 with safe error `GITHUB_CREDENTIAL_REJECTED` (03:28:32Z and 03:28:41Z). The live health endpoint continued to return HTTP 200. No further upstream retries were made after that determination. The narrow grant was locally set to `credential_state=UPSTREAM_REJECTED_401` and `runtime_state=BLOCKED`; the legacy broad `github_access` record remained `REVOKED` and unchanged. A local request after blocking returned HTTP 403 `CAPABILITY_NOT_AUTHORIZED`, and did not call upstream. The state hash remained unchanged. Registry after the fail-closed update SHA-256: `3275baf0a0d45c1ac0ba7a49cc8277af3df7fa5b7212bc1690b0f9ea1125dfa0`.

Therefore the successful E2E result above is a historical observed PASS, but current operational status is `BLOCKED_CREDENTIAL`, not currently functional. The upstream rejection reason and remote credential revocation status are not independently known. Do not restore the grant to READY/ACTIVE until an authorized valid credential is installed and verified without exposing its value. Secret-free evidence: `docs/evidence/20261014/PHONE_RUNTIME_AUTH_BLOCK_20261014.json`.

## Scope limitations / gates not closed
- This proves the new read-only endpoint in the running PHONE HG service, not full HG product/release readiness.
- The source SHA endpoint records the source-file hash at process startup; it is not a hardware-backed or cryptographic attestation of bytecode actually loaded.
- No reboot/power-loss or long-duration recovery test has been run.
- The previously broad `github_access` registry entry remains `REVOKED` with no evidence. It was not reactivated.
- Historical containment report says the old `.pth` bootstrap exposed unauthenticated file read/write routes. The hook is now absent and remains quarantined; remote revocation of the historically potentially exposed credential is not independently proven by this deployment.
- Audit verifier was corrected separately in the live toolplane source. The existing log was not edited. Read-only revalidation found 2,179 records: the first 669 are legacy unchained records and remain unverifiable for tamper evidence; the chained suffix starts at line 670 with `prev=GENESIS` and all 1,510 records validate with no hash/prev errors. The verifier now reports `chain_ok=true`, `bad=[]`, `legacy_prefix_records=669`, and `ok=false` for the whole file to avoid overstating integrity. Patch: `integration/hg_toolplane_audit_verifier.patch`; source SHA-256 before `2a6ac30caedc1e7edbefe3d2e5451993e1aef0464a21b97a42b732c98c678c2d`; after `9d1ff9cb744cab3d0257e59c1cf95fdfbf23e8af7bcf9dc5c0d70ea823ed217c`. Original audit log SHA-256 remains `6701cfa9d1bfeabe3ae538c3e1d2127d3c1695528ded2913b220abc8e346d88a` at the captured snapshot. The 669 legacy records are still not tamper-evident.
- Independent human security review is not obtained. Both PRs remain drafts; no canonical merge or release was performed.

## Rollback
The pre-deploy runtime, capability registry and run script are preserved in the backup directory. `ROLLBACK.sh` restores the pre-deploy runtime and registry, removes the new connector module and restarts only `hg-runtime`. Rollback has been authored but not executed.
