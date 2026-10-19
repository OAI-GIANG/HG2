# HG2 — P0-A Atomic State Recovery Closure

- Audit ID: HG2-P0A-ATOMIC-STATE-RECOVERY-20261019-R1
- Repository: OAI-GIANG/HG2 only
- Base commit: `c2161feb76b2be8964a109910475a5b1a018eb1a`
- Candidate branch: `stt/hg2-brain-orchestrator-r1-20261019`
- Environment: Android/Termux, aarch64, Python 3.14.6
- Test data: temporary directories only; no production runtime state opened or changed
- Dependencies installed: none
- PR #29 at final check: OPEN · DRAFT; merge/deploy not performed

## 1. Decision

**P0-A: PASS FOR THE DECLARED RECOVERABLE CRASH WINDOWS.** The full regression suite passes after the change. Abrupt child-process termination using `os._exit`, injected write/flush/fsync/rename faults, restart and replay show that completed events are recovered exactly once in the test matrix, while an incomplete uncommitted event frame is preserved as evidence and does not become an event. A `StateStore` instance whose append or projection/checkpoint write raises is marked recovery-required and refuses any further `emit()` until a fresh instance validates/reconciles disk state. Reopening and replay verify the event chain and projection after recovery.

This is not a claim of successful recovery from arbitrary corruption or physical flash/power loss. States that lack sufficient evidence remain fail-closed and are not repaired.

## 2. Canonical state decision

The single canonical state authority remains the append-only `history.jsonl` event journal under `hg/history.py::StateStore`.

- `history.jsonl`: canonical ordered event stream; every complete event is validated for schema, sequence, runtime identity, event-ID uniqueness, record hash and previous-hash continuity before replay.
- `head.json`: verified checkpoint/anti-rollback anchor. It is not a second state database. For an interrupted one-event commit, the recovery code requires it to anchor the verified journal prefix.
- `state.json`: derived projection. Recovery accepts it only if it equals the projection reconstructed from the verified journal tail or, for a one-event interrupted commit, exactly equals the known prior projection. Otherwise startup fails closed.
- `runtime_id`: identity binding for the canonical event stream.
- `SQLiteStateStore` remains unintegrated; it was not wired into PhoneRuntime and is not treated as a competing authority.

## 3. Recovery protocol implemented

1. Use atomic temporary-file writes, flush, file `fsync`, `os.replace`, and directory `fsync` for state/head/checkpoint and recovery evidence files.
2. Parse and validate the complete journal before considering reconciliation.
3. Validate that `head.json` points to an actual verified journal prefix. Reject missing, malformed, unanchored, or too-old checkpoints.
4. Permit reconciliation only when the journal is either anchored at its head, or exactly one complete verified event ahead of that head. In the latter case, `state.json` must match exactly either the verified prior state or the verified journal-tail state.
5. For a partial invalid JSON tail, require the head and projection to match the complete verified prefix. First preserve the exact bytes as `history.incomplete-tail.<sha256>.bin`, record a hashed recovery receipt, and only then truncate the uncommitted tail and `fsync` the journal.
6. Emit a stable, idempotent `history.state.recovered` journal event after the canonical journal and derived files are consistent.
7. Bootstrap is itself crash-recoverable: a hashed `history.bootstrap.pending` marker precedes runtime identity/baseline creation and genesis. The marker is removed only after genesis, projection and head verify.

No new state database or external dependency was added.

## 4. Fixed acceptance oracle and boundaries

Oracle/test file: `tests/test_state_recovery.py` (18 test methods; loops cover individual injection points).

The matrix covers:

- write, flush, file `fsync`, directory `fsync` and atomic replace failures for state/head writes;
- fault injection on each `fsync` boundary during ordinary event append and initial bootstrap;
- partial journal frame write, journal flush with complete frame, and incomplete genesis frame;
- abrupt subprocess exit (`os._exit`) after normal-operation `fsync` boundaries, state/head rename, journal/state/head partial write or flush, and each bootstrap `fsync` boundary;
- repeated restart/replay after recovery and event-ID uniqueness/exactly-once assertions;
- recovery retry if repairing state or head fails once;
- refusal to repair when the checkpoint is missing/unanchored;
- a complete valid JSON record missing only the terminal newline is kept untouched and rejected as ambiguous, because it may represent a committed event. It is not silently dropped.

### Oracle outcomes

- Recoverable completed event: event appears exactly once, target projection agrees, `verify()` succeeds, and a second restart still has one event.
- Incomplete invalid frame: frame bytes are preserved under their SHA-256 name; no business event is materialized; one recovery audit event is recorded; replay verifies after repeated restart.
- Ambiguous complete JSON frame without delimiter: `HistoryError`, with journal/head/projection preserved; no quarantine/truncation is performed.
- Missing/corrupt/unanchored checkpoint or projection not matching either verified one-event state: `HistoryError`; no guessed state repair.

