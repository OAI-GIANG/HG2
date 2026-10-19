# HG2 Central Brain R2 — External Evidence & Review Matrix

- Review date: 2026-10-19
- Repository scope: OAI-GIANG/HG2 only
- Status: EXTERNAL EVIDENCE COLLECTED; STT SYNTHESIS; NO HUMAN EXPERT REVIEW CLAIMED
- Purpose: evaluate the Master Plan R2 against published standards, official technical documentation and practitioner engineering guidance. This is a literature-based review, not a certification or a claim that named organizations reviewed HG2.

## Evidence classification

- EXTERNAL EVIDENCE: published source or documented behavior directly available at the URL.
- STT SYNTHESIS: an implication or recommendation derived by comparing the source with HG2's stated architecture.
- INDEPENDENT REVIEW: a review performed by a person or organization independent of the HG2 implementer and evidenced by a review artifact. None was obtained in this pass.
- UNVERIFIED: HG2 runtime/code behavior not established by external publications or not tested in this pass.

Access date for all URLs below: 2026-10-19. Sources are paraphrased; they do not endorse HG2.

## Source register

| ID | Source / publisher | URL | Evidence relevant to HG2 | Limits |
|---|---|---|---|---|
| EXT-01 | NIST AI RMF and Generative AI Profile | https://www.nist.gov/itl/ai-risk-management-framework ; https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf | Risk management should cover the AI lifecycle, context, measurement and governance, not just model output. NIST identifies the GenAI profile as published 2024-07-26; the main AI RMF page notes revision activity in 2026. | Framework is voluntary guidance, not an HG2 audit or implementation test. |
| EXT-02 | OWASP GenAI Security Project, Top 10 2025 | https://genai.owasp.org/llm-top-10/ | Includes prompt injection, sensitive information disclosure, supply chain, data/model poisoning, improper output handling, excessive agency, vector/embedding weaknesses, misinformation and unbounded consumption. | Risk list is not proof that a particular HG2 vulnerability exists. |
| EXT-03 | OWASP LLM06:2025 Excessive Agency | https://genai.owasp.org/llmrisk/llm062025-excessive-agency/ | Risk rises with unnecessary functionality, permissions and autonomy; controls should exist in the extension/API boundary, not rely on the model policing itself. | Requires mapping to actual adapters and authority boundaries to determine HG2 exposure. |
| EXT-04 | Anthropic, Building Effective AI Agents (2024-12-19) | https://www.anthropic.com/engineering/building-effective-agents | Distinguishes fixed workflows from dynamically directed agents and recommends simplest composable architecture before adding agentic complexity. | Practitioner guidance, not a universal theorem or independent review of HG2. |
| EXT-05 | Temporal documentation, retry policies | https://github.com/temporalio/documentation/blob/main/docs/encyclopedia/retry-policies.mdx ; https://docs.temporal.io/nexus/operations | Retries can re-run operations; idempotency and explicit execution semantics matter. “Exactly once” needs carefully defined scope and is not guaranteed merely by a retry setting. | Temporal is a product-specific implementation; HG2 need not adopt Temporal. |
| EXT-06 | AWS Durable Execution, idempotency | https://docs.aws.amazon.com/durable-execution/patterns/best-practices/idempotency/ | Distinguishes at-least-once and at-most-once attempt semantics; an interrupted operation may have external effects even if the checkpoint is missing. | AWS SDK semantics do not directly apply to HG2; use as design evidence. |
| EXT-07 | SQLite atomic commit | https://www.sqlite.org/atomiccommit.html | A transaction can make a group of database changes appear all-or-nothing across interruption under the documented operating assumptions. | Does not guarantee application-level consistency across a database plus remote provider call. |
| EXT-08 | SQLite WAL | https://www.sqlite.org/wal.html | WAL supports concurrent readers/writers with constraints; all processes must be on the same host, and it is not for network filesystems. | HG2 must inspect actual SQLite mode, filesystem and process topology before choosing WAL. |
| EXT-09 | Python sqlite3 transaction control | https://docs.python.org/3.13/library/sqlite3.html | Transaction mode and commit/rollback behavior must be explicit; Python's documented defaults and recommended mode vary by version. | Must pin and test the actual Python version used by HG2. |
| EXT-10 | W3C PROV Primer | https://www.w3.org/TR/prov-primer/ | Provenance can represent entities, activities and agents and help assess origins, trust, compliance and reproducibility. | Provenance metadata alone does not establish that a claim is true or that the actor is authentic. |
| EXT-11 | NIST SP 800-218 SSDF v1.1 | https://csrc.nist.gov/pubs/sp/800/218/final | Secure development practices should be integrated into the SDLC and used to reduce vulnerabilities and recurrence. NIST lists Rev.1 v1.2 as an initial public draft dated 2025-12-17. | Guidance is not evidence of HG2's supply-chain integrity or secure implementation. |
| EXT-12 | Android Developers, background work restrictions | https://developer.android.com/develop/background-work/background-tasks/bg-work-restrictions?hl=en ; https://developer.android.com/about/versions/oreo/background?authuser=104 | Background execution and network behavior may be restricted by Android version, device manufacturer and resource policy. | Termux is not a conventional app architecture; actual device/OEM behavior needs runtime tests. |
| EXT-13 | OWASP GenAI Top 10 overview | https://genai.owasp.org/initiatives/top-10-for-llm-and-genai/ | OWASP describes a broader security project and identifies the 2025 risk taxonomy as current project material. | Taxonomy changes over time; freeze source version/date in test fixtures. |

