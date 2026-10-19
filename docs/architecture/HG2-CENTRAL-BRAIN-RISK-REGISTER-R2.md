# HG2 Central Brain — Risk Register & Failure Taxonomy R2

Date: 2026-10-19. Ratings reflect architecture/source review, not a quantitative probability model. “Open” means mitigation/evidence is incomplete.

## Risk register

| ID | Severity | Likelihood estimate | Impact | Observable trigger / evidence | Mitigation / gate | Owner |
|---|---|---|---|---|---|---|
| R-01 / F-02 | HIGH | Medium | Crash loses plan/step progress; a side effect can be repeated or forgotten | No durable Brain plan/step record on current API path | Persist plan and step transitions before external effects; restart to IN_DOUBT; idempotent retry only | Central Brain + state owner |
| R-02 / F-03 | HIGH | High before tooling expansion | A domain is selected on paper but has no usable adapter or policy boundary | Three domains have no /api/ask adapter; inventory assembled in route | Trusted versioned registry; adapter binding/health check; zero dispatch on mandatory gap | Registry/router |
| R-03 / F-04 | HIGH | Medium | Forged or semantically invalid claim is treated as verified | Request-local dictionary/digest is sole verifier for memory manifest | Independent artifact/provenance/runtime verifier; test false-accept/false-reject | Verification |
| R-04 / F-05 | HIGH | UNKNOWN | Local tests mistaken for production proof; provider/runtime failures unseen | No live provider or deployed phone test in this pass | Exact-target smoke test with redacted evidence, rollback and operational telemetry | Runtime/operations |
| R-05 / F-06 | HIGH | Medium | Two databases diverge; status/authorization disagreement or data loss | Brain ledger integration not decided; DurableTransactionStore is standalone-file SQLite | Do not dual-write; define one transaction boundary over canonical state owner | Architecture/state owner |
| R-06 / F-07 | MEDIUM | Medium | Sync handler exceeds task deadline and blocks request thread/resources | Coordinator checks time only between synchronous adapter calls | Adapter-enforced hard timeout, bounded I/O, worker isolation only if justified; timeout test | Execution adapters |
| R-07 / F-08 | MEDIUM | High under client/network retries | Duplicate provider calls, cost or external side effects | Fresh UUIDs on each /api/ask HTTP request; no stable client idempotency key | Persist key+normalized input digest and outcome atomically; conflict if payload changes | API/workflow |
| R-08 / F-09 | MEDIUM | Medium | Humans confuse a logical domain “branch” with Git branch | Wire/source naming uses branch | Use domain terminology in documentation; rename only via new schema version | Architecture |
| R-09 / F-10 | HIGH | High for unmeasured claims | Misrouting or low-quality answers are presented as “intelligent” without measured quality | No frozen classification/oracle corpus; current route chooses capabilities statically | Build held-out reviewed corpus, confusion matrix, abstain metric and output rubric | Evaluation |
| R-10 / F-01 | HIGH | Previously present; patched in candidate | External call lacks durable start record when crash/write failure occurs | Start event is asserted before fake gateway; failure-injection proves zero gateway calls | Preserve tests and required pre-call audit invariant | API/audit |
| R-11 | HIGH | Medium | Prompt injection from memory/file/web causes unsafe action/false policy | Retrieved memory and model outputs cross trust boundaries | Treat retrieval as data; tool policy outside LLM; adversarial tests for direct/indirect injections | Intake/security |
| R-12 | HIGH | Medium | Model or worker claims authority, approval or capability not granted | Untrusted result tries to elevate scope | Policy validates principal + action + resource + plan digest; default deny; independent approval | Policy/authority |
| R-13 | HIGH | Low-to-medium | Rollback/reset damages canonical history or unrelated untracked data | Broad git clean/reset/delete or state restore without checkpoint | Explicit file allowlist, immutable checkpoint, no clean/reset on unknown worktree, restore rehearsal | Maintainer |
| R-14 | HIGH | Medium | Evidence references pass syntax checks but point to missing/untrusted bytes | Success-shaped worker result / hash-looking URI | Independent resolver, bytes/hash/source checks, verifier revision, evidence freshness | Verification |
| R-15 | MEDIUM | Medium | Resource exhaustion from unbounded context, retries, tasks or model costs | Increasing latency/RSS/calls, rate-limit errors, provider timeouts | Per-request size/step/time/resource caps and aggregate cost budget; stress-test on phone | Operations |
| R-16 | MEDIUM | Medium | Manifest/module register drifts from actual imports/entry points | manifest lists only a subset of source-present modules; intended semantics unclear | Define exact manifest invariants, build import graph, test tracked and dynamic reachability | Architecture |
| R-17 | MEDIUM | Medium | Stale knowledge or conflicts silently influence decisions | Conflicting sources, old content or missing source dates | Source/version/freshness metadata, explicit contradiction set, revalidation policy and decision ledger | Knowledge |
| R-18 | HIGH | Low-to-medium | High-risk writes/merges/deletes/deployments happen without approval | Model-generated plan directly triggers high-side-effect adapter | Scope-specific authorization, approval bound to plan digest, rollback/containment gate | Policy/release |
| R-19 | MEDIUM | Medium | Cross-process context is spoofed or leaks personal data via trace baggage | External/inbound trace metadata trusted | Validate context, omit sensitive baggage, preserve correlation IDs without authorization semantics | Observability |
| R-20 | MEDIUM | Medium | Excessive complexity causes more failure modes than value | Premature agents, modules, databases or concurrency | Minimum complexity; retain single-process boundaries until measured need; independent review | Architecture |

## Failure taxonomy

- F-AUTHORITY: permission missing, invalid principal, scope mismatch, approval/plan digest mismatch.
- F-ROUTING: unknown/unbound capability, duplicate ownership, dependency cycle, missing mandatory branch.
- F-CONTRACT: malformed envelope, unknown field, schema/version mismatch, duplicate JSON key, bad digest or mismatched request/source identity.
- F-EVIDENCE: evidence absent, invalid reference, byte digest mismatch, untrusted source, stale provenance or verifier unavailable.
- F-EXECUTION: adapter error, timeout, unhandled side effect, partial completion or outcome uncertainty.
- F-STATE: append failure, projection/history mismatch, non-atomic checkpoint or state-owner conflict.
- F-RECOVERY: restart with RUNNING/unknown step, idempotency collision, failed compensation/restore.
- F-ADVERSARIAL: direct/indirect prompt injection, data poisoning, privilege escalation, tool-result forgery or unbounded consumption.
- F-QUALITY: wrong intent, unsupported claim, incomplete answer, stale knowledge or evaluation-set leakage.
- F-GOVERNANCE: unauthorized code change, manifest drift, missing independent review, incomplete evidence or unreviewed destructive disposition.

## Closure policy

- A HIGH-severity finding needs a bounded reproduction, root-cause statement, remediation, positive and negative tests, recovery/rollback evidence, and named remaining limitations.
- Any observed unauthorized mutation or data-integrity loss is a P0 stop condition regardless of total score.
- Risk acceptance must name the accepting authority, affected scope and expiry/review trigger.
- A risk score cannot promote PROPOSED to IMPLEMENTED or TESTED to VERIFIED.
