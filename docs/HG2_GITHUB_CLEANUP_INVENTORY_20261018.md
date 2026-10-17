# HG2 GitHub Cleanup Inventory — 2026-10-18

**Purpose:** one authoritative inventory for the HG2 cleanup pass. Detailed component-by-component decisions live in [`HG2_CLEANUP_DECISION_MATRIX_20261018.md`](HG2_CLEANUP_DECISION_MATRIX_20261018.md). This file is an index, not a second competing policy document.

## Canonical scope

- Repository: `OAI-GIANG/HG2` only.
- Canonical branch: `hg-genesis`, verified at `9d83a113ccdf1aeda656e494593fa55b9078c803`.
- Integration candidate: PR #25, branch `stt/hg2-circulatory-architecture-20261018`; draft, not merged or released.
- Optional tool candidate: PR #26 (Voice Tools); draft, not runtime-integrated.
- Runtime authority: phone remains primary. No runtime restart, state migration, database write, credential change, deploy or release was performed during this cleanup pass.

## Current owner map on candidate branch

| Responsibility | Candidate owner | Boundary |
|---|---|---|
| App orchestration | `hg.agent` | Composition/orchestration only; does not own canonical state directly |
| Authentication | `hg.auth` | Validates credential and mints sealed scoped principal |
| Authorization/approval | `hg.policy` | One policy decision point; `hg.authority` is compatibility façade only |
| Canonical schema/JSON/digest | `hg.contracts` | Shared strict parsing, canonicalization, event envelope and digest |
| Phone runtime | `hg.phone_runtime` | Composition root; chooses exactly one state backend |
| Durable file history | `hg.history.StateStore` | Single file-backed history owner, cross-process lock, atomic checkpoint/projection and fail-closed startup/write behavior |
| Optional SQLite backend | `hg.sqlite_state.SQLiteStateStore` | Explicit opt-in candidate; no live cutover, no concurrent canonical authority |
| Task lifecycle | `hg.workflow` | Single persisted task state machine |
| Provider transport | `hg.provider` | One bounded HTTPS provider boundary; no real provider request in tests |
| Tool execution | `hg.toolplane` | Bounded, authenticated, policy-gated tool loop, mutations routed through PhoneRuntime |
| Sync transport | `hg.sync` | Candidate outbox/dispatcher; not proof of an authenticated production peer |
| Migration/recovery | `hg.migration`, `hg.recovery` | Explicit staged migration and verified backup/restore helpers; no live migration performed |
| Developer code intelligence | `tools/hg_code_intelligence.py` | Read-only, static Python import analysis; excluded from runtime manifest |

## Verified implementation and evidence

- Selected useful bounded agent/provider/tool-plane work from PR #24; did not merge its entire branch.
- Selected durable StateStore hardening concepts from PR #5 into `hg.history.StateStore`; did not introduce a second file-backed store.
- Selected the read-only code-intelligence scanner from PR #15 as developer tooling, not runtime functionality.
- Evidence directories tied to exact commits are preserved in `evidence/HG2-CLEANUP-P0-20261018/`, `evidence/HG2-AGENT-PLANE-20261018/`, `evidence/HG2-STATE-STORE-HARDENING-20261018/`, and `evidence/HG2-CODE-INTELLIGENCE-20261018/`.
- Strict Termux command: `PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest discover -s tests`.
- Last verified suite during cleanup: 190 tests, zero failures, `ResourceWarning` treated as error. The strict suite and CircleCI were rerun on the exact current PR #25 HEAD after the documentation/CI updates; final results are reported with the exact SHA at closeout.
- CircleCI PASS had been observed on a verified candidate head before follow-up cleanup-document edits; latest follow-up head status is rechecked before concluding.

## GitHub PR disposition

See the linked decision matrix for the full disposition and rationale. PRs were closed without merging only after recording why and preserving their branches/evidence. The closed set is #1, #2, #3, #5, #6, #7, #8, #11, #12, #13, #15, #16, #17, #19, #21, #22, and #24, all not merged. Their branches and historical evidence remain preserved. The only open streams are #25 (core architecture candidate) and #26 (optional standalone Voice Tools).

Closing these PRs did not delete their source branches or imply that their unique feature proposals were integrated. Unique unaccepted capabilities remain reference-only until selected through the single-owner matrix and independently tested at a new exact commit.

## Non-negotiable remaining gates

- PR #25 is still draft and unmerged; this candidate is not a release certification.
- Runtime/build provenance and trust-root lifecycle remain unverified.
- SQLite remains opt-in. No production state migration, restart, deploy or cutover.
- Authenticated cross-runtime/remote peer operation, production credential health, encryption-at-rest for sensitive replica data, and power-loss/rollback acceptance remain blocked where applicable.
- Voice Tools in PR #26 is not integrated into runtime; Vietnamese quality, device-resource behavior, TTS and model-weight redistribution rights are not certified.
- Do not delete retained source branches, raw evidence or historical records merely to reduce item count. Remove source files only after use/import/reference and recovery-path checks.

## Final status

`CLEANUP_STATUS=PR_BACKLOG_CONSOLIDATED / CORE_CANDIDATE_VERIFIED`
`CANONICAL_MUTATED=false`
`LIVE_RUNTIME_OR_STATE_MUTATED=false`
`PRODUCTION_CUTOVER=BLOCKED / NOT_RELEASED`