## Ten-angle critical review

### R-01 — Distributed systems and orchestration
- EXTERNAL EVIDENCE: EXT-04 says fixed workflows are more predictable for defined tasks; EXT-05/06 show retry can replay activity and must be paired with explicit idempotency semantics.
- STT SYNTHESIS: Central Brain should own the logical plan, but deterministic state transitions and execution adapters should enforce the plan. Do not make the LLM the source of truth for workflow state.
- Weak assumption to reject: writing a “started” event alone makes an external call transactionally safe.
- Failure scenario: provider accepts a request, process dies before response/result persistence, and restart repeats the call.
- Alternative: persist request identity and an IN_DOUBT state; reconcile via provider idempotency/status API when available; otherwise require conservative manual resolution for non-repeatable side effects.
- Decision: KEEP single logical command; IMPROVE durable state/idempotency/reconciliation; DEFER multi-agent parallelism.
- UNVERIFIED: exact behavior of HG2 StateStore, DurableTransactionStore and workflow integration must be checked at source and with crash tests.

### R-02 — AI planning, routing and agent boundaries
- EXTERNAL EVIDENCE: EXT-04 recommends simple composable patterns and differentiates predefined workflow from dynamic agent control.
- STT SYNTHESIS: use model output only as a typed plan proposal; validate graph acyclicity, capability existence, authority, budget, deadlines and evidence requirements in deterministic code.
- Failure scenario: planner emits a nonexistent capability, dependency cycle, or a route that silently expands scope.
- Alternative: fixed routing rules for known task classes, constrained planner proposals for ambiguous tasks, human clarification when confidence/authority is insufficient.
- Decision: KEEP Central Planner as responsibility; ADD deterministic plan validator and fixed-oracle routing corpus before dynamic execution.
- UNVERIFIED: routing accuracy and answer quality lack a frozen representative oracle until benchmark results exist.

### R-03 — AI security, prompt injection and least privilege
- EXTERNAL EVIDENCE: EXT-02/03 identify prompt injection and excessive agency as risks; they recommend controlling permissions and extensions at system boundaries rather than relying on model instructions alone.
- STT SYNTHESIS: retrieved documents, web pages, memory, tool output and user text are untrusted data; they cannot grant authority. Authorize each exact principal/resource/action outside the model output.
- Failure scenario: an ingested document tells the Brain to upload private data or delete repository files; the model routes it to a powerful tool.
- Alternative: narrow read-only adapters first; allowlist paths and operations; isolate credentials; require explicit approval for destructive or external-write actions; add data-exfiltration and confused-deputy tests.
- Decision: KEEP fail-closed and authority separation; ADD injection corpus, privilege-boundary tests and resource caps.
- UNVERIFIED: no independent penetration test or red-team review of HG2 was obtained.

