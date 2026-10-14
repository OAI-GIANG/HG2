# Runtime capability acceptance matrix (design only)

| Test ID | Scenario | Expected result | Actual status |
|---|---|---|---|
| CAP-01 | GET /api/health on PHONE | Liveness only; not capability proof | PASS for liveness only |
| CAP-02 | GET /api/github/status on live legacy runtime | Explicit configuration status | OBSERVED: configured=false |
| CAP-03 | Read exact ref/commit via live runtime | Real upstream commit/file SHA | NOT_RUN; route absent |
| CAP-04 | Capability registry revoked/unknown | Deny every capability action | Pure policy unit test PASS; live grant NOT_VERIFIED |
| CAP-05 | Repo/ref outside allowlist | Deny before upstream request | NOT_RUN on live runtime |
| CAP-06 | Missing/invalid credential | Fail closed, no fallback to public-read on authenticated route | NOT_RUN on live capability |
| CAP-07 | GET causes no state change | Before/after state hashes identical | NOT_RUN on exact live connector |
| CAP-08 | Runtime identity derived from live process | Bind PID/start time/module/build to evidence | PARTIAL; current probe created a separate PhoneRuntime instance |
| CAP-09 | Evidence/log secret scrub | No credential material appears | Spot checks only; full scan NOT_RUN |
| CAP-10 | Strict Android test suite | Exact-SHA tests pass, no ResourceWarning | Warning cleanliness FAIL: 32 assertions passed but ResourceWarnings observed |
| CAP-11 | Audit chain verified | Hash/prev chain valid or original warning separately handled | BLOCKED; reported mismatch from line 1 |
| CAP-12 | Independent review | Reviewer other than author signs exact SHA | NOT_OBTAINED |
