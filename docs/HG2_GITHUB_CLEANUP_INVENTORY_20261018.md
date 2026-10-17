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

## 9. Exact overlap and dependency evidence (cross-checked on 2026-10-18)

### Same paths and identical content
A Git object comparison was run between candidate branch heads, using their common Git merge base rather than filename-only assumptions:
- PR #15 vs PR #19: PR #15 changes 56 paths; PR #19 changes 215 paths relative to the same merge base; all 56 paths overlap. 51 files have identical Git blob content at both heads; five differ: .circleci/config.yml, contract/CODE_INTELLIGENCE_V1.md, docs/ABSORPTION_GATE_REPORT.md, docs/ABSORPTION_SOURCE_DECISIONS.md, and docs/evidence/HG2_CI_GROUND_TRUTH_RESULT_V2.json. This establishes high duplication but not safe PR closure: PR #19 is not mergeable and has broader scope and different product/network decisions.
- PR #22 vs PR #25: two shared paths, hg/phone_runtime.py and tests/test_core.py; both differ at the branch heads. Merge requires explicit composition and test preservation.
- PR #24 vs PR #25: three shared paths, README.md, hg/authority.py, manifest.json; all three differ. PR #25's authority.py is a re-export facade for hg.policy; PR #24 extends the policy action set and introduces auth/provider/tool-plane services. Resolve with one canonical policy and preserve authenticated provider invocation only through the validated principal path.
- PR #21 vs PR #25: no shared changed paths; however their task/workflow, provider, capability, evidence, and durable-transaction responsibilities overlap conceptually. Different paths do not prove distinct responsibilities.
- PR #22 vs PR #24: no shared changed paths, but there is conceptual overlap among model gateway/provider, runtime/service composition, and outbox/replication.
- PR #13 is based on PR #12's branch, so it is stacked, not an independent base-level change.
- PR #3 is based on PR #2, and PR #2 is based on PR #1. Preserve that dependency chain until a combined fix is verified.
- PR #19 and PR #15 report base commit cdebaeed..., while their shared merge base is d11e71ed...; both report not mergeable against the current target. PR #8 has base commit d11e71ed... and reports not mergeable. Rebase/reconcile against current hg-genesis is required before integration decisions.

### Symbol and module map observed by parsing branch source (not a semantic proof)
- PR #21 contains DurableTransactionStore (hg/durable_transactions.py, 552 lines), TransactionCoordinatorModel (hg/transactions.py, 161), and SQLiteEvidenceStore (hg/evidence.py, 436), plus a task contract/compiler, capability registry and model-provider implementation.
- PR #22 contains DurableOutbox (hg/durable.py), MemoryStore over file-backed StateStore, ModelGateway, ReplicaStore/HTTP server, and an HTTP server composing PhoneRuntime + memory + provider gateway.
- PR #24 contains bearer authentication (hg/auth.py), OpenAI-compatible provider transport (hg/provider.py), HGAgent, and fixed ToolPlane.
- PR #25 contains one versioned envelope/serializer helper (hg/contracts.py), policy/approval state machine, SQLiteStateStore (778 lines), task workflow (341 lines), a generic sync dispatcher, migration and backup/restore helpers. It also retains legacy file-backed StateStore behind the default runtime path and keeps SQLite opt-in.
- Source modules with distinct names may still duplicate underlying responsibilities. Before consolidation, determine whether each is an interface, adapter, projection, state machine, or independent capability.

## 10. Preliminary target ownership decisions

