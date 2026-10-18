# HG2 Cleanup Decision Matrix — 2026-10-18

**Repository:** `OAI-GIANG/HG2`
**Canonical:** `hg-genesis` @ `9d83a113ccdf1aeda656e494593fa55b9078c803`
**Candidate:** PR #25, branch `stt/hg2-circulatory-architecture-20261018` (latest SHA is tracked by GitHub; strict suite and CircleCI are rechecked for exact current HEAD at closeout).
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
| Durable event/history | `hg.history.StateStore` (candidate default) | PR #4/#18 old-base integrity proposals; `hg.sqlite_state.SQLiteStateStore`; PR #21 transaction/evidence stores; PR #22 memory/outbox | One selected backend per state directory; SQLite remains explicit opt-in, no dual authority | 190 tests pass; production backend cutover NOT approved |
| Task lifecycle | `hg.workflow` | PR #21 task compiler/transaction coordinator, PR #22 service flow | Workflow owns persisted lifecycle; planner/compiler may only supply validated plans | Tests pass; do not import a second durable lifecycle store |
| Model/provider boundary | `hg.provider` | PR #21 `model_provider`, PR #22 `model_gateway` | Keep one provider transport boundary; alternate names are adapter/reference candidates, not additional runtime owners | Redaction, TLS URL/redirect, bound request/response, principal tests pass; live provider E2E NOT RUN |
| Tools/capability execution | `hg.toolplane` | PR #21 capabilities/scripts, PR #17 read-only connector | ToolPlane routes through runtime and policy; integrate connector only as a typed read-only adapter after exact contract review | 190 tests pass; PR #17 current credentials/status remain blocked |
| Local-to-edge sync | `hg.sync` and state outbox | PR #8 T-018 sync spool, PR #22 replica/outbox | One outbox/cursor/receipt owner; #8 has unique negative/evidence value, do not merge wholesale | Candidate unit tests pass; authenticated production peer/end-to-end sync NOT proven |
| Migration and recovery | `hg.migration`, `hg.recovery` | PR #22 import/reconcile scripts and rehearsal evidence | Keep isolated source inspection, explicit verified migration, backup/restore checks; do not overwrite live state | Unit tests pass; production rollback/power-loss proof still BLOCKED |
| Developer code intelligence | `tools/hg_code_intelligence.py` (not in manifest/runtime) | Earlier PR #14, updated coverage PR #15 and parts of PR #19 | Selectively integrated; close PR #15 without merge, preserve branch and original evidence | 190-test exact-current-head Termux run PASS; CircleCI PR #25 PASS |
| Voice Tools / speech adapter | PR #26 draft tool-local adapter | New standalone capability, not a duplicate provider/runtime owner | Keep as separate draft/reference; do not wire into runtime during cleanup | Its own reported 26-test suite/18 voice tests; Vietnamese accuracy, model-weight license, device-resource performance, TTS and latest CI are gates |
| Memory + replication API | `hg.history` / `hg.sync` candidate boundaries | PR #22 branch preserved as reference | PR #22 closed without merge: unique memory/replica concepts remain reference-only until explicit interface integration; production cutover remains blocked | PR itself records production cutover, credentials, TLS and encryption-at-rest as blockers |
| Agentic intelligence / task compiler | `hg.agent` and `hg.workflow` candidate boundaries | PR #21 branch preserved as reference | PR #21 closed without merge: unique planner/compiler/evaluator materials are preserved for selective future integration; do not introduce second provider/transaction/evidence owners | Exact current candidate evidence reports runtime provenance/trust-root/live-model/rollback gates BLOCKED |
| Read-only GitHub connector | Optional adapter boundary | PR #17 branch preserved as reference | PR #17 closed without merge: upstream credential is blocked and positive-bearer E2E is NOT_RUN; no integration until revalidated | PR evidence says current upstream credential state BLOCKED/401 and current positive bearer E2E NOT_RUN |
| Sync V2 / T-018 | `hg.sync` adapter boundary | PR #8 branch/evidence preserved | PR #8 closed without merge: preserve unique test/protocol material for later reconciliation; unkeyed local hash chains are not authenticated provenance | The PR itself states no authenticated peer, no integration into PhoneRuntime and independent review NOT RUN |
| Independent audit/blocker plan | Cleanup matrix + retained PR #16 branch | Documentation/evidence, not runtime code | PR #16 closed as a stale review-plan stream; credential/audit/recovery findings remain BLOCKED and are preserved in the record | Its own status keeps release blocked |
| Phone-primary ADR | `contract/CIRCULATORY_ARCHITECTURE_V1.md` + retained PR #6 branch | One-file documentation proposal | PR #6 closed without merge after phone-primary invariant was recorded in current architecture contract; original ADR remains on preserved branch | One-file ADR at old base `d11e71ed…`; branch/base mismatch needs reconciliation |
| Selective-absorption reference pack | Retained PR #7 branch | Research/reference only | PR #7 closed without merge; original provenance document/history preserved, and incomplete provenance gates remain unresolved | Old base `d11e71ed…`; provenance/independent review gates explicitly incomplete |
| P0 / ResourceWarning hygiene | Current strict candidate regression suite | PR #2 and #23 old test-only branches; PR #3 old CI branch | PR #2 closed without merge after strict 190-test suite and candidate CI passed; branch preserved | Candidate tests treat ResourceWarning as error; PR #25 CircleCI passes |
| External CI/review checklist | Current `.circleci/config.yml` and cleanup matrix | PR #3 old CI branch | PR #3 closed without merge after exact-head candidate CI passed; preserve the review checklist/history on its branch | CI job passed on old branch; PR #25 exact SHA has CircleCI PASS |
| Legacy source branches | branches referenced by closed/superseded PRs | Historical implementation/evidence | Preserve all branches; no branch deletion in this pass | Verified references remain available through Git history |

