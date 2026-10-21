# HG2 — Five-Branch Architecture V1 (1+4)

**Status:** DESIGN BASELINE for the cleanup branch; not a production certification.
**Repository:** `OAI-GIANG/HG2` only.

## Canonical structure

1. **Central Brain** — the only command authority: intake, classification, planning, routing, orchestration, synthesis and task-level control.
2. **Memory · Knowledge · History** — retrieval, provenance, durable memory and historical state.
3. **Creative · Research · Experiments** — source-grounded research, synthesis, hypothesis generation and controlled experiments.
4. **Tools · Tasks · Automation** — bounded skills/adapters, task workflow, artifact generation and automation.
5. **Security · Policy · Verification · Sync** — authority, permissions, evidence verification, integrity, replication and recovery.

The five branches are logical responsibility domains, not five Git branches, services, agents or peer command authorities. The Brain is the coordinator; the other four are subordinate domains. In particular, `planning_coordination` is not a fifth worker domain: planning belongs to the Brain control plane.

## Implementation rules

- A domain is operational only when a concrete adapter is bound, ready, permission-scoped, bounded and tested. A name in a registry or document is not proof of implementation.
- Capability ownership is single-source. The Brain owns orchestration and does not dispatch itself as a peer worker.
- State authority remains single-owner; memory/context is not workflow state, and replication/outbox is not a task scheduler.
- Reuse existing contracts, workflow, policy, evidence, state and sync implementations. Do not add parallel stores or duplicate coordinators.
- Missing capabilities fail closed and are reported as gaps; they must not be silently marked operational.
- Archive/history/evidence and untracked user artifacts are preserved until their redundancy and recovery path are proven.

## Acceptance gates

- Exactly four subordinate domains appear in the runtime router.
- Central planning is not represented as a peer adapter.
- Unknown/removed capability IDs fail closed before dispatch.
- Every routed subordinate has a concrete adapter and explicit readiness/authority/evidence contract before being marked operational.
- Unit, integration, negative, crash/restart and regression tests pass on Termux; production status additionally requires evidence from the actual deployed runtime.

## Supersession note

Earlier R2/R3 documents and tests use a five-worker-domain taxonomy that included `planning_coordination`. They are retained as historical evidence. This document supersedes that taxonomy for the cleanup candidate by applying the user's 1+4 architecture. Historical evidence must not be rewritten to imply it originally tested the new structure.
