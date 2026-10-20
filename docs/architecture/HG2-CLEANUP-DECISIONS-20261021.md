# HG2 — System Cleanup Decision Record — 2026-10-21

- Repository: `OAI-GIANG/HG2`
- Cleanup branch: `stt/hg2-master-cleanup-20261021`
- Base commit: `f855bd3728bfad5f91c53aa64652067aa7639aa7`
- Environment: Android/Termux, AArch64, Python 3.14.6
- Status: **TESTED candidate; NOT merged; NOT production-verified**

## Findings and disposition

| Finding | Evidence / risk | Decision | Required follow-up |
|---|---|---|---|
| Planning was modeled as a fifth worker domain alongside the Brain coordinator | `hg/brain_orchestrator.py` included `planning_coordination`; this conflicted with the 1+4 ownership rule and exposed planning capability names as peer adapters | **FIXED in candidate**: four subordinate domains only; planning remains central control-plane responsibility | Retest route budget, unknown-capability rejection and registry/API integration; keep the old taxonomy as historical evidence |
| Creative assimilation was absent from the latest integrated branch | A prior HG2 feature branch had a pure-stdlib candidate lifecycle and tests | **RESTORED selectively**: `hg/creative_assimilation.py`, its test and source/contract documentation | It is not yet bound to a live Brain adapter; do not claim runtime capability |
| Code intelligence was absent from the latest integrated branch | Prior feature module provides bounded, non-executing source inventory/import-impact analysis | **RESTORED selectively**: `tools/hg_code_intelligence.py`, tests and usage documentation | CLI is local-only and not a Brain capability until an authorized adapter and contract exist |
| Voice tooling was absent from the latest integrated branch | Prior branch has a local CLI, bounded adapters, corpus-rights gate and 63 tests | **RESTORED selectively** under `tools/voice` | TTS quality remains `NOT_ACCEPTED`; Whisper.cpp needs explicitly installed hash-pinned executable/model; no runtime integration or model cloning is claimed |
| Runtime state ownership is split across implementations | `PhoneRuntime` constructs `history.StateStore`; `sync.py` also uses it. `sync_dispatcher.py` and `workflow_store_adapter.py` instead require `SQLiteStateStore`; the workflow adapter explicitly says it has not cut over the live PhoneRuntime. `durable_transactions.py` adds another transaction ledger | **P0 ARCHITECTURE CONFLICT — HOLD; delete nothing yet** | Decide one canonical persistence boundary; map sync/outbox/workflow semantics; migrate with compatibility and crash-recovery tests before retiring any store |
| Workflow lifecycle and durable transaction logic overlap | `hg/workflow.py`, `hg/workflow_store_adapter.py`, and `hg/durable_transactions.py` model related but not identical concepts | **KEEP current integrated workflow path; do not delete transaction ledger yet** | Prove whether all plan/step/evidence/IN_DOUBT semantics can be represented by the canonical store before deprecating/removing anything |
| Evidence and source-branch archives increase repository size | `docs/consolidation/source-branches`, `evidence/`, and manifests contain source snapshots, hashes and historical test records | **PRESERVE**: size alone is not proof of redundancy; deletion could destroy provenance/recovery | Verify archive manifests and references individually before any later compaction/removal |
| Original checkout has untracked review artifacts and bytecode caches | Original checkout was on an older voice branch, with five large untracked `docs/review/*.json` files and `.pyc` files | **PRESERVE original checkout untouched**; cleanup work is isolated in a separate worktree | Remove only bytecode generated inside this new cleanup worktree after final status/checkpoint |

## Canonical logical ownership (1+4)

1. **Central Brain** — intake, classification, planning, routing, orchestration, synthesis and task-level control.
2. **Memory · Knowledge · History** — memory retrieval, provenance, durable state and history.
3. **Creative · Research · Experiments** — source-grounded research, synthesis, candidate evaluation and controlled experiments.
4. **Tools · Tasks · Automation** — local code intelligence, voice CLI, skills, task workflow and bounded tool adapters.
5. **Security · Policy · Verification · Sync** — authority, policy, evidence verification, integrity, synchronization and recovery.

These are five logical responsibility areas, not five independent command authorities, processes or Git branches. `planning_coordination` is not a peer worker branch.

## Verification record

- Latest integrated baseline before edits: `python -m unittest discover -s tests -p 'test*.py' -v` — **380 tests passed**.
- Prior feature branch baseline: core suite **248 passed**, voice suite **63 passed**.
- Cleanup candidate after code changes: core suite `python -m unittest discover -s tests -p 'test*.py' -q` — **429 tests passed**.
- Cleanup candidate voice suite from `tools/voice`: `python -m unittest discover -s tests -p 'test*.py' -q` — **63 tests passed**.
- Aggregate candidate tests: **492 passed, 0 failed** across the two discovery roots.
- Focused post-patch run: `tests.test_brain_orchestrator`, `tests.test_capability_registry`, `tests.test_server` — **52 tests passed**.
- Tests were executed on Termux, Python 3.14.6, Android AArch64. They prove the tested code paths only; they do not prove production routing of all four subordinate domains.

## Release / destructive-operation gates

- No deletion of durable-state implementations, historical evidence or archived source snapshots in this pass.
- No live service restart or deploy was performed. The observed `hg2-runtime` runs from `~/hg2-phone`; `hg-backend` and `hg-runtime` were down at inspection time. That runtime checkout was not modified.
- No push or merge was performed. The candidate remains isolated pending final diff, import/compile checks, a regression rerun if code changes continue, and evidence/checkpoint sealing.
- `VERIFIED`, `PRODUCTION`, and `CLOSED_VERIFIED` are not claimed.

## Static dependency scan (read-only)

- Analyzer: `tools/hg_code_intelligence.py` version 1.0.0, source revision `7c5c1bc546acf6d1252ebb5158baae84149c5ecf`.
- Snapshot SHA-256: `9d87f4e24627745f54281bb18c81b84f1bbc616ee7653e93ff0834424f54e22d`; report SHA-256: `17e951cf7a0a1d3aa226f5a59c2ffbd136a68dd38e4c0fd326417e097d6e4085`.
- Files seen: 784; Python files: 206 total / 206 parsed / 0 parse failures; dynamic import sites: 16; unclassified files: 334; unsupported non-Python source files: 244.
- Coverage is explicitly **INCOMPLETE** because the repository contains source archives, evidence, JSON, logs and other non-Python files. The impact report for `hg/history.py`, `hg/sqlite_state.py`, `hg/durable_transactions.py`, and `hg/workflow_store_adapter.py` reports `KNOWN_DEPENDENTS_ONLY_INCOMPLETE_COVERAGE`.
- The scan confirms a state-store split but cannot by itself prove runtime reachability, semantic equivalence, or safe deletion. No state implementation was deleted. Exact SHA-256 matches were confirmed for `hg/sqlite_state.py` and `tests/test_sqlite_state.py` against archived copies under `docs/consolidation/source-branches/origin__stt__hg2-circulatory-architecture-20261018/`.