1. One canonical command/event/result schema and deterministic serializer shared by persistence, sync, evidence and tool audit. Legacy HG_STATE_V1 is a migration source, not a second concurrent authority after cutover.
2. One runtime-selected state backend per state directory, with a narrow common store interface. The file-backed store remains read/migration compatible until a tested cutover; do not dual-write canonically.
3. One authorization decision point. Authentication proves the principal; policy authorizes an action; approvals bind a particular principal, resource, request digest and version. Avoid duplicate allowlists in agent, tool-plane, edge and workflow.
4. One task contract + compiler/planner interface + one persistent workflow state machine. Planning decides what should be done; workflow owns lifecycle/retry/deadline/cancel; capability adapters perform bounded operations.
5. One provider transport boundary. Specialized providers implement a common provider interface; they do not each implement their own configuration, HTTPS safety, timeout, redirect, response-limit and redaction logic.
6. One delivery/outbox engine and one explicit relay/replica endpoint contract. Remote durable-memory sync, generic event sync and backup replication may use policies/adapters, but must not each maintain competing cursors, retries, receipt schemas or canonical authority.
7. One memory subsystem for user facts/preferences and scoped recall; provenance/evidence memory is a separate type only if a written contract demonstrates that its ownership and query/use-cases differ from user memory.
8. One source/build/runtime provenance model with type-specific records. Code-intelligence provenance, running-build provenance, memory provenance and evidence integrity can be distinct record types but should not create redundant hash/manifest implementations.
9. Code-intelligence, CTI benchmarks, creative-assimilation research, and evaluation harnesses are not automatically runtime modules. Retain them as optional tools/features only if product scope and acceptance tests justify them; keep raw immutable evidence in an archive/index instead of deleting it to reduce file count.
10. One normative contract for each invariant; stale designs and audit artifacts remain history/reference, visibly marked superseded or archived, not competing current policy.

## 11. Cleanup stage status after evidence update
- Detailed repository and PR inventory: PARTIAL but evidence-backed.
- Proven exact-path/content overlap: PR #15/#19 high overlap (51 identical blobs; 5 content variants).
- Proven module/interface consolidation opportunities: policy/identity, event serializer/state, provider transport, workflow/capability routing, outbox/replica, provenance/evidence.
- Actual source-file deletion, PR closure, branch deletion, runtime change, canonical mutation: NONE.
- Next safe stage: create a bounded integration branch based on current hg-genesis, select one implementation owner per responsibility, port unique needed capabilities with tests, and only then close superseded PRs/branches with retained evidence.

## 12. P0 fail-closed hardening performed on the isolated candidate branch

Commit: 1a57dd088822ab1d1ae7426a3baefc19c6f497bc
Parent: ba3c45d2ef27d9dfe095e33d45d8ff5f5ace4f18

Code changes:
- StateStore now checks the presence of the history log, head checkpoint, state projection, and runtime identity as one artifact set before initializing. Partial existing state fails closed; it cannot create a new genesis and overwrite evidence.
- Existing runtime identity is never silently replaced when unreadable or empty.
- Reopening an existing store validates required event fields, product/schema/runtime identity, sequence and event-ID constraints, chain order, head checkpoint, and replay-derived state projection. Invalid projection is rejected and preserved instead of silently rewritten.
- PhoneRuntime no longer asserts authentication internally for session creation. It requires an injected session_authenticator returning exactly True; missing, rejecting, or raising verifiers deny without appending a session event.
- Added regression tests for incomplete artifacts, projection corruption without repair, and missing/rejecting/raising session verifiers.

Verification evidence directory: evidence/HG2-CLEANUP-P0-20261018/
- summary.json identifies the exact tested commit, command, environment, test count, duration, result, and log digest.
- unittest.log records the full test output.
- exit_code.txt and SHA256SUMS.txt bind the evidence files.
- Exact run: Python 3.14.6 on Android-16-aarch64-64bit-ELF; 112 tests passed in 4.792 seconds; ResourceWarning treated as error; exit code 0.
- unittest.log SHA-256: 7bc77898ac7d15ed8a1fa8e7b0fa376f22aa209f4908319b4a071fad35c9eafd.
- The test was run in the isolated candidate checkout. The active runtime and live state were not read or modified.

This hardening addresses concrete correctness/security gaps found during cleanup. It is not a claim that every PR or feature group is consolidated, and it does not authorize release or canonical-branch changes.

## 13. GitHub cleanup action completed

- PR #19 (chore: detach HG2 runtime from external host infrastructure) is now CLOSED, not merged, verified through authenticated GitHub CLI on 2026-10-18.
- Closure comment: https://github.com/OAI-GIANG/HG2/pull/19#issuecomment-6239595380
- Preserved reference branch: stt/hg2-unification-p0-20261016 @ a64e49d1619f5d83b5741d13c92961df9b07c79a. The branch was not deleted and should be used only as a source for later selective review.
- Other overlapping feature PRs were not closed. PRs #12/#13/#15 carry narrower candidate scopes and still need product-scope disposition; PRs #21/#22/#24/#25 remain distinct candidate feature groups and must not be merged wholesale without one-owner interface reconciliation.
- No merge to hg-genesis, no canonical branch mutation, no runtime change, and no live-state migration.


