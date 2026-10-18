# HG2 Branch 4 — Tools · Tasks · Automation

Date: 2026-10-18

## Scope

Compared branch-specific implementations and related contracts/tests for workflow orchestration, policy, task contracts, dispatch, connectors, and tool-result handling. No bug fixes, optimization, or tests were performed. `hg-genesis` was not modified.

## Results

- Source branches reviewed: **9**
- Unique relevant logical paths: **77**
- Missing active logical paths: **0**
- Paths with multiple distinct source hashes: **4**
- Existing active files were not overwritten. All source versions remain preserved in branch-specific archives.

## Source branches

- `origin/feat/hexis-edge-schema-guard-20261013` — 3 files in source manifest
- `origin/remediation/hg2-authority-recovery-20261014` — 1 files in source manifest
- `origin/remediation/hg2-readonly-connector-20261014` — 1 files in source manifest
- `origin/stt/hg-agentic-intelligence-g1-20261017` — 45 files in source manifest
- `origin/stt/hg2-circulatory-architecture-20261018` — 63 files in source manifest
- `origin/stt/hg2-gap-integration-20261018` — 41 files in source manifest
- `origin/stt/hg2-single-system-20261017` — 50 files in source manifest
- `origin/stt/hg2-unification-p0-20261016` — 17 files in source manifest
- `origin/stt/hg2-voice-tools-design-20261018` — 39 files in source manifest

## Active implementation files

