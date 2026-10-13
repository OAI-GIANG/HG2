# HG2 Product Scope Decision Record V1

**Record status:** `RECORDED — SCOPE ONLY`
**Implementation status:** `NOT PROVEN`
**Readiness:** `BLOCKED / NO-GO`
**Canonical baseline:** `hg-genesis` @ `d11e71ed8b34338b8568664b39bc777c926826d5`
**Permitted work branch:** `fix/hg2-single-product-readiness-20261013`

This record captures the Product Owner's explicit choices. It does not assert that the features have been removed, that any replacement exists, or that tests have passed. The machine-readable source of record is [`contract/PRODUCT_SCOPE_DECISIONS_V1.json`](../contract/PRODUCT_SCOPE_DECISIONS_V1.json).

## 1. Decision register

| Decision ID | Owner choice | Recorded disposition | What the choice does not prove |
|---|---|---|---|
| `PSD-API-001` | HG HTTP API = **C** | Intentional removal of `/v1/sessions` and `/v1/history` is allowed, subject to impact/dependency audit and acceptance tests. | Does not prove the endpoints are absent, consumers are migrated/retired, or runtime behavior is safe. |
| `PSD-BRIDGE-001` | GO Phone Bridge 1.1 = **C** | Intentional removal of the Bridge 1.1 request/auth, replay protection, governed execution, and evidence-correlation capability set is allowed, subject to source/dependency inventory and regression tests. | Does not prove capabilities were removed, that equivalents exist, or that authority/security guarantees remain intact. |
| `PSD-ID-001` | HG/HG2 identity = **A** | Keep durable `PRODUCT_ID="HG"`; formally map **HG = durable/event identity** and **HG2 = product/repository label**. Do not rewrite historical `product_id` values. | Does not prove all metadata/docs/tests consistently implement the mapping. |

## 2. Acceptance criteria and tests

### HG HTTP API — intentional removal allowed

Acceptance criteria: `AC-API-01` through `AC-API-04` in the JSON contract.

- `T-API-01`: inventory the routes in candidate and legacy source; record exact findings.
- `T-API-02`: search all available source, configuration, documentation, and client material for consumers; each dependency must be retired, migrated, or explicitly block acceptance.
- `T-API-03`: integration-test the actual candidate router/server. Confirm removed routes are not served and the resulting HTTP status/error contract is explicit; test remaining supported routes.
- `T-API-04`: regression-test durable history, identity, authorization, and state after removal.

### GO Phone Bridge 1.1 — intentional removal allowed

Acceptance criteria: `AC-BRIDGE-01` through `AC-BRIDGE-05` in the JSON contract.

- `T-BRIDGE-01`: inventory protocol capabilities from the original bridge source/protocol and compare against HG2. Every item must be marked intentionally removed, evidenced replacement, or unresolved; no implicit equivalence claims.
- `T-BRIDGE-02`: search call sites, clients, configs, docs, and workflows for dependencies; unresolved consumers block acceptance.
- `T-BRIDGE-03`: run fail-closed authority/authentication and durable-history regression tests at the exact candidate SHA.
- `T-BRIDGE-04`: audit user-facing capability claims; do not claim removed Bridge 1.1 features are available without separate proof.

### Product identity — keep `PRODUCT_ID=HG`, map product label to HG2

Acceptance criteria: `AC-ID-01` through `AC-ID-05` in the JSON contract.

- `T-ID-01`: unit-test `PRODUCT_ID == "HG"` and the formal mapping `product_id=HG` / `product_name=HG2`.
- `T-ID-02`: create, replay, verify, and audit-export a store; durable/event identity must remain HG.
- `T-ID-03`: reopen and verify a pre-existing HG fixture without rewriting event bytes or changing `product_id`.
- `T-ID-04`: static-scan identity-bearing code, metadata, and docs for any unapproved HG-to-HG2 durable-ID conversion.

## 3. Evidence status at record creation

All implementation-level tests above are `BLOCKED_NOT_RUN` until their required sources/routers/fixtures are available and the test is implemented and executed. The only immediate test to run at this stage is the contract-record consistency test. A passing contract-record test proves only that this decision record is structurally consistent; it does not pass the implementation gates.

The previously recorded durability tests and CI result apply only to their exact recorded source SHA and do not prove these new scope decisions are implemented. No power-loss test is implied.

## 4. Global fail-closed gates

- Exact-SHA acceptance tests and CI: `BLOCKED`.
- Independent review by someone other than the author on the exact candidate SHA: `BLOCKED`.
- Provenance: `BLOCKED` until evidence is independently checked; do not represent unsigned commits as signed.
- Production authentication and applicable VPS/HTTPS/device E2E: `BLOCKED` until supported by evidence.
- No merge, deploy, canonical branch mutation, repository/branch archive or deletion, or history rewrite is authorized by these choices.

**Current conclusion: `BLOCKED / NO-GO`.** The Owner's scope decisions are recorded; implementation, test, review, and production evidence remain separate gates.