### R-04 — Database, idempotency and crash recovery
- EXTERNAL EVIDENCE: EXT-05–09 distinguish database atomicity from application-level side effects and show replay semantics require explicit idempotency.
- STT SYNTHESIS: one local transaction can atomically persist task state and audit intent if both live in the same database transaction; it cannot atomically include a remote model-provider call. Treat the remote call as a distributed boundary.
- Failure scenario: DB records STARTED; provider accepted call; device is killed before RESULT. A retry can duplicate charges, requests or actions.
- Alternative: stable idempotency key from authenticated principal + client request ID + canonical request digest; states QUEUED/STARTED/IN_DOUBT/SUCCEEDED/FAILED/BLOCKED; provider idempotency where supported; otherwise bounded no-blind-retry policy.
- Decision: KEEP canonical StateStore; ADD restart/crash matrix and explicit unknown-outcome reconciliation. Do not add a second workflow database before proving need.
- UNVERIFIED: actual durability settings, filesystem, SQLite mode and kill/restart behavior require on-device evidence.

### R-05 — Independent verification, evidence and provenance
- EXTERNAL EVIDENCE: EXT-10 says provenance describes entities, activities and agents and can support trust and reproducibility judgments.
- STT SYNTHESIS: provenance and hash integrity are necessary but not sufficient: a hash proves bytes match a digest, not factual correctness, actor identity or independent review. Separate evidence collection from claim verification.
- Failure scenario: a model creates a JSON report with a valid SHA-256 but fabricated test results; a verifier checks only schema/hash and accepts it.
- Alternative: verifier independently reads actual artifact/logs, reruns deterministic checks, binds result to exact commit/environment, tests negative cases and records limitations; use external reviewer for claims requiring human independence.
- Decision: KEEP evidence ladder; ADD claim-to-evidence traceability and verifier independence criteria.
- UNVERIFIED: existing request-local manifest callback is not demonstrated to be a semantic or external provenance verifier.

### R-06 — Knowledge, memory and contradiction handling
- EXTERNAL EVIDENCE: EXT-01 and EXT-10 support lifecycle risk management and provenance as distinct concerns; neither establishes a universal algorithm for memory freshness or contradiction resolution.
- STT SYNTHESIS: every memory item should carry source, observed time, validity interval if known, scope, trust tier, version and supersession links. Conflicting facts must remain visible until a policy resolves them.
- Failure scenario: stale memory silently overrides a newer authoritative repository state, causing an unauthorized plan.
- Alternative: distinguish durable facts, task state and derived summaries; prefer source-of-truth reads for volatile facts; record contradiction and ask rather than auto-merge.
- Decision: ADD freshness/provenance/contradiction contract; do not assume “long-term memory” is authoritative state.
- UNVERIFIED: full HG2 memory lineage and stale-fact evaluation have not been externally audited.

### R-07 — Software architecture and maintainability
- EXTERNAL EVIDENCE: EXT-04 favors simple composable patterns and increasing complexity only when justified.
- STT SYNTHESIS: the nine logical responsibilities should not automatically become nine services or agents. Each boundary should correspond to independently testable policy, state ownership, failure isolation or replaceability.
- Failure scenario: duplicate planner, workflow store and registry create conflicting owners and synchronization bugs.
- Alternative: begin as modular in-process components with explicit contracts; split only after measured bottleneck or isolation requirement.
- Decision: KEEP minimum-complexity principle; ADD a written split criterion and module ownership map.
- UNVERIFIED: runtime coupling and dependency graph completeness need dynamic traces in addition to static imports.

### R-08 — Adversarial testing, reliability and safety
- EXTERNAL EVIDENCE: EXT-02/03 provide a threat taxonomy; EXT-11 supports secure development and recurrence prevention.
- STT SYNTHESIS: ordinary unit tests and fake gateway success paths are insufficient. Tests need fixed expected outputs, negative authority cases, mutation/fault injection, crash points and test-set governance.
- Failure scenario: AI-generated tests share the implementation's mistaken assumption and pass despite a defect.
- Alternative: frozen human-reviewed oracle cases, mutation testing where feasible, independent test review, seeded prompt-injection and forged-evidence fixtures.
- Decision: KEEP baseline tests; ADD independent oracle and adversarial/fault injection gates.
- UNVERIFIED: test representativeness and independent review coverage have not been certified.

### R-09 — Repository governance and rollback
- EXTERNAL EVIDENCE: EXT-11 recommends integrated secure development practices and vulnerability recurrence controls.
- STT SYNTHESIS: commit/push/merge/deploy permissions are separate capabilities; user authorization to operate does not mean every destructive action is safe for every candidate. Rollback requires more than a Git revert when data schemas or external effects changed.
- Failure scenario: a commit reverts code but leaves an incompatible database migration or irreversible provider action.
- Alternative: staged migration, backup/restore drill, explicit irreversible-action gate, signed/attributed evidence where available, branch protection and review before production promotion.
- Decision: KEEP checkpoint/rollback; ADD data migration rollback proof and independent PR review as a release gate.
- UNVERIFIED: PR #29 has no human independent review evidenced in this review pass.

