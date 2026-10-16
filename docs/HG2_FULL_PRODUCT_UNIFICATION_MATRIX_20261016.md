# HG2 Product Capability Matrix — Phone-only Candidate

Scope: local phone runtime and developer tooling only. This matrix describes the current candidate tree, not the canonical branch or any remote deployment.

| Capability | Current implementation | Status | Boundary |
|---|---|---|---|
| Product identity | Durable `PRODUCT_ID=HG`, repository label `HG2` | Implemented | Historical event bytes are not rewritten. |
| Local durable state/history | `hg.history`, local runtime identifier, checkpoints and projections | Implemented in candidate | Live state validation must be performed separately; no external state authority exists. |
| Session authorization | Injected credential verifier | Fail-closed boundary | No production verifier implementation is included; absent/invalid verifier denies session creation. |
| Event exchange | `hg.sync` filesystem spool | Optional local capability | No network transport, remote replica, second primary, or automatic failover. |
| Code intelligence | Bounded read-only source inventory and static import graph | Optional developer tool | Does not execute scanned source or access external services. |
| Evidence/rights guards | Optional pure libraries and local tests | Candidate-only | No claim of benchmark acceptance beyond recorded test results. |
| External server/network integration | No runtime module, client, endpoint configuration, or server listener | Intentionally removed | Network integration is not part of the product scope. |

The candidate has not been merged into `hg-genesis`; canonical state therefore remains governed by the existing branch until separately authorized change acceptance. No host deployment or remote host operation is included.
