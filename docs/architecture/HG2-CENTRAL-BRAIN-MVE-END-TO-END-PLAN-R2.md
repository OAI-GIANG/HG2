# HG2 Central Brain — Minimum Viable End-to-End Plan R2

## Objective

Prove one useful task travels through intake, deterministic validation, a single central router, authorized capability execution, independent evidence verification, durable workflow state, and a truthful final status—without enabling arbitrary tools or destructive actions.

## Recommended first use case

“Answer a question using authorized local memory and cite which local memory evidence informed the response.” It is valuable, bounded, can run on the phone, and does not require a write-capable tool adapter. The generated answer remains RESPONSE_ONLY until semantic correctness criteria are independently checked.

## Current slice already evidenced

- POST /api/ask calls the Brain orchestrator.
- It uses the authenticated local memory context builder and configured model gateway adapters.
- Local HTTP test runs against PhoneRuntime and its StateStore with a deterministic fake gateway.
- Memory evidence manifest is checked against a request-local dictionary.
- The provider call returns RESPONSE_ONLY; aggregate status is PARTIAL.
- New pre-call audit event model.call.started must persist before the gateway is called; an injected append failure blocks the call.
- Candidate test evidence after remediation: 34 focused tests passed; 241 full-suite tests passed with ResourceWarning as an error.

This is a local functional integration slice, not a fully closed MVE: Brain plan and step states are not yet durably persisted/recovered, and the evidence verifier is not independent for semantic/external claims.

## MVE completion slices and gates

| Slice | Deliverable | Required test/evidence | Status |
|---|---|---|---|
| MVE-0 Request intake | Versioned normalized request with explicit source and capability requirements | Invalid fields/oversized payload fail before dispatch | PARTIAL; API validation exists, full classifier absent |
| MVE-1 Deterministic router | Exact capability ownership and adapter availability | Missing/unknown capability blocks with zero worker calls | TESTED in core |
| MVE-2 Authorized memory | Read only memory within principal grants | Cross-scope record never enters provider context | Existing memory/server tests; use source-matched result logs |
| MVE-3 Pre-call audit | Redacted append-only start receipt before provider | Valid call order; injected append failure yields zero gateway calls | TESTED in local fake-gateway E2E |
| MVE-4 Response status | Model text remains RESPONSE_ONLY/PARTIAL | Provider answer cannot be promoted to external-action SUCCESS | TESTED on fake gateway |
| MVE-5 Independent answer evidence | Evidence references resolve, freshness/provenance validated; unsupported answer claims marked | Missing bytes, modified digest, stale source, unsupported statement fail verification | OPEN |
| MVE-6 Durable workflow | Persist plan/steps/checkpoints in canonical state authority | crash/restart matrix recovers same plan; uncertain action becomes IN_DOUBT | OPEN |
| MVE-7 Exact phone runtime | Run approved local use case on named runtime/device | startup, health, logs, actual state path and post-run integrity evidence | NOT RUN in this pass |
| MVE-8 Acceptance and budgets | Frozen intent/answer corpus, resource ceiling and user-oriented rubric | independent scoring, latency/RSS/tool counts and unauthorized action count | OPEN |

## Minimal acceptance rubric

All mandatory criteria must pass; do not trade off a failure in authority or evidence for better natural-language quality:
1. The capability set is allowlisted and bound to a real adapter.
2. A denied scope, absent adapter or invalid evidence yields no unsafe execution.
3. Pre-call audit failure yields zero provider/tool calls.
4. Every admitted task/step is bound to request ID, stable idempotency key, plan digest and explicit source revisions.
5. Restart does not replay a possibly executed non-idempotent effect without reconciliation.
6. Independent verifier does not trust the executor's success claim alone.
7. The response names its status and evidence; response generation is not presented as proof of an action.
8. Test suite passes; logs, environment, commit and hashes are recoverable.
9. Target device resource limits are measured before a threshold is set.
10. Rollback/checkpoint path is rehearsed before promotion.

## Explicit non-goals for first MVE

- No automatic repository writes, merge, delete or deploy.
- No arbitrary shell execution by an LLM.
- No five peer agents with equal authority.
- No parallel workers until DAG, write-set isolation, join and compensation behavior are specified.
- No second authoritative task database.
- No live provider call during the standard regression suite.
