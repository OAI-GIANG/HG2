# HG2 GitHub Cleanup Inventory — 2026-10-18

Status: READ-ONLY AUDIT / NO REPOSITORY MUTATIONS
Canonical repository: OAI-GIANG/HG2
Repository default branch: hg-genesis (verified via GitHub metadata)
Audit baseline for open PR #25: 9d83a113ccdf1aeda656e494593fa55b9078c803
Architecture candidate: PR #25, branch stt/hg2-circulatory-architecture-20261018, head 88284de49ca71b0f32a75f7d7b37a8f4d0016e2c
Canonical branch, runtime, state and all PRs/branches left unchanged.

## 1. Objective
Reduce duplication, redundant module ownership, redundant acceptance contracts, repeated benchmark versions and fragmented integration work. Preserve unique needed capabilities, data, and evidence. Build an authoritative module/function inventory before deleting or closing anything.

## 2. Observed facts

### Canonical branch baseline
The GitHub tree for hg-genesis at the audit baseline contains top-level:
.circleci/, README.md, contract/, docs/, evidence/, hg/, manifest.json, tests/.
Production source modules under hg/:
- __init__.py
- authority.py
- edge.py
- history.py
- identity.py
- phone_runtime.py
Manifest modules list only identity, authority, history, phone_runtime, edge.
Core architecture contract says phone is sole canonical runtime/state owner; VPS1 is relay only; VPS2 may be an optional standby/worker/failover but never canonical state owner.

### Existing candidate architecture PR
PR #25 — “feat: begin circulatory HG2 architecture reconstruction”
- OPEN / DRAFT; base hg-genesis @ 9d83a113ccdf1aeda656e494593fa55b9078c803
- head 88284de49ca71b0f32a75f7d7b37a8f4d0016e2c
- 62 changed files, +5352/-78; PR description reports local suite 108 passed (not independently rerun during this inventory).
- Adds contracts.py, policy.py, sqlite_state.py, migration.py, recovery.py, sync.py, workflow.py; changes authority.py, history.py, edge.py, phone_runtime.py and manifest.json; adds tests/evidence/docs.
- SQLite is opt-in in candidate and live state was not switched. It is not certified or merged.
- Major risk: the new SQLite state backend coexists with the current file-based StateStore; implementation must define one active backend, one state authority, one event model, and guarded migration rather than retaining two competing canonical stores.

### Open PRs with materially overlapping scope
- PR #25: circulatory architecture; contracts, SQLite event/state backend, policy/approvals, workflow, sync/outbox, migration/recovery.
- PR #22: “HG2 single-system runtime and unified memory foundation”; adds durable, memory, replica, server, model gateway, provenance and limits; overlaps PhoneRuntime/state/history/durable outbox/provenance/tests with PR #25.
- PR #24: “feat: add bounded HG provider and tool plane”; adds agent, auth, provider, toolplane and updates authority/contracts/architecture/manifest; overlaps authority/security/interfaces/contracts with PR #25 and PR #22.
- PR #21: “feat: harden HG agentic intelligence foundation”; adds agentic intelligence, capabilities, durable transaction pieces, evidence, model-provider/criteria, task contract/compiler, verification-budget and several benchmark/evaluator suites. Overlaps workflow, provider, task contracts, evidence and durable transactions with #22/#24/#25.
- PR #19: “chore: detach HG2 runtime from external host infrastructure”; very large (223 changed paths reported by GitHub); broad collection of contracts/docs/evidence, creative assimilation, code-intelligence, provenance, sync, runtime and product-scope work. Must be decomposed by capability with explicit disposition; do not integrate wholesale or discard wholesale.
- PR #15: “Fix fail-closed coverage for unclassified repository files”; 56 changed paths; code-intelligence contract/tool/tests plus evidence/docs overlapping PR #19.
- PR #13 and PR #12: CTI/creative assimilation and benchmark protocol/evidence families with versioned preregistrations/results. Need one current canonical benchmark protocol plus immutable archival evidence; do not destroy raw results merely to reduce count.
- PR #8 and PR #1/#2/#11: sync/history integrity/test hygiene and resource handling; some overlapping hg/history.py, hg/sync.py, tests/test_core.py plus evidence.
- PR #17: phone-side read-only connector/integration verifier; candidate integration and tests, separate from core domain modules.
- PR #16/#7/#6: review evidence or decision/reference documentation; likely retain as provenance/audit records, but index under coherent docs/evidence rather than treat them as runtime modules.
- Other open PRs include #5 and #3. Some older PR metadata references earlier baselines (e.g., cdebaeed or d11e71ed) and needs exact-base reconciliation before disposition.