## Pull-request disposition

| PR | Current status at audit | Action now | Reason |
|---|---|---|---|
| #1 | CLOSED, not merged | Preserve branch | P0 state-integrity path selectively replaced on candidate |
| #2 | CLOSED, not merged | Preserve branch | Test-only old-baseline change superseded by candidate strict suite; T-018 material is retained separately on closed branch #8 |
| #3 | CLOSED, not merged | Preserve branch and independent-review checklist | CI-only old-base change superseded by current candidate CI; no old CI branch merged |
| #4 | CLOSED, not merged | Preserve integrity proposal branch | Fail-closed artifact/projection checks are represented in the current StateStore candidate; old-base PR remains reference-only |
| #5 | CLOSED, not merged | Preserve branch | Durability mechanisms selectively integrated into the single file StateStore |
| #6 | CLOSED, not merged | Preserve ADR branch/history | Phone-primary invariant is recorded in the current architecture contract; the one-file PR targeted a stale base |
| #7 | CLOSED, not merged | Preserve reference pack/branch | Source provenance and independent-review gates remain incomplete; no runtime feature needed from this stale-base PR |
| #8 | CLOSED, not merged | Preserve T-018 contract, raw evidence, tests and branch | Useful protocol/evidence remains a reference for later selective integration; current candidate sync/outbox tests do not establish authenticated production peers |
| #11 | CLOSED, not merged | Preserve branch | P0 validation coverage selectively superseded on candidate |
| #12/#13 | CLOSED, not merged | Preserve branches and raw research/evidence | Creative-assimilation and CTI remediation proposals remain reference-only, not runtime owners |
| #14 | CLOSED, not merged | Preserve original code-intelligence proposal branch/evidence | Earlier bounded scanner proposal is superseded by the updated #15 coverage work selectively integrated into candidate tooling |
| #15 | CLOSED, not merged | Preserve branch/evidence | Scanner selectively integrated and tested on candidate; PR was closed after exact-head suite passed |
| #16 | CLOSED, not merged | Preserve blocker/red-team report and branch | Blocking findings are retained here; close the stale review-plan PR as documentation/history, without implying gates passed |
| #17 | CLOSED, not merged | Preserve connector source and evidence branch | Upstream credential state is blocked and positive-bearer E2E is NOT_RUN; no integration until revalidated |
| #18 | CLOSED, not merged | Preserve malformed-record guard branch/evidence | Candidate StateStore now validates malformed record shapes fail-closed and the strict full suite covers the behavior |
| #19 | CLOSED, not merged | Preserve branch | Broad mixed-scope bundle; source history retained for selective review |
| #21 | CLOSED, not merged | Preserve agentic-intelligence source and evidence branch | Unique planner/compiler/evaluator material remains available for selective future integration; trust/provenance/live-model/rollback gates block integration today |
| #22 | CLOSED, not merged | Preserve memory/replication source and evidence branch | Unique memory/replica concepts remain reference-only; production cutover, credentials, TLS/encryption-at-rest and restore/rollback are blocked |
| #23 | CLOSED, not merged | Preserve test-hygiene branch | Current full suite is run with ResourceWarning as error and passes; no separate old-base test-only integration needed |
| #24 | CLOSED, not merged | Preserve branch | Agent/provider/toolplane selected into current candidate; remaining provenance inventory retained for reference |
| #25 | OPEN draft | Keep as sole core integration candidate | Exact current HEAD is checked by the final GitHub/Termux/CircleCI verification; not merged, certified, or released |
| #26 | OPEN draft | Keep separate | Voice Tools is a bounded optional developer/tool capability; language quality, redistribution, resource and TTS gates remain |

