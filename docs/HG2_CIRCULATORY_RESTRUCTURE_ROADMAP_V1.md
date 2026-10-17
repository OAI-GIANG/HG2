# HG2 Circulatory Restructure Roadmap V1

Status: planning baseline on branch stt/hg2-circulatory-architecture-20261018.

## Objective

Restructure the single canonical repository OAI-GIANG/HG2 around the Circulatory Architecture contract. Preserve the phone as the only canonical runtime/state owner. Treat remote servers as optional relay/worker/recovery targets only. Build from a clean, evidence-backed baseline; do not carry local uncommitted edits forward by accident.

## Work packages

### WP0 — Baseline and containment
- Record canonical commit, tree, branch, remotes, worktree status, and current test baseline.
- Keep the pre-existing dirty phone checkout untouched until its diff is reconciled explicitly.
- Keep this restructure in an isolated worktree and branch.
- Acceptance: exact baseline provenance is recorded; no existing worktree is reset or cleaned.

### WP1 — Architecture contracts
- Establish the body-to-module mapping, dataflow, ownership, security boundaries, failure semantics, and acceptance gates.
- Add architecture tests for dependency direction, canonical state ownership, no legacy execution roots, and no secret sinks.
- Acceptance: contracts are explicit and tests fail on a deliberate boundary violation.

### WP2 — Core contracts
- Define typed command/event/result envelopes, deterministic serializer, schema versioning, provenance references, and idempotency semantics.
- Acceptance: canonicalization tests, schema negative tests, replay tests, and version rejection tests pass.

### WP3 — Heart and state integrity
- Make the phone kernel the only composition root and canonical writer.
- Define transaction boundaries among state, history, head/checkpoint, and sync outbox.
- Acceptance: crash/fault-injection tests prove no false success and no silent divergence.

### WP4 — Immune system and approval
- Consolidate authorization, approval state machine, secret boundaries, and capability grants.
- Acceptance: deny-by-default, forbidden-action, privilege-escalation, and secret-sink tests pass.

### WP5 — Organs and workflows
- Extract planning/workflow from concrete provider, filesystem, network, and UI adapters.
- Add explicit timeouts, cancellation, bounded retries, and idempotency at each capability port.
- Acceptance: offline, timeout, retry, duplicate-delivery, and partial-failure tests pass.

### WP6 — Circulation and remote roles
- Separate local durable commit from outbound sync.
- Specify outbox/inbox, authenticated batches, monotonic cursor/anchor, relay acknowledgements, and conflict handling.
- Acceptance: VPS1/VPS2 cannot write canonical state; relay loss does not lose local work; replay and cursor regressions fail closed.

### WP7 — Kidneys and recovery
- Define backup manifest, independent digest verification, restore candidate quarantine, rollback, and explicit promotion protocol.
- Acceptance: corrupt, stale, partial, replayed, or wrong-lineage backup is rejected; restore drills are reproducible.

### WP8 — Evidence and observability
- Make every test/gate emit machine-readable result, source commit, environment, input/output digests, and status.
- Redact secrets and distinguish NOT_RUN/BLOCKED from PASS.
- Acceptance: evidence can be independently verified without relying on narrative claims.

### WP9 — Android packaging and release
- Verify Android build path and dependency constraints from HG2 only.
- Build a signed/traceable artifact only after packaging prerequisites are proven; do not claim APK readiness before artifact and installation checks.
- Acceptance: exact APK hash, build provenance, installation result, smoke tests, and rollback instructions are recorded.

## Operating rules

- One package at a time; each package has a contract, implementation, tests, evidence, and stop condition.
- No broad rewrite of all modules in a single patch.
- No destructive reset/clean of pre-existing user work.
- No cross-repository runtime dependency.
- No deployment, key rotation, remote-state mutation, or canonical merge without a verified gate and exact scope.
- If a gate is blocked, record the blocker and continue only with independent work that cannot weaken the blocked invariant.

## Current checkpoint

- Canonical source: OAI-GIANG/HG2, hg-genesis at 9d83a113ccdf1aeda656e494593fa55b9078c803.
- Isolated worktree: ~/hg2-circulatory-architecture-20261018.
- Baseline tests before changes: python -m unittest discover -s tests -v — 26 tests passed.
- The existing ~/hg2-phone worktree contains uncommitted modifications and is intentionally untouched.
- Architecture documentation is not implementation proof; WP1 onward remains open until code and evidence satisfy the gates.
