# HG2 — Intelligence, Creativity & Controlled Self-Evolution Plan R1

- Date: 2026-10-20 (Asia/Ho_Chi_Minh)
- Repository: OAI-GIANG/HG2 only
- Implementation branch: `stt/hg2-intelligence-evolution-r1-20261020`
- Baseline: `cc7ffb39c58f4c4090a13ccaa414af3b70e109dc` (PR #29 head at time checked)
- Design method: existing-artifact inventory → sourced initial proposal → adversarial role-based critique → final synthesized plan
- Dependencies: Python standard library first; no paid software/dependency required by the deterministic evolution gate
- State: plan + bounded offline acceptance gate; NOT a general autonomous coder, not a model-weight self-training system, and not production authorization

## 1. MTC-1.0

### OBJECTIVE
Evolve HG from a well-governed runtime into a more flexible, self-evaluating and creativity-supporting problem solver without multiplying command authorities, databases, services or unverified permissions. Enable bounded improvement through measurable evidence and reusable skills.

### SCOPE
- Preserve one logical Central Brain and the existing five logical capability domains.
- Reuse the existing capability registry, skill manifest, Unified Harness, evidence/provenance mechanisms and canonical phone StateStore where they are compatible.
- Add one small, pure, deterministic evolution policy module; do not wire it to production writes or a background autonomous loop while task-state durability/ownership has open contract gaps.
- Treat generated plans, reflections, candidate skills and proposed changes as untrusted proposals.
- Begin with bounded “soft” artifacts only. Do not autonomously mutate security/authority policy, identity, tests/oracles, canonical state code, credentials, or deployment.
- Use a frozen evaluation corpus, same-version environment, explicit resource budgets, rollback digest, and a fail-closed acceptance decision.
- Keep all Termux execution on the phone; do not touch the already running HG services or runtime data.

### INPUT / OUTPUT
Input: HG2 source at the pinned baseline, existing R2/R3 architecture docs, skill and capability contracts, synthetic native-intelligence fixtures, published papers/standards.
Output: overlap/disposition matrix, evidence-backed design, adversarial critique, final phases/gates, a stdlib acceptance-gate module with negative tests, exact test logs and SHA-256 evidence.

### ACCEPTANCE CRITERIA
1. Every proposed capability is classified IMPLEMENTED / TESTED / VERIFIED / OPERATIONAL / UNBOUND / MISSING with its evidence boundary.
2. No duplicate command brain or authoritative task database is introduced.
3. A proposal cannot execute code, grant itself a capability, alter its oracle, change policy, or directly promote itself.
4. Candidate and baseline evaluation use identical test-suite digest, environment digest and case IDs.
5. Missing, blocked, not-run, duplicate or mismatched evaluation records never promote a candidate.
6. Any baseline PASS → candidate non-PASS regression rejects promotion; any failed C0 safety assertion rejects promotion regardless of aggregate score.
7. Minimum improvement is declared before evaluation; no statistically/operationally supported gain means keep the baseline.
8. Any persisted production task loop remains blocked until canonical task state, crash recovery, restart/replay and IN_DOUBT handling are integrated and tested.
9. No claims of human independent review, zero-cost model inference, production operation or self-evolution beyond the actual evidence.
10. All changes are confined to this branch and can be reverted without touching other worktrees or live state.

### RISKS / STOP CONDITIONS
Stop before any mutation if branch/baseline identity differs, untracked or user data would be touched, authority/state owner is ambiguous, a dependency/license is unverified, the test oracle can be changed by the candidate, or an irreversible side effect lacks reconciliation and rollback. This slice must not enable arbitrary shell, self-delete, auto-merge, auto-deploy, credential changes, or privilege expansion.

## 2. Existing-state and overlap audit

This audit is source/docs based at the pinned baseline, not a claim that every path is operational.

| Existing component / artifact | Observed responsibility | Disposition | Why / boundary |
|---|---|---|---|
| `hg/brain_orchestrator.py` | Deterministic router over explicit capability IDs and injected worker adapters | KEEP + later IMPROVE | Single logical command authority is correct; this code is not yet a general intent classifier or durable planner. |
| `hg/capability_registry.py` | Concrete adapter binding, ownership, readiness, budget and lifecycle gate | KEEP | Complements rather than duplicates the static maximum-ownership map. |
| `hg/skill_contract.py` | Validates declarative, versioned skill metadata, source digest, license and trust; does not run skill code | KEEP + COMPOSE | This should remain skill trust/manifest validation; new code handles candidate/evaluation eligibility. |
| `hg/unified_harness.py` | Fail-closed admission and outcome trace checks | KEEP + REUSE | Do not create a parallel quality harness; add evolution-specific predicates only where no existing helper exists. |
| `hg/history.py` / `PhoneRuntime.store` | Existing phone-owned event journal and state projections | KEEP as canonical owner; do not write from this slice | Multi-file journal/projection atomic recovery remains an open limitation. |
| `hg/workflow.py` | Pure task state machine + service expecting a richer transactional store contract | INVESTIGATE / NOT WIRE | Its store API is not compatible with legacy `StateStore.emit()`; it lacks the explicit IN_DOUBT task state. |
| `hg/sqlite_state.py`, `hg/durable_transactions.py` | Different typed state/event/transaction contracts | ISOLATE; NO DUAL-WRITE | Not proven drop-in replacements; using them as a second task authority risks split-brain state. Do not delete or merge based on names alone. |
| `hg/authority.py` vs `hg/policy.py` | Different authorization/policy helpers with potential conceptual overlap | INVESTIGATE callsites before disposition | Similar vocabulary does not prove semantic duplication or safe replacement. |
| `hg/memory.py` and `hg/provenance_memory.py` | Lexical retrieval, provenance/freshness/conflict information | KEEP; add evaluation feedback as a separate explicit record later | Storing a history or reflection is not proof that HG learned or improved. |
| `tests/fixtures/hg-native-intelligence-v2.1` | Synthetic test-oracle fixtures for planning, correction, creative alternatives and controlled-improvement cases | KEEP as specification input; build real runtime tests around it | Existing wrapper reports fixtures `SYNTHETIC_NON_PRODUCTION / NOT_RUN`; they do not establish implemented capability. |
| R2/R3 Master Plan, expert review, evolution ledger, failure matrix | Existing architecture/research/critical review/gates | EXTEND BY REFERENCE; do not create new service or competing blueprint | The new plan narrows their unresolved “measured evolution” work into a first falsifiable code slice. |

### Core finding
HG2 already contains foundations for orchestration, governed skills, memory provenance, typed capability dispatch and testing. The verified gap is not “nothing exists”; it is the lack of a connected, source-evidenced improvement loop that diagnoses a weakness, proposes a bounded candidate, evaluates it against an immutable baseline/oracle and safely decides whether to retain it. Existing documentation explicitly labels dynamic intent classification and measured evolution as deferred, and the current five-domain API path leaves three domains unbound. Synthetic fixtures are not implementation evidence.

## 3. External research register and design consequences

Accessed/reviewed 2026-10-20. These papers inform hypotheses and tests; they do not certify HG2.

| Source | Main finding used | Design consequence / limitation |
|---|---|---|
| ReAct, Yao et al., 2022 — https://arxiv.org/abs/2210.03629 | Interleaving reasoning/action with observations helps adapt a plan | Allow plan revision from actual observations, but do not make a model's narrative the state authority; stop or replan through typed events and budgets. Research result is not a guarantee for HG tasks. |
| Reflexion, Shinn et al., 2023 — https://arxiv.org/abs/2303.11366 | Verbal feedback and episodic experience can improve later attempts without weight updates | Keep compact task-scoped lessons and validate transfer on held-out cases; reflection may also reinforce a mistaken hypothesis. |
| Self-Refine, Madaan et al., 2023 — https://arxiv.org/abs/2303.17651 | Iterative feedback/refinement can improve outputs on evaluated tasks without additional training | Use an evaluate–revise loop for proposals; never treat self-rating alone as proof of gain. |
| Voyager, Wang et al., 2023 — https://arxiv.org/abs/2305.16291 | Curriculum, a reusable skill library and feedback/verifier loop support continual skill acquisition in its environment | Reuse versioned skills + explicit verifier, but avoid unsafe executable skill import. The reported system uses GPT-4 queries; it does not prove free inference. |
| LLM agent planning survey, 2024 — https://arxiv.org/abs/2402.02716 | Planning includes task decomposition, selection, external modules, reflection and memory | Model planning as replaceable proposal generation around deterministic validation and explicit state. |
| Agent memory survey, 2024 — https://arxiv.org/abs/2404.13501 | Memory mechanisms differ in structure, lifecycle and evaluation | Keep task state, durable user facts and episodic learning distinct; measure retrieval and freshness instead of equating storage with learning. |
| SWE-agent, 2024 — https://arxiv.org/abs/2405.15793 | A carefully designed agent-computer interface affects coding task results | Expose narrow, typed, allowlisted operations; do not hand a model unrestricted shell access. |
| NIST AI RMF — https://www.nist.gov/itl/ai-risk-management-framework | AI risk is governed, mapped, measured and managed over a lifecycle | Put risk checks in proposal, evaluation, promotion, and rollback—not only at release. Voluntary framework, not certification. |
| OWASP GenAI / LLM Top 10 (2026) — https://github.com/GenAI-Security-Project/GenAI-LLM-Top10/blob/main/2026/README.md and Excessive Agency — https://github.com/GenAI-Security-Project/GenAI-LLM-Top10/blob/main/2026/final/LLM03_ExcessiveAgency.md | Prompt injection, data disclosure, excessive agency, poisoning, supply chain and unbounded consumption are relevant risk classes | Treat fetched content and generated changes as untrusted; enforce least privilege, budget, provenance and external policy checks. |
| METR task time-horizon methodology — https://metr.org/time-horizons/ | Agent capability claims require empirical task-success/time measurements on defined tasks | Keep a frozen, representative evaluation set and report success/abstention/error and budget, not vague “smarter” claims. Benchmarks may not transfer to HG’s task mix. |
| Android background work restrictions — https://developer.android.com/develop/background-work/background-tasks/bg-work-restrictions | Android/OEM lifecycle can interrupt background work | Do not promise continuous self-evolution until exact-device screen-off, process kill, reboot, low-storage and network-loss recovery are tested. |

### Free/offline constraint
The code gate and deterministic mutation operators use Python standard library and require no paid service. This is not general generative intelligence. The checked interactive Termux shell had no `HG_MODEL_*` configuration, no recognized local LLM executable (`ollama`/`llama.cpp`), and no `transformers`/`torch` inference package; the inspected Hugging Face cache contained a VieNeu-TTS speech model, not a verified general-purpose text model. Thus R1 can propose small evidence-linked rule variants for predefined failure classes without network or model cost; open-ended creative generation and semantic planning remain `BLOCKED_UNVERIFIED` until a compatible local model/runtime is proven on-device or an optional configured provider is explicitly budgeted. No large model/package install is included in this slice.

## 4. Initial proposal before critique (P0/P1/P2)

1. Add a constrained improvement cycle: Observe → Diagnose → Hypothesize → Propose → Evaluate against frozen oracle → Compare with baseline → Accept/reject → Preserve decision/evidence.
2. Use only standard-library code and one small `hg/evolution.py` for typed proposal/evaluation/decision contracts plus a narrow deterministic offline mutation registry for evidence-linked text candidates. It will not execute candidate code, write runtime history, mutate active artifacts, or self-promote.
3. Reuse existing skill/capability/harness contracts; retain the one Brain and five domains.
4. Only allow candidate classes that are easy to sandbox/rollback (versioned skill metadata, prompt templates, bounded retrieval/routing strategy). Explicitly deny changes to authority/security rules, frozen test oracle, canonical state code, identity/credentials and production deployment.
5. Require matched candidate/baseline suite digest, environment digest and case identities; deterministic evaluation; mandatory complete outcomes; zero C0 critical failures; no regression; predeclared minimum gain; resource budget and rollback digest.
6. Persist reflections/evolution history only when a compatible, crash-safe canonical task/evidence writer is proven. Until then, keep the gate pure and produce a deterministic decision/evidence record without changing production state.
7. Keep a manual/owner-authorized promotion boundary. A successful eligibility verdict is not permission to auto-edit, delete, merge or deploy.
8. Add fixed positive/negative tests for schema errors, oracle mismatch, incomplete runs, C0 failure, regression, no gain and qualified improvement.

## 5. Adversarial expert-perspective critique

**Honesty boundary:** These are deliberately separated critical perspectives synthesized by STT using external sources and code/docs. No human experts were contacted, and no GitHub independent-review feature was used. They must not be represented as an independent human certification.

| Perspective | Strongest challenge to the initial proposal | Change required in the final plan |
|---|---|---|
| Agent-learning researcher | Reflection can preserve a false causal story; a clever self-generated explanation can sound right while not transferring to future tasks. | Persist candidate lessons as hypotheses with source/task/evidence and confidence; accept only when held-out cases show improvement. Self-critique cannot be its own oracle. |
| Evaluation/statistics specialist | A candidate can overfit the golden set, change the scoring rule, cherry-pick missing cases or exploit aggregate scores while breaking a critical case. | Pin suite and environment digests; predeclare metrics/thresholds; compare exact case-ID sets; disallow candidate changes to oracles; no PASS if any case is missing/BLOCKED/NOT_RUN; C0 failure overrides aggregate. Add a separate holdout in a later phase and track repeated attempts. |
| Software architect | Adding an evolution agent, skill engine, planner and new database will inflate architecture and create competing sources of truth. | Implement a single pure policy module only; compose existing registry/skill/harness; do not introduce new process/service/database. Delay durable automation until state contracts align. |
| Security specialist | A “self-evolving” system could rewrite policy, import hostile code, expand permissions or execute hidden prompt instructions. | Candidate is data-only; no `exec`, dynamic import or arbitrary shell in the gate; source/license/digest required; protected target classes hard-denied; runtime authority remains outside model output. |
| Reliability engineer / Android operator | A long-running loop may die when Android reclaims Termux or after a partial journal write, then repeat external side effects. | No autonomous background loop in R1. First close the StateStore/WorkflowService contract mismatch, single state owner, crash recovery, IN_DOUBT and exact-device lifecycle tests. |
| Creativity/product specialist | Safety-only tuning can make HG conservative and generic; “unique identity” is not measured or separated from mutable memory. | Define an HG identity rubric: preserve user constraints, traceable originality, useful alternatives, contradiction handling and explicit uncertainty. Keep identity/authority invariants immutable; measure usefulness and novelty against task-specific rubrics, not arbitrary “creativity” scores. |
| Cost/offline specialist | Calling a paid hosted model contradicts an absolute free requirement; silently adding a local model may exceed mobile resources. | No paid dependency required for the deterministic gate. Provider calls must be optional and budgeted. Verify local model availability and resource budget before claiming offline creative generation; do not install a large model without evidence. |
| Governance/SRE specialist | “Auto-delete weaker feature” risks removing unrecognized consumers or persisted schemas; a hash or green unit test doesn’t prove safe promotion. | Use KEEP/IMPROVE/MERGE/REPLACE/DEPRECATE/QUARANTINE/DELETE with dependency/callsite/data migration proof. Prefer deprecation/quarantine first. Code gate only grants eligibility; promotion needs a separate governed operation and rollback/recovery evidence. |

### Critique verdict
The initial proposal is directionally useful but must **not** create an autonomous mutation loop yet. The immediate shippable unit is a pure, fail-closed evaluation gate plus test oracle. The runtime may call this gate only after durable state ownership and recovery are fixed. “Continuous self-evolution” is a staged target, not an honest claim about the first implementation.

## 6. Final consolidated plan R1

### Target architecture
One Central Brain; five existing capability domains; one versioned skill contract; one runtime capability registry; one quality harness; one canonical phone state owner. Add only a small `hg/evolution.py` pure module in the first implementation. Do not add a new brain, daemon, agent framework, scheduler service or task database.

### Improvement cycle
1. **Observe:** capture task class, source revision, authorized inputs, tool capability/readiness, outputs, errors and actual evidence.
2. **Diagnose:** identify a specific measurable shortfall; preserve conflicting explanations; distinguish observation from hypothesis.
3. **Hypothesize:** define the expected improvement and an explicit falsifier before generating a candidate.
4. **Propose:** create a digest-bound candidate limited to an allowed soft artifact, with source/license, budget and rollback digest.
5. **Evaluate:** run deterministic unit/integration tests and a frozen task-specific oracle against baseline and candidate under the same environment and resource caps.
6. **Challenge:** run negative/adversarial cases and counterexamples; ensure the candidate did not change the oracle or evaluator.
7. **Compare:** require complete matched records; reject any C0 failure, any baseline PASS regression, any budget violation, or any missing/mismatched evidence.
8. **Decide:** `KEEP_BASELINE`, `REJECT`, `INCONCLUSIVE` or `PROMOTION_ELIGIBLE`. The last is eligibility only, not an automatic mutation or deployment.
9. **Preserve:** emit a deterministic decision record containing proposal digest, baseline/candidate/suite/environment digests, case-level deltas, limitations and rollback digest. Durable integration waits for canonical state recovery closure.
10. **Revisit:** use observed results and held-out cases to decide whether a lesson transfers. Do not change model weights or protected policy automatically.

### Allowed target classes in R1
- Versioned declarative skill/procedure metadata.
- Versioned prompt/template or bounded strategy parameters.
- Retrieval/routing heuristics behind fixed safety and capability gates.

### Permanently out of scope for self-approval
- Owner identity, authority/security policy, credentials/secrets, canonical state owner/journal format, frozen acceptance oracle/scorer, unrestricted executable code, package installation with unverified license/provenance, automatic deletion, merge, push to protected branch, or deployment.
- These can only be changed through separately authorized change control, dependency mapping, frozen tests, migration/rollback proof and the required authorization gate.

### Roadmap and release gates

**P0 — Pure evolution admission/evaluation gate (this slice)**
- Strict proposal/evaluation schemas; digest/case/environment binding.
- Deterministic comparison with critical-failure, regression, completeness and resource-budget rules.
- Unit and negative tests.
- No production storage wiring, no arbitrary code execution, no auto-promote.
- Acceptance: focused suite + full repo suite pass on Termux; static compile; diff check; saved logs and SHA-256. Status at code completion must still say candidate, not operational.

**P1 — Durable episodic learning & plan recovery**
- Resolve canonical StateStore vs WorkflowService transactional API contract.
- Versioned task/step/evolution events, single-writer semantics, crash recovery and IN_DOUBT reconciliation.
- Record compact lessons with evidence and source/scope/freshness metadata; deduplicate and handle contradictions.
- Exact-device kill/reboot/screen-off/low-storage/network-disconnect tests. No second database.

**P1 — Flexible planning and bounded tool use**
- Add task classification/dependency DAG only after a frozen routing oracle exists.
- Model proposes; deterministic code validates capability owner, adapter readiness, scope, deadline, budget and side-effect policy.
- Start serial; concurrency only with measured benefit and explicit dependency/write-set/compensation semantics.

**P2 — Creative generation and measured self-improvement**
- Measure utility, novelty/diversity, constraint satisfaction, factuality, transfer, regression, latency, memory and inference cost on fixed and held-out tasks.
- Compare existing provider and optional local model only where a reproducible free model/runtime is available and fits the phone.
- Do not fine-tune or claim self-generated new model weights as a free/offline feature without a separately costed and verified plan.
- Enable periodic autonomous proposal generation only after P0/P1 gates, queue persistence, cancellation, budget and rollback are operational. Owner approval remains required for protected or irreversible actions.

### Component decision rule
1. Inventory imports, runtime callsites, tests, public contracts, data formats, service start points and persisted-state readers/writers.
2. Build producer/consumer/dependency and overlap matrices. Similar names are not proof of duplicates.
3. Select one owner per responsibility and one canonical state authority.
4. Compare candidates against the frozen contract/oracle and measured cost/quality/reliability.
5. First deprecate or quarantine a redundant path; migrate consumers and persisted data; run compatibility/recovery tests.
6. Delete only after no reachable consumers, no data dependency, no supported contract and a tested rollback checkpoint remain. Preserve decision/evidence. A missing web source does not itself justify deleting a feature; replace only a disproven/unmaintainable method after proving a better alternative.

### Exit criteria for calling R1 closed
- [ ] This plan and role-based critique are recorded in repository.
- [ ] `hg/evolution.py` is pure, deterministic, stdlib-only and denies protected target classes.
- [ ] Positive/negative evaluation and promotion-decision tests pass.
- [ ] Existing skill, registry, Brain, harness and state-owner constraints are preserved.
- [ ] Full Termux suite, static compile and diff check pass on the exact commit; logs and SHA-256 recorded.
- [ ] Changes are committed on this isolated branch and pushed if network/credentials permit; PR may be opened without using GitHub review features.
- [ ] Open blockers are explicitly reported; no production auto-evolution or release claim without P1 evidence.

## 7. Evidence & implementation boundary

Code implemented by this plan only evaluates proposals/reports and returns a deterministic decision. The comparator requires an identified evidence-verifier callback to return literal true for each cited evidence reference; if absent, failing or throwing, the result is INCONCLUSIVE. A verifier ID is recorded in eligibility results. A callback's identity and implementation must be trusted by the eventual caller; the unit-test stub is not production verification. Hashing only establishes record-byte integrity, not the truth, origin or meaning of the evidence. This slice does not make HG self-aware in the human/subjective sense. “Self-awareness” here means machine-readable knowledge of current capability status, uncertainty, error signals and limits. It does not make inference free if a hosted model is called.

External source conclusions are research inputs, not endorsements of HG2. This plan's critical review is a structured STT role-based challenge, not a real independent human expert review or security certification.
