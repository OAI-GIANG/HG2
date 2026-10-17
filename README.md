# HG2 — Circulatory Architecture

HG is the product; HG2 is its single canonical repository and operating structure. The canonical runtime and state authority remain the phone / Termux. VPS1 is an optional relay; VPS2 is an optional worker or disaster-recovery target, never a second primary.

## Architecture direction

HG2 is being restructured around a human circulatory-system analogy: the phone runtime is the heart, canonical event envelopes are the blood, the sync outbox and transport adapters are the vessels, capability modules are organs, policy is the immune system, ingress validation is the filtering system, and integrity/recovery are the kidneys. This analogy defines responsibility boundaries; it does not justify unnecessary complexity.

Read the normative design contract in [contract/CIRCULATORY_ARCHITECTURE_V1.md](contract/CIRCULATORY_ARCHITECTURE_V1.md), the module map in [docs/HG2_CIRCULATORY_MODULE_MAP_V1.md](docs/HG2_CIRCULATORY_MODULE_MAP_V1.md), and the phased migration plan in [docs/HG2_CIRCULATORY_RESTRUCTURE_ROADMAP_V1.md](docs/HG2_CIRCULATORY_RESTRUCTURE_ROADMAP_V1.md).

## Non-negotiable invariants

- One canonical repository: OAI-GIANG/HG2.
- One canonical runtime/state owner: the phone.
- Offline-first local operation; remote services are optional.
- Deny-by-default authority, validated inputs, append-only auditable state, idempotent retries.
- No secrets on relays; no implicit failover or second primary.
- Evidence distinguishes PASS, FAIL, BLOCKED, NOT_RUN, and NOT_APPLICABLE.
- Documentation is not implementation proof; release requires source-linked tests, recovery evidence, and a verified Android artifact.

## Current state

The circulatory architecture is a design baseline. Implementation and runtime compliance are not yet certified. Use the roadmap's work packages and acceptance gates; do not perform a big-bang rewrite or reset uncommitted work in other worktrees.
