# HG/HG2 Independent Red-Team Review & Plan Revision

**Status:** red-team review and integration evidence updated 2026-10-14; narrow PHONE → HG2 read-only route is live-verified. Full release remains BLOCKED by unresolved security, audit and independent-review gates.
**Canonical repository:** `OAI-GIANG/HG2`
**Canonical branch:** `hg-genesis`
**Baseline used for this review branch:** `cdebaeed014371f033f14352f552c6d0d4e69198`
**Review date:** 2026-10-14

## 1. Executive decision

Do not merge, deploy, delete or change canonical state on the basis of this review package. Available evidence proves an Android/Termux checkout and a running legacy HG HTTP runtime, but not a deployed GitHub connector loaded into that runtime.

Gate status:
- `HG → HG2 = BLOCKED`
- `RELEASE = BLOCKED`
- `PHONE_IDENTITY_SOURCE = PARTIALLY_OBSERVED`
- `GITHUB_HG2_PUBLIC_READ = HISTORICAL_E2E_PASS; CURRENT_BLOCKED_CREDENTIAL`
- `LEGACY_GITHUB_ACCESS = REVOKED (unchanged)`
- `PHONE_RUNTIME_NEGATIVE_GATES = 8/8 PASS`
- `PHONE_RUNTIME_STABILITY = 3/3 repeated requests passed during earlier window; later upstream credential rejection means current E2E is blocked`
- `AUDIT_INTEGRITY = WARNING / NOT_RESOLVED`
- `INDEPENDENT_EXTERNAL_REVIEW = NOT_OBTAINED`

## 2. Evidence classification

### OBSERVED from Android/Termux via Remote Desktop Commander

- Device platform Android, ARM64, Python 3.14.6.
- Runtime processes include:
  - `python3 -u /data/data/com.termux/files/home/hg/core/runtime/hg_runtime.py`
  - `python3 -u /data/data/com.termux/files/home/hg2-service/entry.py`
- Service `hg-runtime` is supervised and `127.0.0.1:8787/api/health` returns HTTP 200.
- Legacy runtime `/api/github/status` returns `configured=false, mode=public-read`.
- Legacy runtime `GET /api/github/repo/OAI-GIANG/HG2` succeeds for public repository metadata; this is not authenticated private-scope proof and does not fetch arbitrary ref content.
- Legacy route `GET /api/github/repo/OAI-GIANG/HG2/contents/manifest.json` remains absent. A separate narrow `/api/hg2/read` endpoint was added to the live legacy HG process and now reads commit + manifest metadata for the exact allowlisted ref.
- The `hg2-runtime` run script starts `hg2-service/entry.py`; that file constructs `PhoneRuntime` from `hg2-phone/hg/phone_runtime.py` then sleeps. It does not expose HTTP endpoints or invoke GitHub.
- Local capability registry reports `runtime_state=READY`, `revocation_state=REVOKED`, and empty evidence list. This local snapshot is not an authoritative proof of the external authority provider’s state.
- `~/.config/hg/github_token` metadata shows mode 0600 and 40 bytes. Token contents were not emitted. A separate in-process GET-only probe verified the current file credential against GitHub as `OAI-GIANG` with `public_repo` scope; this does not prove the HG service consumes it.
- Historical containment evidence states a Python `.pth` startup hook previously executed `~/hg/hgcap-.py`; its `/api/capability/readfile` and `/api/capability/writefile` paths did not call `_need_token` before operating. The hook is now absent from site-packages and its quarantined copy matches recorded original SHA-256 `ca78ce8e1aaf4d86f5a229e74b3f4f48a62a2e50f06146647730c24072cf7dd1`. The payload remains preserved but inert via that hook. The old token may have been exposed; remote revocation of that credential has not been independently verified.
- The local registry still records old credential fingerprint prefix `c480e1745d8549e1`, while the current file credential's SHA-256 prefix differs; registry state has `revocation_state=REVOKED` and no evidence entries. Do not rewrite registry to make this appear resolved.
- A read-only probe instantiated `PhoneRuntime(state_dir=~/hg2-state)`, returned runtime ID `8577fe1012cc4182a8e7c5ab755cb4ce` and integrity true for one event. This was an in-process diagnostic against the local checkout/state; it is not proof that the service process loaded that module or that a production GitHub request succeeded.
- Source hashes from the `hg2-phone` working tree:
  - `hg/phone_runtime.py`: `4a788efdbe0427ca36f8d497073dcdbab55b87c70b418dafa7a8373345751b22`
  - `hg/authority.py`: `1531473ebe1f3534a91bb9c992ae8bf7d6944f5f6ce5ebcb48008d8267572068`
  - `hg/history.py`: `77e188d73c82668dcce5b89f2cfd9470d8ee75dffd103c86d2818e9f4f05fbbc`
  - `hg/identity.py`: `128211f8cb18cf8f8359721097244fe5fcc008b41cbb6b73dac64ee61e68a227`
  - `hg/edge.py`: `e38b44150b258a6ad8bbab2c7791822a16b887af1651f32a1952948348dda7bb`
  - `manifest.json`: `748649af5d45e10d7df322e430aa01240a6f303c5f2bcb6a363aa5cf8c221abf`