## Explicit completion gates

- [x] Refresh exact canonical SHA, candidate SHA and GitHub PR list.
- [x] Candidate test run on Termux: `PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest discover -s tests -v` → 190 passed, 0 failed.
- [x] `git diff --check origin/hg-genesis...HEAD` passes.
- [x] Candidate branch pushed; local and remote branch head were compared at closeout; the exact current SHA is shown in PR #25 metadata.
- [x] CircleCI check for PR #25 at current candidate SHA reports PASS.
- [x] Canonical `hg-genesis` unchanged at `9d83a113ccdf1aeda656e494593fa55b9078c803`.
- [x] PR #15 closed without merge and branch preserved.
- [x] Legacy/overlapping and stale-base PR delivery streams closed with reasoned comments; source branches and evidence retained.
- [x] Verified only two open PRs remain: #25 (single core integration candidate) and #26 (optional standalone Voice Tools candidate).
- [ ] Production backend migration, runtime restart/deployment, or release: expressly outside this cleanup completion.

## Verified GitHub cleanup closure

As checked after the closure actions, the only open pull requests are:

- #25 — the single core architecture/integration candidate (draft, unmerged).
- #26 — the separate optional Voice Tools candidate (draft, unmerged).

PRs #1, #2, #3, #4, #5, #6, #7, #8, #11, #12, #13, #14, #15, #16, #17, #18, #19, #21, #22, #23, and #24 are CLOSED with `mergedAt=null`. Their source branches were not deleted. The `hg-genesis` branch remains at `9d83a113ccdf1aeda656e494593fa55b9078c803`.

Latest exact-head verification is performed on GitHub PR #25 at closeout; a documentation-only follow-up commit is re-run through the strict test suite and CircleCI before final status is recorded. Do not treat source branches retained for reference as active runtime dependencies.

## Final assessment

**CLEANUP_STATUS=PR_BACKLOG_CONSOLIDATED / CORE_CANDIDATE_VERIFIED**
**CANDIDATE_TESTS=PASS (190/190)**
**PR25_CIRCLECI=PASS on the exact current PR #25 HEAD as verified at closeout**
**CANONICAL_MUTATED=false**
**LIVE_RUNTIME_OR_STATE_MUTATED=false**
**PRODUCTION_CUTOVER=BLOCKED / NOT_RELEASED**

This matrix deliberately does not equate fewer open PRs with production readiness. The two remaining PRs represent distinct candidate scopes; all other PRs were closed without merge and their branches/evidence were retained. Unique functionality on closed candidate branches is not claimed to be integrated or certified. One-owner capability reconciliation and runtime/release gates still apply.
