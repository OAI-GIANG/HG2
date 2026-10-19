# HG2 Central Brain — External Research & Evidence Matrix R2

Checked: 2026-10-19. Sources were used to challenge architectural assumptions and shape test requirements; they do not verify that HG2 implements a pattern.

| Source | Main idea relevant to HG2 | Application | Limitation / disagreement |
|---|---|---|---|
| NIST AI RMF Playbook — https://www.nist.gov/itl/ai-risk-management-framework/nist-ai-rmf-playbook | Govern, Map, Measure and Manage are cross-cutting risk-management functions; the playbook is guidance, not a rigid sequence | Apply risk governance during design, test, operation and evolution; maintain risk/evidence records | Voluntary generic framework; does not define HG2's runtime APIs |
| NIST AI RMF Core — https://airc.nist.gov/airmf-resources/airmf/5-sec-core/ | Governance must inform the full system lifecycle and be continuous | Do not restrict governance to a final release score | Does not certify any implementation |
| NIST AI 600-1 GenAI Profile — https://www.nist.gov/itl/ai-risk-management-framework/ai-risk-management-framework-resources | GenAI requires context-specific risk identification and management | Explicitly test hallucination, data provenance, prompt injection, privacy and output misuse | General risk profile; thresholds must be derived from HG2 data |
| OWASP GenAI LLM Top 10 2026 (current release published 2026-08-04) — https://genai.owasp.org/llm-top-10/; canonical source https://github.com/GenAI-Security-Project/GenAI-LLM-Top10 | The current release frames risks for LLM/GenAI applications and agentic systems; relevant classes include prompt injection, sensitive-information disclosure, supply chain and data/model poisoning | Least privilege, untrusted retrieved data, policy gate outside model, resource caps, adversarial tests | Community threat guidance is not a substitute for a threat model tied to HG2 adapters; avoid relying on a superseded 2025 list |
| Microsoft Azure Saga pattern — https://learn.microsoft.com/en-us/azure/architecture/patterns/saga | Central orchestration can clarify complex workflows; distributed effects may need compensations, idempotency and state tracking | Use a coordinator plus persisted task/step state; only define compensation for actually compensable operations | Saga introduces coordinator complexity and cannot guarantee every side effect is reversible |
| Microsoft Idempotent Consumer — https://learn.microsoft.com/en-us/azure/architecture/patterns/idempotent-consumer | At-least-once delivery can repeat work; use a stable identifier across redelivery and store outcome atomically where possible | Distinguish request ID, correlation ID and operation idempotency key | Does not make arbitrary external providers exactly-once |
| Microsoft Transactional Outbox — https://learn.microsoft.com/en-us/azure/architecture/databases/guide/transactional-out-box-cosmos | Persist state transition and publication intent in one transactional boundary to avoid dual-write inconsistency | Bind task state and event/outbox intent transactionally to the canonical state owner | Current HG2 replication outbox is not automatically a scheduler or task queue |
| OpenTelemetry Context Propagation — https://opentelemetry.io/docs/concepts/context-propagation/ | Trace/span context correlates observations across process boundaries; inbound context from untrusted sources must be validated/sanitized | Preserve correlation and causal lineage; avoid putting secrets/PII in baggage | Full TraceContext implementation is not present in the inspected Brain code |
| Google code review practices — https://google.github.io/eng-practices/review/ | Reviews examine design, functionality, complexity, correctness and edge cases; facts/data outrank preferences | Independent reviewer and frozen test evidence before high-risk merge | Internal team guidance is not an external certification of HG2 |
| Google SRE reliability testing — https://sre.google/sre-book/testing-reliability/ | Test real production behavior in controlled, gradual ways; tests and monitoring complement one another | Separate hermetic unit tests, local E2E, exact-runtime checks and production rollout evidence | Does not justify enabling live actions before rollback and telemetry are ready |
| GitHub protected branches — https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches | Reviews/status checks and signed commit requirements can form merge gates | Keep draft while release gates are open; configure gates only after confirming current policy and available check names | This review did not change branch protection; it is not evidence that rules are currently enabled |

## Independent critique questions derived from research

1. Who has the final permission decision if the model proposes an action? Trusted policy code, never model output.
2. What happens when the coordinator crashes after an external effect but before storing its receipt? IN_DOUBT and reconciliation; no blind replay.
3. Can a retry be distinguished from a new request? Stable idempotency key bound to normalized input digest.
4. What does a digest prove? Byte integrity only unless a trusted chain proves source, method and custody.
5. Can an adapter claim its own success? It can produce a claim; an independent verifier accepts or rejects it.
6. Does a passing synthetic test prove live-provider operation? No.
7. How does the architecture behave under hostile retrieved content? Treat it as data; policy and adapter permissions are outside the model.
8. What prevents one failed module from using unlimited time or cost? Adapter-enforced timeouts and per-task/process budgets.
9. Could the same task status be stored in two competing places? The architecture must choose one canonical state authority.
10. Is the module count itself the architecture? No; the responsibility contracts and measured operational boundaries define it.

## Decision

Adopt explicit orchestration, idempotency, risk lifecycle, independent code review, context propagation and layered verification as design principles. Do not copy provider-specific infrastructure or add services solely because a reference architecture uses them. HG2 remains offline-first and dependency-light unless a measured requirement justifies otherwise.