## 3. Preliminary duplication/ownership matrix

| Capability area | Current canonical owner | Candidate overlaps | Preliminary decision |
|---|---|---|---|
| Product/runtime identity | hg/identity.py and runtime | #22 provenance/identity, #25 contracts/runtime IDs, #24 auth identities | One identity/provenance contract; split identity from permission grants. Audit references before merging. |
| Authorization and approvals | hg/authority.py currently owns basic allowlist | #25 hg/policy.py/ApprovalService; #24 hg/auth.py and authority modifications; #21 capability policy | Keep one policy decision point; authority.py should be compatibility façade or removed only after imports/tests prove unused. Separate credential authentication from authorization and approval persistence. |
| Canonical event schema/serialization | current history has its own canonical JSON/hash | #25 hg/contracts.py plus SQLite event model; #22 durable/memory event and import; #24 state/auth contracts | One versioned canonical event envelope/serializer shared by persistence layers; no duplicate serializers or incompatible event schemas. |
| Durable canonical state/history | #25 file StateStore compatibility + SQLiteStateStore candidate | #22 durable/memory/replica/state imports; #21 durable_transactions/transactions | One canonical state interface and one active backend per state directory. Keep event log/projection/outbox atomic. SQLite and JSON legacy store must be migration source/target, not concurrent authorities. |
| Workflow/task lifecycle | canonical branch has no standalone workflow module | #25 workflow.py persisted task events; #21 task_contract/task_compiler/agentic compiler; #22 server/runtime command flow | One workflow state machine and task contract. Planner/compiler emits validated plan; workflow owns lifecycle; capability adapters execute. |
| Model/provider | absent from canonical branch | #24 provider/agent/toolplane; #22 model_gateway; #21 model_provider/agentic intelligence | One provider interface/credential boundary; gateway/provider adapters implement it. Agent/planner must not duplicate provider transport or hold state authority. |
| Tools/capabilities | canonical branch explicitly denies arbitrary shell/filesystem/network | #24 toolplane/agent; #21 capabilities/task compiler; #17 read-only connector | One capability registry/port, default-deny, explicitly granted adapters. Connector is an adapter, not an alternate policy/state writer. |
| Sync/network/relay | current edge.py is a small device registration/heartbeat relay; phone runtime uses optional POST | #25 sync outbox/dispatcher; #22 durable replica/outbox/API; #19 sync/auth/bootstrap; #8 T-018 | Distinguish local command routing from remote replication. One outbox/inbox/cursor contract; relay transports, never authority/state. Avoid duplicate sync engines and repeated cursor logic. |
| Migration | no canonical migration module | #25 migration.py; #22 import/reconcile scripts | One read-only source inspector plus explicit staged importer; no direct live import or implicit mixed-state conversion. |
| Backup/recovery | no standalone canonical module | #25 recovery.py; #22 restore/reconciliation evidence; #19 provenance/gates | One backup/restore contract and verifier. Recovery must not silently promote a secondary or overwrite canonical state. |
| Evidence/observability/provenance | evidence tree, tests; basic repo integrity | #21 evidence/provenance/evaluator; #22 provenance/runtime gates; #24 provenance graph; #19 audits; #15 code-intelligence evidence | One evidence schema/manifest and verifier, but distinct evidence types remain separate. Immutable test logs/raw benchmark data are not duplicates unless byte-identical or explicitly superseded. |
| Code intelligence/CTI | not in canonical source modules | #15, #19, #13, #12 | Treat as optional product capability; separate runtime feature from development/audit tooling. Merge protocols by explicit supersession map; preserve original raw results. |
| Documentation/contracts | canonical architecture contract is brief | #25 circulatory contracts; #22 unified-system decision/runbook; #24 auth/state/acceptance contracts; #19 overlapping contracts and decision matrices | One normative contract per concern, one index, archive superseded versions with supersession metadata. Do not keep multiple documents claiming authority over the same invariant. |
| Tests | tests/test_core.py central, plus schema guards and fixtures | #25 focused tests; #22/#24/#21 overlap core, runtime, auth, workflow, provider and integration | Keep focused tests by module plus small end-to-end suite. Move repeated setup into shared test helpers. Preserve unique negative/fault-injection coverage; remove only proven duplicates. |
| Build/CI/release | .circleci exists in current branch | PR #21/#15/#19 CI/config candidates | One required CI workflow/config source and a small set of stable verification commands; do not rely on unavailable CI provider as sole proof. |