- Isolated local authority-policy tests passed 9/9. The broader candidate suite passed 32/32 assertions but emitted multiple ResourceWarnings from test helpers; not warning-clean.

### OBSERVED from GitHub API

- Repository `OAI-GIANG/HG2` is public and its default branch is `hg-genesis`.
- Remote `hg-genesis` currently points to `cdebaeed014371f033f14352f552c6d0d4e69198`, whereas historic task reports refer to `d11e71ed8b34338b8568664b39bc777c926826d5`. Do not force-update refs or assume these baselines are interchangeable.
- Canonical manifest blob SHA (Git blob ID) is `f30da194e246dba2773125d074488a30912635eb`; its contents specify package `hg`, version `1.0.0`, modules `hg.identity`, `hg.authority`, `hg.history`, `hg.phone_runtime`, `hg.edge`, origin `clean_room`.
- Canonical `hg/phone_runtime.py` blob SHA is `75fa6bcda1e29bf08aeb5341dbe8f0e124684199`; canonical `hg/authority.py` blob SHA is `a9fb1ddae181944e2e87decb806368e916ac6379`. These modules do not implement the GitHub connector routes needed for ref/content proof.
- Open PR #11 remains a candidate, not release certification; its description leaves production credential verifier, VPS/HTTPS/device E2E, power-loss recovery, external consumer inventory and global runtime identity/build attribution unresolved.
- Open PR #15 remains draft and says its static import-analysis tool is not integrated into the phone runtime; independent review, representative production-repository ground-truth benchmark and provenance gates remain blocked.

### NEW OBSERVED — Live PHONE runtime E2E after narrow integration

- Active `hg-runtime` process PID `7449` returned `GET /api/hg2/read?repo=OAI-GIANG/HG2&ref=hg-genesis` with HTTP 200.
- Both upstream GitHub GETs returned HTTP 200. Commit SHA `cdebaeed014371f033f14352f552c6d0d4e69198`; tree SHA `fa986a20e8c5c091f930f66a653f4a41611c76b2`; manifest blob SHA `f30da194e246dba2773125d074488a30912635eb`.
- Three repeated requests in the initial verification window returned identical commit/manifest SHA values through one PID; eight negative/method gates passed; state hash stayed unchanged.
- After the audit verifier restart, one more E2E request passed at `03:25:25Z`. However, two later requests at `03:28:32Z` and `03:28:41Z` returned HTTP 502 / `GITHUB_CREDENTIAL_REJECTED` while runtime health stayed 200.
- Fail-closed response: the narrow local grant was changed to `credential_state=UPSTREAM_REJECTED_401`, `runtime_state=BLOCKED`; route then returned HTTP 403 `CAPABILITY_NOT_AUTHORIZED` without an upstream call. Registry SHA-256 after block: `3275baf0a0d45c1ac0ba7a49cc8277af3df7fa5b7212bc1690b0f9ea1125dfa0`.
- The separate `github_hg2_public_read` grant is currently BLOCKED, and allows only `commit.read` and `manifest.read` when reauthorized; `write_enabled=false`. The previous broad `github_access` record remains `REVOKED` and unchanged.
- Runtime source SHA-256: `29e2f3cf7caac6d3d5b3820ab118a40a93ae44dc878ab6b50f4cc93cedf16253`; connector SHA-256: `96872852a0b89da8cdd7c912eaa687fa58d47e9fc2a4a8512c39777af1347bb1`.
- Detailed evidence is recorded in PR #17 under `docs/evidence/20261014/` and `docs/PHONE_RUNTIME_DEPLOYMENT_20261014.md`.

### NEW OBSERVED — Audit chain verifier forensic correction

