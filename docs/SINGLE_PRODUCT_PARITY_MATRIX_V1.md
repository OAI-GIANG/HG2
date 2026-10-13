# HG2 Single-Product Parity Matrix V1

Status: DRAFT / READ-ONLY AUDIT INPUT. This matrix records source-visible capabilities; it is not a certification of runtime behavior or complete historical parity.

Audit references:
- HG2 baseline: `hg-genesis` at `d11e71ed8b34338b8568664b39bc777c926826d5`.
- HG2 integrity candidate inspected: `b28fff890f2d879a77e1fda3ce26c87f3bec7a45`.
- GO branches inspected: `hg-genesis` at `c6f37fce653d8f7515404829d72c95605b227442`; `hg-phone-bridge-v1` at `4a20c319fe740f1a092ade4e407d693439629385`.
- HG branch inspected: `hg-genesis` at `0495ac8bba4dc59bbf5b84ef7f38dd78bae7dead`.

## Feature decisions

| Capability | Source evidence | Proposed disposition for HG2 | Gate / caveat |
|---|---|---|---|
| Phone-primary canonical state owner | HG2 `contract/ARCHITECTURE_V1.md`, `hg/phone_runtime.py`, `hg/history.py` | KEEP | Must remain exactly one canonical state owner; no implicit dual-primary/forked history |
| Append-only JSONL history, record hashes, replay, idempotency | HG and HG2 history implementations and tests | KEEP; strengthen fail-closed behavior | P0 integrity tests must pass on a clean checkout at the exact candidate SHA |
| Checkpoint and state projection validation | HG2 `hg/history.py`, `tests/test_integrity_v2.py` | KEEP; fail closed on any missing/mismatched durable artifact | Missing checkpoint, projection, runtime identity, rollback, malformed record, and no-repair assertions required |
| Runtime identity persistence and binding to history | HG2 `runtime_id`, record `runtime_id`, projection fields | KEEP | Identity must never be silently regenerated for an existing store; formal HG durable identity to HG2 product-label mapping is recorded; compatibility tests remain open |
| Authority allowlist and forbidden actions | HG2 `hg/authority.py`; HG `runtime/hg_runtime/authority.py` | KEEP | Session creation must require a real injected authentication verifier; no caller-independent `authenticated=True` shortcut |
| Device registration, heartbeat, status via edge relay | HG2 `hg/edge.py`, `hg/phone_runtime.py` | KEEP if edge connectivity remains a product requirement | Edge `DEVICES` storage is in-memory in the inspected source; durable device registry is not proven |
| HG HTTP API `/v1/sessions` and `/v1/history` | HG `runtime/hg_runtime/service.py` | REMOVE_INTENTIONALLY_ALLOWED by owner choice C; removal still requires dependency inventory and exact-SHA acceptance tests | Legacy route source/tests inventoried in `evidence/HG2_PRODUCT_SCOPE_DEPENDENCY_INVENTORY_V1.json`; candidate edge-router 404 integration tests added. External client/deployment inventory remains unknown |
| GO Phone Bridge 1.1 request/auth/replay/governed-execution/evidence correlation | GO `phone_bridge/bridge.py`, `phone_bridge/protocol.md` on `hg-phone-bridge-v1` | REMOVE_INTENTIONALLY_ALLOWED by owner choice C; removal still requires source/dependency inventory and fail-closed regression tests | GO branch source/protocol and branch-local consumers inventoried in `evidence/HG2_PRODUCT_SCOPE_DEPENDENCY_INVENTORY_V1.json`; candidate runtime exclusion/fail-closed tests added. External consumers and production replacement remain unproven |
| Separate GO/HG/HG2 implementations evolving in parallel | Repository/branch inventories | REMOVE from active development workflow after HG2 acceptance | Keep source repositories and evidence read-only; do not delete or archive as part of this change |
| HG2 identity label versus embedded product ID `HG` | HG2 `hg/identity.py`, `hg/history.py`, `manifest.json` | KEEP PRODUCT_ID=HG with formal mapping HG (durable/event identity) → HG2 (product/repository label) by owner choice A | Manifest mapping is declared; new-store replay/audit and pre-mapping canonical fixture byte-preservation tests added. Exact-SHA verification pending; do not rewrite historical IDs |

## Current gate state

- Feature parity: `BLOCKED` — scope acceptance plan is `docs/PRODUCT_SCOPE_ACCEPTANCE_HG2_V1.md`; source inventory is `evidence/HG2_PRODUCT_SCOPE_DEPENDENCY_INVENTORY_V1.json`. External clients/deployments remain unknown and exact-SHA/CI evidence is pending.
- History integrity: `CANDIDATE IMPLEMENTATION` — remediation on this branch must be independently reviewed and tested; this document alone is not evidence of correctness.
- Session authentication: `PARTIAL` — the runtime now requires a host-supplied verifier and fails closed if missing/rejecting/raising; production credential verification and authority integration remain to be independently assessed.
- Independent review: `BLOCKED` until a reviewer other than the author reviews the exact candidate SHA.
- Production / VPS / HTTPS / device E2E: `NOT_RUN` in this branch; no deployment is authorized.
