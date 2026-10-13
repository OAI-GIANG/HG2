# HG2 × Hexis — Selective Absorption Report

**Status:** `MERGED INTO HG2 CANONICAL VIA PR #9 / POST-MERGE TESTS PASS`
**Date:** 2026-10-13
**Canonical repository:** `OAI-GIANG/HG2`
**Canonical branch:** `hg-genesis`
**Canonical base commit:** `d11e71ed8b34338b8568664b39bc777c926826d5`
**Canonical base tree:** `1a2ee9b52b39feabd50a9a86f66140a85b1b38a6`

## 1. Source identity and provenance

- Inspected archive: `Hexis-main.zip`
- SHA-256: `9f2a1f3306486c83b5886577666e4b2a464da0521fbfc3567e524e9f65d436ef`
- Package metadata identifies `@bevel-software/platform-mcp-core` version `0.28.1`, repository `Bevel-Software/Hexis`, license `Apache-2.0`.
- The archive contains no Git metadata. The exact upstream commit represented by the archive is **UNKNOWN**; archive-to-upstream commit equivalence is **NOT VERIFIED**.
- No Hexis implementation code was copied into HG2. This change adapts an inspected engineering principle; it does not claim provenance or equivalence for an upstream Hexis revision.

Inspected source and tests include:
- `packages/mcp-core/src/call-guards.ts`
- `packages/mcp-core/src/dispatch.ts`
- `packages/mcp-core/src/session-recovery.ts`
- `packages/mcp-core/src/__tests__/call-guards.test.ts`
- `packages/mcp-core/src/__tests__/dispatch.test.ts`
- `packages/mcp-core/src/__tests__/session-recovery.test.ts`

Hexis tests were inspected but **not executed** in this task.

## 2. Decision matrix

| Hexis capability/principle | Decision | HG2-specific reason |
|---|---|---|
| Validate tool/request arguments before dispatch or side effects | **ADAPT** | The HG2 edge route is an authoritative handler and can reject invalid request shapes before mutating device state. |
| Route-level validation rather than relying only on one client path | **ADAPT** | Validation is performed inside `hg/edge.py`, so every caller of these endpoints receives the same gate. |
| Do not coerce invalid arguments into valid values | **ADAPT** | HG2 rejects wrong field types and invalid sequence values. |
| MCP/UTCP runtime and TypeScript dependencies | **REJECT for this scope** | Canonical HG2 is Python standard-library-only and has no MCP/UTCP tool runtime. Adding that runtime would be an architectural expansion, not a selective security adaptation. |
| Session-loss recovery and automatic retry | **NOT APPLICABLE** | The canonical source has no corresponding remote MCP session. Retry semantics must not be introduced without a demonstrated operation/idempotency contract. |
| Git/PR workflow service | **NOT APPLICABLE** | The canonical runtime has no Git/PR workflow subsystem. |
| Hexis authentication/access-control service | **DO NOT REPLACE** | HG2 already has a deny-by-default `hg/authority.py`; any future comparison must preserve HG2's own authority boundary. |
| Hexis lifecycle/readiness service | **NOT ADOPTED** | The inspected service measures different backend dependencies and does not establish phone-primary runtime readiness for HG2. |

## 3. Demonstrated HG2 capability gap

A local counterexample was executed against an isolated export of the exact canonical base commit. A validly authenticated `POST /edge/register` payload containing `device_id` plus an unexpected field received HTTP `201`, and the device state was mutated. The counterexample was run only against a local test server; no production endpoint was called.

This is a demonstrated request-schema gap, not a claim that the entire HG2 authority or runtime is defective.

## 4. Implementation in this candidate

Changed files:
- `hg/edge.py`
- `tests/test_edge_schema_guard.py`
- `docs/HEXIS_SELECTIVE_ABSORPTION_REPORT.md`

The candidate adapts the guard principle without copying Hexis code or adding dependencies:
1. Per-endpoint allowlists for `/edge/register` and `/edge/heartbeat`.
2. Strict type and bounds checks for `device_id`, `runtime`, `architecture`, and `seq`; no type coercion.
3. Reject unknown fields and recursively reject field names that look like model-key material, while not scanning arbitrary string values for the words model and key.
4. Reject duplicate JSON object keys and non-standard JSON constants.
5. Return a 400 refusal before `DEVICES` is mutated.
6. Preserve existing valid payload forms exercised by the canonical test suite.

No changes were made to `hg/authority.py`, `hg/history.py`, `hg/identity.py`, or `hg/phone_runtime.py`. No third-party dependency was added.

## 5. Verification evidence

- Exact base commit/tree verified through GitHub and a clean isolated checkout.
- Baseline suite on the exact base: **12 tests passed**, exit code 0, in 1.948 s. Existing `ResourceWarning`s were emitted by baseline tests; these are pre-existing and are not represented as fixed by this change.
- Counterexample on the exact base: unexpected register field accepted with HTTP 201 and state mutation confirmed.
- New focused guard suite: **11 tests passed** with `ResourceWarning` treated as an error, in 1.545 s.
- Full candidate suite: **23 tests passed**, exit code 0, in 3.052 s. Existing `ResourceWarning`s from `tests/test_core.py` remain.
- `python3 -m py_compile hg/edge.py tests/test_edge_schema_guard.py`: passed.
- `git diff --check`: passed.
- The original source branch passed all 23 tests locally. The integration PR now includes the repository's existing strict CircleCI unittest configuration so CI can validate the submitted tree.

## 6. Final integration status

- Pull request #9 was merged into `hg-genesis` on 2026-10-13.
- Canonical merge commit: `cdebaeed014371f033f14352f552c6d0d4e69198`.
- Post-merge verification ran on that exact commit: **23 tests passed**, exit code 0, using `PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest discover -s tests -v`.
- CircleCI run #28 passed on the submitted source commit `ddfd11e2af38ca9cbc38b3aa18e71e5a4c92b0cc`.
- `git diff HEAD^ HEAD --check` passed; the SHA-256 evidence manifest verified every listed item.
- The implementation adapts a request-validation principle; no Hexis implementation code or runtime dependency was copied. The inspected archive has no Git metadata, so the exact upstream commit remains unknown.
- Production/VPS/HTTPS/device end-to-end behavior was not run by this change and is not claimed as verified.