- Audit file snapshot SHA-256: `6701cfa9d1bfeabe3ae538c3e1d2127d3c1695528ded2913b220abc8e346d88a`; 2,179 records.
- Lines 1–669 are legacy records without `h`/`prev`, so they are not tamper-evident.
- Hash chain starts line 670 (`prev=GENESIS`); all 1,510 chained records verify under the writer's exact serialization rule, with `bad=[]`.
- Verifier was patched to distinguish this prefix from the chain. Whole-file `ok` remains `false`; `chain_ok=true`; no audit records were edited.
- The change and four tests are in PR #17 (`integration/hg_toolplane_audit_verifier.patch`, `tests/test_audit_chain_legacy_prefix.py`).

### NOT_EXPOSED / NOT_VERIFIED

- Whether the running `hg-runtime` service has any GitHub connector module injected.
- An attestation tying source/build identity to the live service process.
- Current accepted GitHub credential and recovery/reauthorization path; later upstream requests received 401.
- Reboot/power-loss recovery and long-duration stability of the new route.
- Authoritative capability-revocation reason or fresh active grant from the authority provider.
- Remote revocation status of the old potentially exposed credential. Current token GET success is a separate credential and does not prove the old token/app is revoked.
- Clean audit integrity. Previous reports indicate hash/prev mismatch from line 1; this task did not repair or rewrite that log.
- Independent external reviewer approval.

## 3. Red-team findings

### RT-01 — False equivalence between health and capability (mitigated for narrow read path)
A successful `/api/health` establishes liveness only. This risk is partly mitigated for the exact narrow GitHub read because the running HG process now exposes `/api/hg2/read`, returns process/source metadata and passed live E2E checks. It does not establish overall HG release readiness.

**Status:** MITIGATED FOR NARROW READ PATH; broader capabilities remain unverified.
**Residual action:** keep capability grants separate; never infer capability from health alone.

### RT-02 — Capability state conflict and upstream credential rejection
At initial deployment the registry's broader `github_access` was `REVOKED` while the runtime lacked the route. A new narrow grant enabled successful E2E, but the upstream later returned `GITHUB_CREDENTIAL_REJECTED`. The narrow grant has now been locally fail-closed as `runtime_state=BLOCKED`, `credential_state=UPSTREAM_REJECTED_401`; the broad grant remains `REVOKED`.

**Severity:** P0 current operational blocker.
**Remediation:** do not retry upstream or set the grant back to READY until an authorized valid credential/authority state is provided. The exact remote cause/revocation status remains unverified.

### RT-03 — Capability lifecycle (implemented, currently blocked)
The phone-local adapter reads the private token in-process, validates file ownership/permissions, and accepts only a separate narrow repo/ref grant. It succeeded through the actual HG runtime, then GitHub rejected the credential on later requests. The narrow grant is now locally blocked, and further upstream requests cease until credential recovery.

**Status:** IMPLEMENTED and historically E2E-verified; CURRENTLY BLOCKED_CREDENTIAL.
**Residual action:** reconcile credential state without exposing token contents; keep the old broad `github_access` record REVOKED.

### RT-04 — Source hash is not runtime attestation
Hashing a file on disk and calling a new `PhoneRuntime` verifies the checkout/diagnostic instance, not the module loaded into a long-running process.

**Severity:** P1 assurance gap.
**Remediation:** record process identity, start time, module path, artifact hash and build revision. If live module bytes cannot be measured, disclose that limitation rather than claiming strong attestation.

### RT-05 — Authority recovery must remain fail-closed
The isolated `hg/github_authority.py` is a pure policy gate: exact repository, authentication, verified credential, active state, explicit action grant, remediation refs for mutations and additional approval/manual-executor constraints. Its 9 unit tests prove only the policy. The module does not call APIs and is not wired into production.

**Severity:** P0 integration gap.
**Remediation:** keep this as design/test evidence until external authority is freshly verified and a separate reviewer approves any integration. Local tests must never mutate runtime grants.

### RT-06 — Legacy audit prefix is not tamper-evident; chained suffix now verifies
Read-only forensic analysis observed 2,179 records. Lines 1–669 use a legacy schema without `h`/`prev`; they cannot be proven tamper-evident. Line 670 starts the hash chain with `prev=GENESIS`. Recomputing hashes using the writer's `json.dumps(record, sort_keys=True)` rule verified all 1,510 chained records through line 2,179 with zero hash/prev mismatches. The earlier verifier incorrectly applied the chained schema to the unchained legacy prefix, causing a misleading mismatch-from-line-1 report.