### R-10 — Performance and Termux/Android runtime
- EXTERNAL EVIDENCE: EXT-12 documents background restrictions and OEM variability.
- STT SYNTHESIS: a successful interactive Termux test does not prove a service survives screen-off, process reclaim, reboot, network transitions or low storage. Keep the phone as a primary target only with explicit supported-runtime assumptions and recovery tests.
- Failure scenario: Android kills the process while an external request is in flight; the persisted task becomes IN_DOUBT and is incorrectly retried.
- Alternative: explicit foreground/service assumptions, bounded queue and memory, timeout/cancellation, reboot recovery, low-storage and network-loss tests. Do not promise uninterrupted background operation absent device evidence.
- Decision: KEEP Termux-compatible dependency restraint; ADD target-device operational matrix.
- UNVERIFIED: OEM-specific process restrictions and long-duration behavior on the exact target remain untested here.

## Agreement / disagreement / unresolved matrix

| Topic | Convergence in sources | Real trade-off / disagreement | R2 decision |
|---|---|---|---|
| Workflow vs agent | Simple fixed workflows are more predictable; agentic flexibility has a cost. | Dynamic planning may improve coverage but raises variance, latency and attack surface. | Deterministic workflow by default; model proposes, validator disposes. |
| Retry semantics | Replay and retries can repeat side effects. | At-most-once attempt can reduce duplicates but may leave an operation unresolved; retries improve availability but need idempotency. | Explicit IN_DOUBT and reconcile; never claim global exactly-once. |
| One central brain | Single logical command owner reduces authority ambiguity. | One coordinator can become bottleneck or failure concentration. | One logical owner, modular internals, bounded queue, explicit failure handling. |
| Evidence and hashes | Provenance and integrity improve traceability. | Neither alone proves semantic truth or reviewer independence. | Verify claims independently; report limits. |
| Local phone runtime | Local persistence supports offline-first operation. | Android process lifecycle and OEM constraints may interrupt long jobs. | Prove device-specific restart/recovery; no blanket uptime claim. |
| More modules/services | Clear boundaries can help testing/isolation. | Splitting increases deployment, synchronization and debugging costs. | Keep responsibilities logical; split only on measurable evidence. |

## Priority findings and dispositions

| Finding | Severity | Disposition | Acceptance evidence required |
|---|---|---|---|
| R-01 workflow recovery/idempotency | P0 | IMPROVE | Crash after every persistence/provider boundary; replay and IN_DOUBT reconciliation tests |
| R-02 planner trust boundary | P0 | IMPROVE | Cycle/unknown capability/scope expansion/budget overflow tests; fixed routing oracle |
| R-03 prompt injection and excessive agency | P0 | IMPROVE | Adversarial corpus; all unauthorized side effects denied |
| R-04 evidence overclaim | P0 | IMPROVE | Forged evidence and hash-only false-accept tests |
| R-05 source-of-truth conflict | P0 | INVESTIGATE | State ownership map and one canonical task/workflow authority |
| R-06 phone process lifecycle | P1 | IMPROVE | Exact device restart/reboot/network/low-storage evidence |
| R-07 knowledge freshness | P1 | IMPROVE | Stale/conflicting memory fixtures and provenance policy tests |
| R-08 human review provenance | P1 | BLOCKED | Actual review artifact from independent human reviewer, if claiming human independent review |
| R-09 performance budgets | P1 | INVESTIGATE | Measured latency, memory, storage and provider cost on representative tasks |
| R-10 supply-chain/secure development | P1 | IMPROVE | Dependency inventory, pinned versions/hashes, reproducible build and vulnerability review |

## Limitations

1. This is a literature-based critical synthesis, not an external human expert panel.
2. No external source has inspected or certified HG2's source tree, deployment or runtime.
3. No penetration test, independent semantic verification study, or human review artifact was obtained.
4. Some product documentation describes its own implementation; the design principles were transferred cautiously rather than copied as HG2 requirements.
5. The source register records access date and URL; archived snapshots and source-file digests have not been captured in this pass. For audit-grade reproducibility, archive the source documents and hashes in a subsequent controlled evidence task.