## 14. Selective agent/provider/tool-plane consolidation (candidate branch only)

Selected from PR #24 without merging the PR wholesale:
- hg/auth.py: credential validation and sealed, scoped AuthenticatedPrincipal.
- hg/provider.py: bounded OpenAI-compatible HTTPS transport; redirects rejected, request/response/time limits enforced, safe errors and no credential logging.
- hg/agent.py: application composition/orchestration root; it composes PhoneRuntime, provider and tool router, not canonical state directly.
- hg/toolplane.py: bounded turn/tool loop with allowlist, redacted/hash-only event audit, strict arguments and iteration/call limits.
- Focused tests copied and adapted: test_auth.py, test_provider.py, test_agent.py, test_toolplane.py.

Single-owner changes made in this candidate:
- Active runtime and tool-plane imports now use hg.policy directly; hg.authority remains only a thin compatibility facade and is removed from the active functional module registry.
- CONFIGURABLE_SCOPES is the shared source for token-scope registration and policy authenticated action sets.
- provider.invoke requires a sealed principal carrying the explicit scope; a boolean authenticated=True, generic string-ID grant, or approval request cannot authorize it.
- ToolPlane requires the PhoneRuntime interface and calls runtime.start_session(principal=...) for session creation. The tool plane no longer emits session.created directly, avoiding a second mutation route.
- Provider response parsing and tool argument parsing now reuse the canonical strict JSON parser in hg.contracts. Hash/canonical message serialization uses canonical_digest/canonical_json. Private copies of duplicate-key parser and canonical hash helpers were removed.
- manifest.json records one active model/provider boundary (hg.provider) and explicitly maps hg.authority as a compatibility facade; it does not register alternate model_gateway or model_provider modules.
- Updated README, normative architecture contract and module map to distinguish Brain/HGAgent from Heart/PhoneRuntime, and Authentication from Policy.

Focused verification after these changes: 54 tests across auth/provider/toolplane/agent/policy pass under ResourceWarning-as-error. Full-suite exact-head verification and evidence recording are pending after final review. The agent/provider modules do not invoke a real external provider in test runs; tests use fake/local transport fixtures. No token was displayed or changed; no real provider request was sent.
\nAdditional principal-bound rule: PhoneRuntime.start_session always calls authorize_principal. An injected session_authenticator must return a sealed AuthenticatedPrincipal; True/False results and exceptions fail closed. Regression coverage explicitly verifies that a boolean True does not create a session. The old authorize boolean compatibility API is no longer used by the application-session path.\n
## 15. Single-owner durable StateStore consolidation

The useful durability work from PR #5 has been selected into the existing `hg.history.StateStore`; no second file-backed state store was introduced. The current implementation now provides:

- Cross-process exclusive writer locking with on-disk refresh while locked, so two `StateStore` objects cannot append using the same stale sequence/hash.
- Atomic replacement for the state projection and checkpoint, with file `fsync` before replacement and directory `fsync` after replacement.
- A poisoned-store state after a persistence failure; later writes are denied pending investigation instead of implicitly repairing a possibly partial append.
- Strict JSON event payload snapshots, finite timestamps, strict record field/identity/sequence/hash checks, checkpoint and state-projection parity checks, and fail-closed startup when an artifact is missing or malformed.
- Detached snapshots for `emit`, `replay`, and `audit_export`, preventing callers from mutating in-memory state through returned objects.
- One shared JSON/hash implementation in `hg.contracts`, used by the durable history store, provider adapter, and tool plane; private canonicalization/parser/hash copies were removed from those owners.

Regression tests now cover write poisoning, missing history with other durable artifacts, projection corruption without repair, detached read results, and two separate store instances writing in an interleaved sequence.

Evidence `evidence/HG2-STATE-STORE-HARDENING-20261018/summary.json` is tied to tested commit `b524e5747dd2b4cb1891ea01ef15c9be4814384a`: 165 tests passed in 5.868 s on Python 3.14.6 / Android-16 aarch64; `ResourceWarning` was treated as error; exit code 0. The log SHA-256 is recorded in both `summary.json` and `SHA256SUMS.txt`.