**Severity:** P1 historical auditability gap; verifier behavior corrected on PHONE.
**Remediation/status:** the active verifier now reports `chain_ok=true`, `bad=[]`, `legacy_prefix_records=669`, `chained_records=1510`, `chain_start_line=670`, while keeping whole-file `ok=false`. Original audit data was not rewritten. Current snapshot SHA-256: `6701cfa9d1bfeabe3ae538c3e1d2127d3c1695528ded2913b220abc8e346d88a` (2,179 records). The legacy prefix still lacks tamper evidence and remains a release caveat. Four verifier contract tests pass, covering valid chained suffix after legacy prefix and corruption/prev/missing-hash failure cases.

### RT-08 — Historical unauthenticated capability bootstrap exposed file access
A previously active Python `.pth` startup hook executed a separate payload. The saved security-containment report records that the payload's file read/write routes failed to authenticate before operating. The original hook is absent and a hash-matching copy remains quarantined. Historical credential exposure remains plausible; remote revocation is not independently verified. The latest upstream 401 further means current credential validity is also not established.

**Severity:** P0 credential and capability-lifecycle risk.
**Remediation:** keep the `.pth` hook disabled and payload inert; do not reinstall it. Confirm/revoke the historical credential at GitHub through supported account controls; record non-secret evidence and keep the broad registry grant fail-closed. Use explicit, reviewed integration code instead of a broad startup hook.

### RT-07 — Canonical/branch drift and open PR accumulation
Remote `hg-genesis` is `cdebaeed014371f033f14352f552c6d0d4e69198`; historic reports refer to `d11e71e…`. Multiple open PRs contain distinct work. Merging any one PR does not prove capability activation or stable production operation.

**Severity:** P1 governance risk.
**Remediation:** keep canonical untouched. Select one candidate only after exact-base review; do not bundle unrelated creative-assimilation, CTI or sync work into this blocker fix.

## 4. Minimal plan to unblock

### Gate A — Capability ownership
- Identify the exact runtime process and component authorized to install code on PHONE.
- Do not install `.pth` startup loaders or run a persistent bootstrap unless the code path is explicitly approved and a backup/rollback is defined.
- If authorized activation is unavailable, mark `BLOCKED_CAPABILITY` and name the owner-mediated action.

### Gate B — Fresh authority proof
- Use phone-local credentials only inside private storage/process; do not print, copy or export them.
- Do not publish a full token fingerprint; use only a short non-secret identifier if needed in local evidence.
- Verify authenticated user and effective repository read scope through the runtime's own transport, without writes.
- Resolve `REVOKED` through the actual authority provider. Never alter local registry metadata to fake activation.

### Gate C — Runtime/process identity
- Collect live PID, process start time/command, actual module path, expected source hash, build revision and state directory.
- Verify integrity against the configured HG2 state; a temporary test store is not production state evidence.
- Preserve dirty/untracked checkout artifacts; do not clean them as part of this task.

### Gate D — End-to-end read
- Make one read-only request through the actual HG2 phone runtime to `OAI-GIANG/HG2`, ref `hg-genesis`.
- Response must include the real GitHub commit SHA or file/blob SHA, not merely repository metadata.
- Capture UTC timestamp, runtime ID, source/build identity, endpoint, status, ref, returned SHA, response hash and evidence-bundle hash. Exclude tokens, authorization headers and cookies.

### Gate E — Negative/security checks
- Wrong repository/ref is denied before upstream request.
- Missing/invalid credentials are denied; no public-read fallback for requests marked authenticated.
- Mutation endpoints are absent or explicitly denied.
- No credential in response/log/evidence.
- GET causes no state mutation; compare relevant state hashes before/after.

### Gate F — Independent review and operational stability
- A reviewer distinct from author/STT must inspect the exact SHA and evidence. External reviewer approval has not been obtained.
- Run exact-SHA tests on clean checkout and actual Android/Termux; treat ResourceWarnings as failures for strict verification.
- Run reconnect/outage and reboot-persistence tests only after safe staging and rollback definition.
- Claim stability only after repeated observations and relevant failure/recovery checks; one health check is insufficient.

## 5. Owner/operator decisions required

