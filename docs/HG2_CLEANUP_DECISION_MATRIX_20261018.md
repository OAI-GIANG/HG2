# HG2 Cleanup Decision Matrix — 2026-10-18

**Repository:** `OAI-GIANG/HG2`  
**Canonical:** `hg-genesis` @ `9d83a113ccdf1aeda656e494593fa55b9078c803`  
**Candidate:** `stt/hg2-circulatory-architecture-20261018` @ `c62421d5c2b45759dcd9c9e0106237101848201a`  
**Scope:** GitHub repository cleanup only. No canonical branch mutation, production runtime switch, live-state migration, or deployment.

## Decision rule

Use one owner for each runtime responsibility. Keep unique capability/evidence until its disposition is verified. Close a PR only when its useful content is integrated or explicitly classified as reference-only and closure does not hide an unresolved safety gate. Preserve source branches. A closed PR does not mean its capability is certified or deleted from history.

## Capability ownership matrix

| Capability | Candidate owner / boundary | Overlap or alternative | Decision | Verification / risk |
|---|---|---|---|---|
| Application orchestration | `hg.agent` | PR #21 agentic planner/evaluator; PR #22 server composition | Keep `hg.agent` as composition root; evaluate planner separately | Unit and architecture tests pass; real provider not called in tests |
| Authentication | `hg.auth` | policy checks embedded in tools/provider/legacy connector | Keep credentials/principal minting separate from authorization | Sealed principal and fail-closed tests pass |
| Authorization and approval | `hg.policy` | `hg.authority` facade; policy/action logic in alternate branches | One policy decision owner; authority is compatibility-only | Architecture tests assert facade and single-sourced scopes |
| Canonical serialization/event envelope | `hg.contracts` | private serializers/hash helpers in alternate tools | Shared strict JSON, canonical JSON and digest | Contract + architecture tests pass; runtime default size bound remains strict |
| Durable event/history | `hg.history.StateStore` (candidate default) | `hg.sqlite_state.SQLiteStateStore`; PR #21 transaction/evidence stores; PR #22 memory/outbox | One selected backend per state directory; SQLite remains explicit opt-in, no dual authority | 190 tests pass; production backend cutover NOT approved |
| Task lifecycle | `hg.workflow` | PR #21 task compiler/transaction coordinator, PR #22 service flow | Workflow owns persisted lifecycle; planner/compiler may only supply validated plans | Tests pass; do not import a second durable lifecycle store |
| Model/provider boundary | `hg.provider` | PR #21 `model_provider`, PR #22 `model_gateway` | Keep one provider transport boundary; alternate names are adapter/reference candidates, not additional runtime owners | Redaction, TLS URL/redirect, bound request/response, principal tests pass; live provider E2E NOT RUN |
| Tools/capability execution | `hg.toolplane` | PR #21 capabilities/scripts, PR #17 read-only connector | ToolPlane routes through runtime and policy; integrate connector only as a typed read-only adapter after exact contract review | 190 tests pass; PR #17 current credentials/status remain blocked |
| Local-to-edge sync | `hg.sync` and state outbox | PR #8 T-018 sync spool, PR #22 replica/outbox | One outbox/cursor/receipt owner; #8 has unique negative/evidence value, do not merge wholesale | Candidate unit tests pass; authenticated production peer/end-to-end sync NOT proven |
| Migration and recovery | `hg.migration`, `hg.recovery` | PR #22 import/reconcile scripts and rehearsal evidence | Keep isolated source inspection, explicit verified migration, backup/restore checks; do not overwrite live state | Unit tests pass; production rollback/power-loss proof still BLOCKED |
| Developer code intelligence | `tools/hg_code_intelligence.py` (not in manifest/runtime) | PR #15 and parts of PR #19 | Selectively integrated; close PR #15 without merge, preserve branch and original evidence | 190-test exact-current-head Termux run PASS; CircleCI PR #25 PASS |
| Voice Tools / speech adapter | PR #26 draft tool-local adapter | New standalone capability, not a duplicate provider/runtime owner | Keep as separate draft/reference; do not wire into runtime during cleanup | Its own reported 26-test suite/18 voice tests; Vietnamese accuracy, model-weight license, device-resource performance, TTS and latest CI are gates |
| Memory + replication API | PR #22 | Overlaps `hg.history`, `hg.sync`, `hg.provider`, `hg.phone_runtime` | Keep PR open as blocked candidate; port only proven unique memory/replication requirements after interface reconciliation | PR itself records production cutover, credentials, TLS and encryption-at-rest as blockers |
| Agentic intelligence / task compiler | PR #21 | Overlaps provider, workflow, capabilities and durable transactions | Keep draft open as optional planning/evaluation source; do not absorb wholesale | Exact current candidate evidence reports runtime provenance/trust-root/live-model/rollback gates BLOCKED |
| Read-only GitHub connector | PR #17 | Runtime adapter surface | Keep draft open, isolated as optional adapter; no broad GitHub capability and no automatic retry when auth blocked | PR evidence says current upstream credential state BLOCKED/401 and current positive bearer E2E NOT_RUN |
| Sync V2 / T-018 | PR #8 | Overlaps `hg.sync` and SQLite outbox | Keep until unique protocol/evidence and tests are reconciled; never count a local hash chain as authenticated provenance | The PR itself states no authenticated peer, no integration into PhoneRuntime and independent review NOT RUN |
| Independent audit/blocker plan | PR #16 | Documentation/evidence, not runtime code | Keep draft: it records unresolved credential/audit/recovery risks not replaced by this architecture candidate | Its own status keeps release blocked |
| Phone-primary ADR | PR #6 | The candidate architecture contract repeats some platform invariants | Keep/reconcile as decision history; do not merge stale base blindly or close until exact normative facts are represented on current base | One-file ADR at old base `d11e71ed…`; branch/base mismatch needs reconciliation |
| Selective-absorption reference pack | PR #7 | Research/reference only | Keep as provenance/history until its unique source decisions are linked from the inventory | Old base `d11e71ed…`; provenance/independent review gates explicitly incomplete |
| P0 resource cleanup | PR #2 | Its sole changed file is `tests/test_core.py`, also touched by PR #8 and already hardened on candidate | Close without merge only after current candidate tests plus PR #3 CI evidence are verified; preserve branch | Candidate tests treat ResourceWarning as error; PR #25 CircleCI passes |
| External CI/review checklist | PR #3 | `.circleci/config.yml` and review checklist, while current PR #25 has a passing CircleCI check | Do not merge its stale CI config wholesale; preserve the checklist/history or link the relevant checklist to the current evidence | CI job passed on old branch; PR #25 exact SHA has CircleCI PASS |
| Legacy source branches | branches referenced by closed/superseded PRs | Historical implementation/evidence | Preserve all branches; no branch deletion in this pass | Verified references remain available through Git history |