## 5. Executed test evidence

### Fault-injection suite

Command:

```sh
PYTHONDONTWRITEBYTECODE=1 python -W error::ResourceWarning -m unittest tests.test_state_recovery -v
```

Result: **22 tests passed in 7.819 seconds**, exit code 0.
Log: `logs/fault-injection.log`.

- SHA-256: `df515c1b9be5e6501223c9626e45f84fe53214d40cb99a71fbc06a7840c900e6`
- Exit-code file: `logs/fault-injection.exit_code.txt` contains `0`.

### Full regression suite

Command:

```sh
PYTHONDONTWRITEBYTECODE=1 python -W error::ResourceWarning -m unittest discover -s tests -v
```

Result: **281 tests passed in 41.119 seconds**, exit code 0.
Log: `logs/full-regression.log`.

- SHA-256: `de50366c49a8e4b193ee833331538a0ae3ef0747f1aaee185b574f42a16c63a9`
- Exit-code file: `logs/full-regression.exit_code.txt` contains `0`.

## 6. Machine-readable pre/post-state observations

A standalone standard-library harness records the pre-fault state, exact child-process exit code, on-disk state immediately after the crash, post-recovery state, event inventory, journal/head/projection digests, quarantine receipts and the assertion result for each abrupt-crash scenario.

Command:

```sh
PYTHONDONTWRITEBYTECODE=1 python tests/run_state_recovery_observations.py
```

Observed result: **27/27 cases PASS** — 13 ordinary-operation crashes and 14 bootstrap fsync crashes. All observed exit codes matched the injected boundary; every recovered state verified; complete events existed exactly once; the incomplete journal write did not become a business event and its raw bytes were quarantined. The JSON includes `before_state`, `after_crash_state`, `after_recovery_state`, `process_exit_code`, `expected_exit_code`, and `oracle_pass` for every case.

- Observation artifact: `logs/recovery-observations.json`
- SHA-256: `d8b6862d339b1c31adca29f110290772181ba94c0d567a1747769d2aa907a3b9`
- Harness source: `tests/run_state_recovery_observations.py`
- Harness SHA-256: `2151221e28709a37371cc256c13ee9a0c27dc9ee05e658c3b402917cf8d2501f`
- stderr artifact is empty; SHA-256 of empty bytes: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

## 7. Source and test digests

- `hg/history.py`: `e68bafc9bfc2579e763a29be6b35e4573e0f1850282ebb7a7558157e38ed856b`
- `tests/test_integrity_v2.py`: `bb2d2c1a8cf2a4ae28d65ac927bd83a029772ccd6fb4c8cfb5dc063b02d0aa93`
- `tests/test_state_recovery.py`: `b480086dfd51146c0ab53b3c2e2442708bad776b95bbdce2b4e5ebe5e5155cf4`
- `tests/run_state_recovery_observations.py`: `2151221e28709a37371cc256c13ee9a0c27dc9ee05e658c3b402917cf8d2501f`

## 8. Remaining limits and refusal conditions

- A complete JSON frame missing only its final newline remains ambiguous and is not automatically discarded or accepted. Operator/independent evidence is required.
- Missing/corrupt/unanchored `head.json`, a projection that matches neither of the two verified states, journal tampering/sequence gaps/hash-chain failure, or a checkpoint lag greater than one complete event remain fail-closed.
- These are injected process-crash and filesystem-call failure tests on disposable temporary directories. They are not physical power-cut tests and do not prove the behavior of every Android/OEM/filesystem/flash device under real power loss.
- Production device restart, low-storage, filesystem corruption and restore drill remain separate P1 evidence items.
- P0-A closure does not close MRAF as a whole: semantic recall quality (M2), active freshness/consolidation (M4), broad contradiction verification and production restore/independent review remain open.

## 9. Repository / release governance

- The application source-of-truth remains the event journal; no second canonical store was introduced.
- The active PhoneRuntime was not switched to `SQLiteStateStore`; any later migration requires explicit migration, rollback and ownership evidence.
- PR #29 must stay OPEN · DRAFT. No merge or deployment is authorized or performed by this closure.
- Final commit/head, clean/dirty worktree and PR state are verified with Git/CLI commands at finalization; no merge or deployment is performed.

**Conclusion: P0-A is accepted only for the tested, explicitly bounded recovery windows. The release is not certified production-ready, and ambiguous/corrupt states continue to fail closed.**
