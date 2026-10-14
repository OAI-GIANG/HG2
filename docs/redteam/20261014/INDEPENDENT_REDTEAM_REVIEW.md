# HG/HG2 Independent Red-Team Review & Plan Revision

**Status:** design/evidence handoff only; production remains BLOCKED.
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
- `GITHUB_CAPABILITY = NOT_LOADED / REVOKED_IN_LOCAL_REGISTRY`
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
- `GET /api/github/repo/OAI-GIANG/HG2/branches` and `.../contents/manifest.json` return 404 (routes not implemented).
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

### NOT_EXPOSED / NOT_VERIFIED

- Whether the running `hg-runtime` service has any GitHub connector module injected.
- An attestation tying source/build identity to the live service process.
- Successful read of commit/ref/content through the HG runtime (as distinct from GitHub direct access or public repository metadata).
- Authoritative capability-revocation reason or fresh active grant from the authority provider.
- Remote revocation status of the old potentially exposed credential. Current token GET success is a separate credential and does not prove the old token/app is revoked.
- Clean audit integrity. Previous reports indicate hash/prev mismatch from line 1; this task did not repair or rewrite that log.
- Independent external reviewer approval.

## 3. Red-team findings

### RT-01 — False equivalence between health and capability
A successful `/api/health` establishes liveness of the legacy runtime only. It does not establish that GitHub capability code is installed and authorized.

**Severity:** P0 blocker.
**Remediation:** verify the exact capability endpoint in runtime code/build, then test the actual endpoint. If the loader is absent, request a minimal owner-authorized installation process. Do not simulate on VPS.

### RT-02 — Contradictory capability state
The local registry says `runtime_state=READY` while `revocation_state=REVOKED` and `evidence=[]`. The live runtime reports GitHub `configured=false`.

**Severity:** P0 blocker.
**Remediation:** fail closed. Reconcile through the actual authority provider with fresh evidence; never edit the local registry merely to claim ACTIVE. Treat registry metadata as advisory until reconciled.

### RT-03 — Capability lifecycle is not closed
The existence of a token file is not proof the runtime uses it. The current phone runtime reads `GITHUB_TOKEN` from process environment; the documented private token file is not loaded by this code. The public repository metadata route does not fetch a branch's commit/content.

**Severity:** P0 blocker.
**Remediation:** use an explicit authorized phone-side activation process. Add only the required read-only adapter and bind it to a separate grant and explicit repository/ref allowlist. No arbitrary URL, unrestricted owner, write, push, merge or delete.

### RT-04 — Source hash is not runtime attestation
Hashing a file on disk and calling a new `PhoneRuntime` verifies the checkout/diagnostic instance, not the module loaded into a long-running process.

**Severity:** P1 assurance gap.
**Remediation:** record process identity, start time, module path, artifact hash and build revision. If live module bytes cannot be measured, disclose that limitation rather than claiming strong attestation.

### RT-05 — Authority recovery must remain fail-closed
The isolated `hg/github_authority.py` is a pure policy gate: exact repository, authentication, verified credential, active state, explicit action grant, remediation refs for mutations and additional approval/manual-executor constraints. Its 9 unit tests prove only the policy. The module does not call APIs and is not wired into production.

**Severity:** P0 integration gap.
**Remediation:** keep this as design/test evidence until external authority is freshly verified and a separate reviewer approves any integration. Local tests must never mutate runtime grants.

### RT-06 — Audit integrity warning
`audit_tail` reported hash/prev mismatch from line 1, and record counts differed between observations. Current conclusions do not rely on that log as a sole source of truth.

**Severity:** P1 auditability issue.
**Remediation:** preserve the original log; acquire a byte-identical forensic copy; hash it; independently validate hash algorithm, genesis rule and schema; publish a new report, never rewrite old events.

### RT-08 — Historical unauthenticated capability bootstrap exposed file access
A previously active Python `.pth` startup hook executed a separate payload. The saved security-containment report records that the payload's file read/write routes failed to authenticate before operating. The original hook is currently absent and a hash-matching copy remains quarantined. The old token may have been exposed; remote revocation is not verified. The current file credential successfully authenticates for public repository GETs, but that alone does not prove the old credential is revoked or that the runtime is using the current token.

**Severity:** P0 credential and capability-lifecycle risk.
**Remediation:** keep the `.pth` hook disabled and payload inert; do not reinstall it. Confirm/revoke the old credential at GitHub through a supported account-authority path, record non-secret evidence, and keep registry state fail-closed until the authority source and credential lifecycle are reconciled. Use explicit, reviewed integration code instead of a broad startup hook.

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
2. Revoke/confirm status of the historical potentially exposed credential through GitHub account controls; separately restore/confirm external GitHub authority and reconcile the `REVOKED` registry state through the actual authority provider. Do not treat the newly verified public-read credential as proof the old credential is revoked.
3. Arrange an independent reviewer or acknowledge that the independent-review gate remains blocked.
4. Any production service restart/deletion requires a verified target, dependency assessment and rollback path. Device access alone does not prove destructive changes are safe.

## 6. Acceptance criteria for release

All must be evidenced:
- Runtime identity is derived from the real PHONE service process, not a separate diagnostic instance.
- Fresh external authority is active and bound to exact repository/action scope.
- One real read-only request traverses the running PHONE HG runtime to GitHub and retrieves the expected ref/commit/content.
- Source/provenance and evidence hashes are reproducible and secret-free.
- Negative gates deny out-of-scope access and mutations.
- Audit/history warnings are addressed or formally bounded so release evidence remains trustworthy.
- Independent review records the exact SHA reviewed.
- Exact-SHA tests pass with no warnings and relevant operational recovery checks pass.

**Until then:** `HG → HG2 = BLOCKED`; `RELEASE = BLOCKED`.

## 7. References
- SLSA Provenance v1.2: https://slsa.dev/spec/v1.2/provenance
- NIST Secure Software Development Framework SP 800-218: https://csrc.nist.gov/pubs/sp/800/218/final
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- GitHub REST repository contents API: https://docs.github.com/en/rest/repos/contents