## Pull-request disposition

| PR | Current status at audit | Action now | Reason |
|---|---|---|---|
| #1 | CLOSED, not merged | Preserve branch | P0 state-integrity path selectively replaced on candidate |
| #2 | OPEN | Close without merge after documenting current-suite replacement | Test-only old-baseline change; candidate's strict suite and PR #25 CI now pass |
| #3 | OPEN | Close without merge after preserving review checklist link/reference | CI-only old-base change; current candidate has passing CircleCI on exact head |
| #5 | CLOSED, not merged | Preserve branch | Durability mechanisms selectively integrated into the single file StateStore |
| #6 | OPEN | Keep as ADR/history; stale-base reconcile required | Unique one-file platform decision record, not production certification |
| #7 | OPEN | Keep reference-only pending source/provenance cross-link | Unique absorption decision/provenance record; base skew and review gates remain |
| #8 | OPEN | Keep until protocol reconciliation | Unique T-018 fail-closed batch/cursor evidence; core overlaps, but not yet proven redundant in full |
| #11 | CLOSED, not merged | Preserve branch | P0 validation coverage selectively superseded on candidate |
| #12/#13 | CLOSED, not merged | Preserve branches and raw benchmark evidence | Optional research/benchmark candidates, not runtime owners |
| #15 | CLOSED, not merged | Preserve branch/evidence | Code-intelligence scanner selectively integrated and current candidate passed 190 tests |
| #16 | OPEN draft | Keep | Active audit/blocker record for unresolved security, credential, and recovery gates |
| #17 | OPEN draft | Keep | Optional adapter has current authentication and E2E blockers; not safe to mark superseded |
| #19 | CLOSED, not merged | Preserve branch | Broad mixed-scope bundle; source history retained for selective review |
| #21 | OPEN draft | Keep as optional intelligence/planning candidate | Unique evaluator/task-planning material, but trust/provenance/live-model/rollback acceptance blocked |
| #22 | OPEN | Keep as blocked memory/replication candidate | Useful unique staging/backup evidence; production cutover remains blocked |
| #24 | CLOSED, not merged | Preserve branch | Agent/provider/toolplane selected into current candidate; remaining provenance inventory retained for reference |
| #25 | OPEN draft | Keep as sole integration candidate for this cleanup pass | Current candidate HEAD `c62421d5…`, 190/190 Termux tests pass, CircleCI exact-head check passes; not merged/certified/released |
| #26 | OPEN draft | Keep separate | Voice Tools is a bounded optional developer/tool capability; language quality, redistribution, resource and TTS gates remain |

## Explicit completion gates

- [x] Refresh exact canonical SHA, candidate SHA and GitHub PR list.
- [x] Candidate test run on Termux: `PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest discover -s tests -v` → 190 passed, 0 failed.
- [x] `git diff --check origin/hg-genesis...HEAD` passes.
- [x] Candidate branch pushed; remote branch SHA equals local `c62421d5c2b45759dcd9c9e0106237101848201a`.
- [x] CircleCI check for PR #25 at current candidate SHA reports PASS.
- [x] Canonical `hg-genesis` unchanged at `9d83a113ccdf1aeda656e494593fa55b9078c803`.
- [x] PR #15 closed without merge and branch preserved.
- [ ] Entire open-PR backlog resolved. Several PRs contain still-unverified unique capability/evidence or explicit acceptance blockers, so indiscriminate closure is unsafe.
- [ ] Production backend migration, runtime restart/deployment, or release: expressly outside this cleanup completion.

## Final assessment

**CLEANUP_STATUS=PARTIAL_COMPLETION / INTEGRATION_CANDIDATE_VERIFIED**  
**CANDIDATE_TESTS=PASS (190/190)**  
**PR25_CIRCLECI=PASS at `c62421d5c2b45759dcd9c9e0106237101848201a`**  
**CANONICAL_MUTATED=false**  
**LIVE_RUNTIME_OR_STATE_MUTATED=false**  
**PRODUCTION_CUTOVER=BLOCKED / NOT_RELEASED**

This matrix deliberately does not equate fewer open PRs with a clean system. Remaining PRs are kept where their content is not proven redundant or where they document real release/security blockers. Close/merge/delete is not a substitute for capability reconciliation.
