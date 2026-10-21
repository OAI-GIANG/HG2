# HG2 Central Brain Adapter Readiness — 2026-10-21

- Repository: `OAI-GIANG/HG2`
- Candidate branch: `stt/hg2-master-cleanup-20261021`
- Architecture: one Central Brain + four subordinate domains
- Status: **PARTIAL / UNBOUND WHERE NOT QUALIFIED**

## Rule

`BRANCH_CAPABILITIES` is an ownership allowlist, not evidence that a capability works. Only a concrete adapter with an explicit authority boundary, readiness test, bounded side effects, stable output contract and independent evidence verifier may be admitted by `RuntimeCapabilityRegistry`. Any adapter that lacks these requirements remains `UNBOUND`; no capability is inferred from a module's existence or unit tests alone.

## Current capability disposition

| Domain | Capability | Current evidence | Disposition |
|---|---|---|---|
| Memory · Knowledge · History | `memory.search` | Server has a concrete memory-context adapter and registry binding; it uses the phone runtime's memory store | **Bound in API path; tested path only, not proof of production runtime identity** |
| Memory · Knowledge · History | `memory.recall` | No distinct Brain adapter contract and acceptance evidence located | **UNBOUND** |
| Memory · Knowledge · History | `provenance.inspect` | Provenance module exists in candidate/source, but no Brain adapter with independent verification bound | **UNBOUND** |
| Creative · Research · Experiments | `synthesis.propose` | Server has a configured-model adapter; its result is explicitly `RESPONSE_ONLY`, not proof of execution or semantic correctness | **Bound only as response-only; never upgrade to SUCCESS without independent verifier** |
| Creative · Research · Experiments | `research.analyze` | No source-grounded research adapter with retrievable evidence/provenance contract located | **UNBOUND** |
| Creative · Research · Experiments | `source.compare` | No independent source comparison adapter and evidence corpus contract located | **UNBOUND** |
| Tools · Tasks · Automation | `tool.execute` | No least-privilege execution adapter with per-tool allowlist, approval gate, hard timeout, idempotency and receipt contract | **UNBOUND** |
| Tools · Tasks · Automation | `artifact.build` | Voice CLI and code-intelligence CLI exist as local utilities but are not a Brain artifact adapter; model/artifact quality gates remain distinct | **UNBOUND** |
| Security · Policy · Verification · Sync | `policy.check` | Policy primitives exist, but no request-scoped Brain adapter with complete inputs, explicit authority and independent result verifier located | **UNBOUND** |
| Security · Policy · Verification · Sync | `evidence.verify` | Code-intelligence report and test receipts do not by themselves provide an independent evidence verifier for arbitrary worker output | **UNBOUND** |
| Security · Policy · Verification · Sync | `conflict.review` | No independent conflict adjudicator and typed evidence contract located | **UNBOUND** |

## Integration boundary

The API's registry currently registers only a subset of the memory domain and one response-only synthesis capability. It does not establish that all four domains are fully integrated. The capability registry correctly leaves absent capabilities unavailable; preserve this fail-closed behavior.

The candidate restores `hg.creative_assimilation`, `tools/hg_code_intelligence.py` and `tools/voice`, but these are utilities/modules, not automatically authorized workers. The four-domain runtime adapter work is therefore not complete.

## Requirements before binding a new capability

1. Versioned input/output contract and stable error codes.
2. One explicit domain owner; no capability escalation or cross-domain authority.
3. Principal/permission binding from trusted runtime context, never from user-provided grants.
4. Side-effect class, resource limits, timeout behavior and invocation budget.
5. Independent readiness and evidence verifier; worker cannot self-certify its result.
6. Request/correlation/source-revision binding and content digest validation.
7. Unit, negative, adversarial, restart and integration tests on Termux.
8. Registry snapshot and evidence receipt bound to exact commit SHA.
9. Any incomplete gate means `UNBOUND` or a narrower status such as `RESPONSE_ONLY`, never `OPERATIONAL`.

## No false integration

This document does not claim all four domains are operational. The next implementation slice should bind one narrow read-only capability at a time, then test the API routing and denial paths. General shell execution, network research, policy approval, evidence verification and arbitrary conflict resolution must not be bound by a placeholder adapter.