1. Approve the exact in-phone capability installation/reboot mechanism if an authorized activation path is absent. Broad repository write authority alone is not the same as device-level installation authorization.
2. Revoke/confirm the status of the historical potentially exposed credential through GitHub account controls. The current public-read credential and narrow grant are not proof the old credential is revoked. Keep legacy broad `github_access` REVOKED.
3. Arrange an independent reviewer or acknowledge that the independent-review gate remains blocked.
4. Any production service restart/deletion requires a verified target, dependency assessment and rollback path. Device access alone does not prove destructive changes are safe.

## 6. Acceptance criteria for release

All must be evidenced:
- Runtime identity is derived from the real PHONE service process, not a separate diagnostic instance.
- Fresh external authority is active and bound to exact repository/action scope.
- One real read-only request traverses the running PHONE HG runtime to GitHub and retrieves the expected ref/commit/manifest metadata. **This criterion now passes for the narrow read path.**
- Source/provenance and evidence hashes are reproducible and secret-free.
- Negative gates deny out-of-scope access and mutations.
- Audit/history warnings are addressed or formally bounded so release evidence remains trustworthy.
- Independent review records the exact SHA reviewed.
- Exact-SHA tests pass with no warnings and relevant operational recovery checks pass.

**Current distinction:** `HG → HG2 public-read path = HISTORICALLY E2E-VERIFIED, CURRENTLY BLOCKED_CREDENTIAL`; broader `HG → HG2 = BLOCKED_PENDING_SECURITY_AND_REVIEW_GATES`; `RELEASE = BLOCKED`.

## 7. References
- SLSA Provenance v1.2: https://slsa.dev/spec/v1.2/provenance
- NIST Secure Software Development Framework SP 800-218: https://csrc.nist.gov/pubs/sp/800/218/final
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- GitHub REST repository contents API: https://docs.github.com/en/rest/repos/contents


## Final status update — 2026-10-14T03:40Z

- Local endpoint hardening is deployed: separate phone-local bearer token (0600), loopback caller check, constant-time comparison, and six-read/minute rate limit.
- After controlled restart the service is alive (PID 24729, health HTTP 200). Unauthenticated /api/hg2/read returns HTTP 401 LOCAL_CAPABILITY_AUTH_REQUIRED.
- Valid local-bearer check after the final restart is NOT_RUN because the safe tool path to provide it was blocked. It must not be marked PASS.
- The narrow grant remains runtime_state=BLOCKED, credential_state=UPSTREAM_REJECTED_401; no further upstream call was made. State SHA remains 392ce5f66c81ef7402bbc0992da2151dcc0b5db2ab822052058309f034481ecc.
- PR #17 head f852bc768290fb2606586b1946a7016140a9371b has CircleCI run 85 success. PR #16 and #17 remain draft; there are no requested reviewers.
- Remote canonical hg-genesis remains cdebaeed014371f033f14352f552c6d0d4e69198; local clone hg2-phone HEAD 4d97c34d8bb7c1091265330aef63dd78d0e72c49 differs. No canonical branch push was made.

Final gate: HG runtime health = PASS; HG -> HG2 = BLOCKED_CREDENTIAL / REVIEW_PENDING; RELEASE = BLOCKED.


## Final status update - 2026-10-14T03:40Z

- Local endpoint hardening is deployed: separate phone-local bearer token (0600), loopback caller check, constant-time comparison, and six-read/minute rate limit.
- After controlled restart the service is alive (PID 24729, health HTTP 200). Unauthenticated /api/hg2/read returns HTTP 401 LOCAL_CAPABILITY_AUTH_REQUIRED.
- Valid local-bearer check after the final restart is NOT_RUN because the safe tool path to provide it was blocked. It must not be marked PASS.
- The narrow grant remains runtime_state=BLOCKED, credential_state=UPSTREAM_REJECTED_401; no further upstream call was made. State SHA remains 392ce5f66c81ef7402bbc0992da2151dcc0b5db2ab822052058309f034481ecc.
- PR #17 head f852bc768290fb2606586b1946a7016140a9371b has CircleCI run 85 success. PR #16 and #17 remain draft; there are no requested reviewers.
- Remote canonical hg-genesis remains cdebaeed014371f033f14352f552c6d0d4e69198; local clone hg2-phone HEAD 4d97c34d8bb7c1091265330aef63dd78d0e72c49 differs. No canonical branch push was made.

Final gate: HG runtime health = PASS; HG -> HG2 = BLOCKED_CREDENTIAL / REVIEW_PENDING; RELEASE = BLOCKED.
