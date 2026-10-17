# HG2 — Circulatory Architecture

HG is the product; HG2 is its single canonical repository and operating structure. The canonical runtime and state authority remain the phone / Termux. VPS1 is an optional relay; VPS2 is an optional worker or disaster-recovery target, never a second primary.

## Architecture direction

HG2 is being restructured around a human circulatory-system analogy: HGAgent is the brain coordinating one bounded turn, the phone runtime is the heart and sole canonical state owner, canonical event envelopes are the blood, the shared event/tool-routing workflow is the nervous system, and the outbox/provider/relay adapters are transport pathways. Each capability is a specialized organ; hg.policy is the immune system, hg.contracts is the one canonical JSON/parser/digest owner, and integrity/recovery are the kidneys. This analogy defines responsibility boundaries; it does not justify unnecessary complexity or duplicate modules.

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

The circulatory architecture is a design baseline. This candidate branch now includes a tested principal-based agent/provider/tool-routing path and stricter fail-closed state verification, but it is not merged to hg-genesis, is not connected to the deployed runtime, and is not release-certified. The legacy history store remains the default; SQLite remains opt-in with explicit migration required. Use the roadmap's work packages and acceptance gates; do not perform a big-bang rewrite or reset uncommitted work in other worktrees.