Disposition for PR #5: its file-locking, atomic-write and poisoned-store concepts have been integrated into the single StateStore candidate implementation. Its old branch is still preserved while its unrelated product-scope/base skew is assessed; it must not be merged wholesale. PRs #1 and #11 are redundant P0 candidate branches whose core fail-closed behavior is now in the same tested StateStore, but their closure waits until their remaining unique test/value is confirmed and current PR status is rechecked.

## 16. Current cleanup state (refreshed 2026-10-18)

This section supersedes earlier inventory sections wherever they described PRs #1/#5/#11/#12/#13/#19/#24 as still open or closure as pending.

### Closed PRs — all branches preserved, none merged
- #19: broad old-base runtime/product-scope bundle; closed without merge, branch retained.
- #1, #5, #11: duplicate P0 history/state candidate branches; useful integrity/durability behavior selectively integrated into the one StateStore candidate and covered by 165-test evidence; all branches retained.
- #24: auth/provider/agent/tool-plane code selectively ported into the architecture candidate and covered by full tests; its standalone provenance/acceptance inventory remains on the retained branch.
- #12, #13: optional CTI/creative-assimilation/research benchmark candidate group; closed as non-core/reference-only for now, raw evidence and branches preserved. Nothing was erased.
- Each closure was confirmed through authenticated GitHub CLI as CLOSED with mergedAt=null. The hg-genesis branch was not changed. PR #25 remains the working draft.

### Developer-only code-intelligence scanner
The bounded static Python import scanner, its 23 unit tests, normative contract and local usage guide were selectively ported from PR #15 into tools/, tests/, contract/ and docs/. Benchmark runners and duplicate versioned evidence packs were not copied. It is deliberately excluded from manifest.json functional runtime modules. It uses hg.contracts canonical JSON/digest helpers with an explicit larger byte cap suitable for bounded scan reports; the canonical runtime default remains 1 MiB. Tests cover keeping it outside the runtime module set and using shared serialization.
- Code commit: 5ca99f5464722170812dff47ec0bb143b8e2ca5a
- Exact-commit test evidence: evidence/HG2-CODE-INTELLIGENCE-20261018/summary.json
- 190 tests passed in 7.367 s on Python 3.14.6 / Android-16 aarch64; ResourceWarning as error; exit code 0.
- Log SHA-256: 728d59bc02eb2027af9a2baeef0bf7684ee23f418e09ef1e147aa5b2ead3f53f.
- PR #15 remains open pending current-tree scan and final verification of its selective absorption, then should close without merging; its branch and research/benchmark files remain available as references.

### Remaining open work groups — do not integrate wholesale
- #22: candidate unique memory + replica/server/limits features. Integrate at most one memory subsystem and one explicit replication/outbox interface. Do not import its alternate model_gateway alongside hg.provider; do not allow server/replica to own canonical state. Reconcile against PR #25's event and SQLite models first.
- #21: task compiler/contracts and agentic capabilities/evaluators. The current agent/provider/tool-plane is already bounded. Task compiler can be considered as plan-generation input, while workflow.py remains sole task-lifecycle owner. Do not import alternate model_provider, capability registries or duplicate durable transaction stores. Evaluators and benchmarks remain developer/research tooling.
- #17: read-only connector/integration verifier is an external adapter candidate, not runtime-state owner. Compare it against typed adapter interfaces before deciding selective port.
- #8: T-018 cross-context sync candidate. Treat only as protocol adapter/test evidence; reconcile cursor/outbox/receipt schema against the current single hg.sync before integrating.
- #15: code-intelligence feature is being absorbed selectively as developer tooling. Keep its benchmark/evidence packs and original branch, and close its PR only after confirming the current scanner/tests on the candidate branch.
- #6: phone-primary platform ADR may provide a useful decision record; reconcile its invariants into the normative architecture contract rather than keep duplicate active normative contracts.
- #7 and #16: reference/red-team/absorption packs are not runtime modules. Preserve history and close only after verifying any unique blocker/evidence not yet represented in the inventory.
- #2/#3: test resource hygiene and external CI proof branches; current candidate full-suite tests run with ResourceWarning as error. Reconfirm state and unique CI value before closure; never delete their branches or assume an external CI token exists.

### Cutover and release remain blocked
No canonical branch mutation, merge, runtime switch, live-state import, APK installation, or deployment occurred. PR #25 remains a draft; tests prove only the isolated candidate at exact evidenced commits. SQLite remains opt-in; migration/cutover are separate gates.