- `contract/PROVENANCE_CONTRACT_V1.md` — active; 1 source version(s), 1 distinct hash(es)
- `contract/STATE_V1.md` — active; 1 source version(s), 1 distinct hash(es)
- `contract/T018_SYNC_V2.md` — active; 1 source version(s), 1 distinct hash(es)
- `evidence/CIRCULATORY-RESTRUCTURE-20261018/sync-dispatcher-report.json` — active; 1 source version(s), 1 distinct hash(es)
- `evidence/CIRCULATORY-RESTRUCTURE-20261018/sync-dispatcher-unittest.log` — active; 1 source version(s), 1 distinct hash(es)
- `evidence/CIRCULATORY-RESTRUCTURE-20261018/sync-dispatcher.exit_code.txt` — active; 1 source version(s), 1 distinct hash(es)
- `hg/auth.py` — active; 1 source version(s), 1 distinct hash(es)
- `hg/contracts.py` — active; 1 source version(s), 1 distinct hash(es)
- `hg/durable.py` — active; 1 source version(s), 1 distinct hash(es)
- `hg/durable_transactions.py` — active; 1 source version(s), 1 distinct hash(es)
- `hg/history.py` — active; 9 source version(s), 4 distinct hash(es)
- `hg/memory.py` — active; 1 source version(s), 1 distinct hash(es)
- `hg/policy.py` — active; 1 source version(s), 1 distinct hash(es)
- `hg/provenance.py` — active; 2 source version(s), 2 distinct hash(es)
- `hg/provenance_memory.py` — active; 1 source version(s), 1 distinct hash(es)
- `hg/replica.py` — active; 1 source version(s), 1 distinct hash(es)
- `hg/sqlite_state.py` — active; 1 source version(s), 1 distinct hash(es)
- `hg/sync.py` — active; 2 source version(s), 2 distinct hash(es)
- `hg/sync_auth.py` — active; 1 source version(s), 1 distinct hash(es)
- `hg/sync_bootstrap.py` — active; 1 source version(s), 1 distinct hash(es)
- `hg/task_contract.py` — active; 1 source version(s), 1 distinct hash(es)
- `hg/workflow.py` — active; 1 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HG-NATIVE-INTELLIGENCE-FIXTURE-V2.1-REVISION-REPORT.md` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HG-NATIVE-INTELLIGENCE-V2.1-CHECKPOINT-20261017.md` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HG-NATIVE-INTELLIGENCE-V2.1-CLOSURE-REPORT.md` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HG-NATIVE-INTELLIGENCE-V2.1-INTEGRATION-NOTE.md` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HG-NATIVE-INTELLIGENCE-V2.1-SEMANTIC-REVIEW-REPORT.md` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-01-TASK-CONSTRAINTS-DEPENDENCIES.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-02-AMBIGUITY-CONFLICT.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-03-CLAIM-EVIDENCE-EPISTEMIC-LABELS.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-04-PROVENANCE-MISSING-METADATA.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-05-CREATIVE-OPTIONS-RUBRIC.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-06-FEEDBACK-DELTA-PRESERVE-CONSTRAINTS.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-07-CONTROLLED-IMPROVEMENT-EXPERIMENT.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-08-TRANSFER-BOUNDARY.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-09-COUNTEREXAMPLE-SEARCH.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-10-UNCERTAINTY-CALIBRATION.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-11-CORRECTION-CHAIN-TWO-DEPENDENTS.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-12-TOOL-RESULT-TRUTH-PARTIAL-SEQUENCE.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-13-AUTHORIZATION-STATE-TRACE.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-14-DECOY-SECRET-SINKS.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-15-CORRUPT-STATE-FAULT-CASES.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-16-REPEATABILITY-IDENTITY-RUNCOUNT.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-17-REGRESSION-CRITICAL-GATE.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-18-STATUS-AND-HISTORICAL-SOURCE-REQUEST.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-19-COMPARABLE-IMPROVEMENT-REGRESSION.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-20-DIGEST-INTEGRITY-NOT-AUTHORITY.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-21-RETRY-IDEMPOTENCY-SIDE-EFFECT.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-22-MISSING-ARTIFACT-DIGEST-MISMATCH.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-23-MANIFEST-STRUCTURE-NEGATIVES.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-24-ORACLE-POSTHOC-CHANGE.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-25-UNAPPROVED-NA-EXCLUSION.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/HNIF2-26-MISSING-EVIDENCE-STATUS-BOUNDARIES.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/README.md` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/SHA256SUMS-V2.1.txt` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/build_v21.py` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/complete_oracles_v21.py` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/manifest.json` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/test_fixture_package_v21.py` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg-native-intelligence-v2.1/validate_v21.py` — active; 5 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg_store_pre_mapping/history.jsonl` — active; 2 source version(s), 1 distinct hash(es)
- `tests/fixtures/hg_store_pre_mapping/state.json` — active; 2 source version(s), 1 distinct hash(es)
- `tests/test_authenticated_sync_transaction.py` — active; 1 source version(s), 1 distinct hash(es)
- `tests/test_durable.py` — active; 1 source version(s), 1 distinct hash(es)
- `tests/test_durable_transactions.py` — active; 1 source version(s), 1 distinct hash(es)
- `tests/test_history_malformed_shapes.py` — active; 1 source version(s), 1 distinct hash(es)
- `tests/test_memory.py` — active; 1 source version(s), 1 distinct hash(es)
- `tests/test_phone_runtime_sync_integration.py` — active; 1 source version(s), 1 distinct hash(es)
- `tests/test_policy.py` — active; 1 source version(s), 1 distinct hash(es)
- `tests/test_provenance.py` — active; 2 source version(s), 2 distinct hash(es)
- `tests/test_replica.py` — active; 1 source version(s), 1 distinct hash(es)
- `tests/test_sqlite_state.py` — active; 1 source version(s), 1 distinct hash(es)
- `tests/test_sync.py` — active; 1 source version(s), 1 distinct hash(es)
- `tests/test_sync_auth.py` — active; 1 source version(s), 1 distinct hash(es)
- `tests/test_sync_bootstrap.py` — active; 1 source version(s), 1 distinct hash(es)
- `tests/test_t018_sync.py` — active; 1 source version(s), 1 distinct hash(es)
- `tests/test_workflow.py` — active; 1 source version(s), 1 distinct hash(es)

## Conflicts

- `hg/history.py` — 4 source variants; preserved separately.
- `hg/provenance.py` — 2 source variants; preserved separately.
- `hg/sync.py` — 2 source variants; preserved separately.
- `tests/test_provenance.py` — 2 source variants; preserved separately.

## Missing paths

- None in the selected inventory.

Detailed SHA-256 and source-branch data: `HG2-BRANCH4-TOOLS-TASKS-AUTOMATION-INVENTORY-20261018.json`.