## 4. Evidence and document hygiene
- Do not delete raw logs, source archives, preregistrations, failed attempts, or hashes only because they are old or numerous.
- Exact duplicates may be deduplicated only after byte/hash comparison and reference analysis.
- Superseded protocol versions should be archived and cross-linked, not rewritten as if they never existed.
- Split runtime source, tests, design contracts, immutable evidence, optional benchmarks, and operational runbooks into clear areas.
- Keep one current normative contract per subject; historical contracts should be explicitly marked non-normative/superseded.

## 5. Recommended folder model (target proposal, not yet implemented)
- hg/kernel or hg/runtime: composition root, lifecycle, command boundary, health.
- hg/contracts: event, command, result, task and adapter interface schemas.
- hg/identity: identity/provenance.
- hg/policy: authentication interface, authorization rules, grants, approvals.
- hg/state: store interface, active durable implementation, event history/projections.
- hg/workflow: task lifecycle, planner/compiler handoff.
- hg/capabilities: registry and typed ports.
- hg/adapters: provider, tools, UI/API, relay transport.
- hg/sync: outbox/inbox, receipts, cursors/anchors and retry.
- hg/recovery: backup, restore, migration, rollback/promotion checks.
- hg/observability: audit, redacted telemetry, health and evidence collection.
- tests: unit tests aligned with ownership plus integration/fault/recovery tests.
- contract: only normative architectural/security/schema decisions.
- docs: one index, ADRs and operational runbooks.
- evidence: immutable evidence grouped by verification campaign; never mixed into runtime imports.
- benchmarks: optional measurement harnesses, preregistrations, archived results.

Folder moves are justified only when they improve responsibility boundaries; do not create modules just to imitate human anatomy.

## 6. Safe execution sequence
1. Freeze/verify exact canonical base and branch/PR list; reconcile branch/base skew.
2. Inventory every production module, exported function/class, import edge, test claim and manifest entry.
3. Inventory each open PR's changed paths and capability claims, then create capability-by-capability keep/merge/replace/archive/unknown dispositions.
4. Select one integration trunk on a noncanonical branch; do not merge or close other PRs yet.
5. Integrate one bounded capability at a time and run unit, regression and architecture tests on exact SHAs.
6. Only after mapping and tests pass, close demonstrably duplicate PRs with reasons; retain branches/evidence until disposition is verified.
7. Only after a complete verified matrix, delete stale branches/files if a verified recovery path exists.
8. Do not change runtime backend, import live state, deploy, install APK, or modify canonical branch until separate cutover gates pass.

## 7. Risks and limitations
- PR summaries are author-provided, not proof every capability is correct or unique.
- Tests described in PR bodies were not all rerun in this inventory.
- GitHub and local checkouts show baseline skew and many parallel branches.
- Several checkouts have uncommitted changes (notably /home/hg2-phone and /home/tmp-hg2-readonly-connector-20261014); preserve them.
- PR #25 does not certify HG2 and does not imply release readiness.
- No PRs were closed, merged, rebased, deleted, or retargeted; no canonical branch, live runtime, or state was changed in this audit.

## 8. Current disposition
AUDIT_STATUS=INVENTORY_PARTIAL
CANONICAL_MUTATED=false
PR_MUTATED=false
BRANCH_DELETED=false
RUNTIME_CHANGED=false
STATE_MIGRATED=false
RELEASE_STATUS=BLOCKED_NOT_RELEASED
