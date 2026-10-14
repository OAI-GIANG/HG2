# Runtime capability acceptance matrix (design only)

| Test ID | Scenario | Expected result | Actual status |
|---|---|---|---|
| CAP-01 | GET /api/health on PHONE | Liveness only; not capability proof | PASS for liveness only |
| CAP-02 | GET /api/github/status on live legacy runtime | Explicit configuration status | OBSERVED: configured=false |
| CAP-03 | Read exact ref/commit via live runtime | Real upstream commit/file SHA | HISTORICAL PASS (3 repeats + post-restart request); later upstream 401, narrow grant now BLOCKED_CREDENTIAL |
| CAP-04 | Capability registry revoked/unknown | Deny every capability action | PASS: broad grant remains REVOKED; narrow grant runtime_state=BLOCKED, route returned 403 without upstream call |
| CAP-05 | Repo/ref outside allowlist | Deny before upstream request | PASS: wrong repo 403; wrong ref 403 |
| CAP-06 | Missing/invalid credential | Fail closed, no fallback to public-read on authenticated route | Unit tests PASS; live invalid-credential runtime mutation test NOT_RUN |
| CAP-07 | GET causes no state change | Before/after state hashes identical | PASS: state SHA unchanged in E2E/negative/stability runs |
| CAP-08 | Runtime identity derived from live process | Bind PID/start time/module/build to evidence | PARTIAL PASS: live PID/starttime/source hashes reported; not bytecode attestation |
| CAP-09 | Evidence/log secret scrub | No credential material appears | Spot checks only; full scan NOT_RUN |
| CAP-10 | Narrow connector tests | Exact-SHA tests pass with warnings treated as errors | PASS: 9/9; broader unrelated suite still emitted ResourceWarnings |
| CAP-11 | Audit chain verified | Legacy prefix and chained suffix accurately distinguished | PARTIAL: 1,510-record suffix verifies; 669 legacy records are unchained and whole-file `ok=false` remains |
| CAP-12 | Independent review | Reviewer other than author signs exact SHA | NOT_OBTAINED; PR #16/#17 remain draft, no reviewer requested/assigned |
| CAP-13 | Old potentially exposed credential is revoked at GitHub | Verifiable non-secret revocation evidence | BLOCKED / NOT_VERIFIED |
| CAP-14 | Historical `.pth` bootstrap remains quarantined | Active site-packages hook absent; quarantine hash matches original | PASS: hook absent, quarantine hash matches |
| CAP-15 | Reboot/power-loss recovery | Connector and grant survive safe recovery; no data corruption | NOT_RUN |
| CAP-16 | Upstream credential rejection | Fail closed and prevent further upstream calls | PASS: two 502/GITHUB_CREDENTIAL_REJECTED observations, then local 403/CAPABILITY_NOT_AUTHORIZED after grant blocked |
