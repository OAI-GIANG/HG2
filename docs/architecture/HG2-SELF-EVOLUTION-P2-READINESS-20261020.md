# HG2 — Self-Evolution P2 Readiness Checkpoint

- Date: 2026-10-20 (Asia/Ho_Chi_Minh)
- Repository: `OAI-GIANG/HG2`
- Work branch: `stt/hg2-self-evolution-p2-readiness-20261020`
- Parent commit: `25992701fd0e8ce8d4349dc0fdd298311420d309`
- Status: **TESTED in isolated worktree; NOT CLOSED_VERIFIED; production cutover deliberately not attempted.**

## MTC-1.0

### OBJECTIVE
Reduce uncertainty in the two grouped P2 blockers: evidence trust/semantics and live runtime state ownership/recovery, while checking whether a free offline text model can run on the target ARM64 phone.

### SCOPE
- Read-only inspection of the active Termux service composition and its source checkout.
- Add an isolated crash-boundary regression using a temporary SQLite database.
- Execute the complete repository regression suite.
- Build and exercise a local llama.cpp runtime and model entirely under `~/.cache/hg2-llm-local`.
- Do not alter live runtime source, live state, service configuration, `hg-genesis`, or production service processes.

## Evidence obtained

### 1. Runtime crash-boundary proof

Added `tests/test_workflow_crash_recovery.py`. The test launches a child Python process, starts a SQLite write transaction, writes partial event and task-projection rows, then calls `os._exit(17)` before commit. Reopening the temporary store verifies:

- the SQLite event chain remains valid;
- only the genesis event is present;
- the partial task projection is absent;
- `PRAGMA integrity_check` returns `ok`.

Focused result: **1 passed**.

This proves rollback of an uncommitted SQLite transaction in an isolated temporary database. It does **not** prove a cutover of the active PhoneRuntime, filesystem-level power-loss behavior, outbox remote reconciliation, or Android reboot/background reliability.

### 2. Repository regression

Command: `python -W error::ResourceWarning -m unittest discover -s tests`

Result: **380 tests passed, 0 failures, 0 errors**, 43.863 seconds. Log: `evidence/HG2-SELF-EVOLUTION-P2-20261020/logs/full-regression.log`.

### 3. Free local text-generation candidate

Built `llama.cpp` from source revision `3bb63cbcbfb62056c84fe9e521b0f3d756d29c32` using Termux Clang 21.1.8 for Android `aarch64`, with two build jobs and OpenMP disabled. The CLI and server binaries were built under `~/.cache/hg2-llm-local`; no package was installed into the system.

Model tested:
- Source: `Qwen/Qwen2.5-1.5B-Instruct-GGUF`
- Pinned source revision: `a615a81362316d7b9f5a7a9c4313adfdf9b54588`
- Declared license: Apache-2.0
- Quantization: Q4_K_M
- Size: 1,117,320,736 bytes
- SHA-256: `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e`

A loopback-only test server was started at `127.0.0.1:18080` with a test-only API key, and the existing `hg.model_gateway.ModelGateway` successfully called it. Example answer latency was about 4.8 seconds total; the server reported 22.96 generated tokens/second for that request. The gateway returned `MODEL_CALL_COMPLETED` and a response digest. The test server was then terminated; verification showed PID 8760 absent and port 18080 closed.

Quality limitation: three official Qwen candidates were exercised on the same Vietnamese SQLite-recovery prompt. Qwen2.5-1.5B produced incorrect recovery guidance; Qwen3-1.7B suggested unsupported commands; Qwen3-4B Q4_K_M (source revision `bc640142c66e1fdd12af0bd68f40445458f3869b`, declared Apache-2.0, size 2,497,280,256 bytes, SHA-256 `7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`) also suggested `.load` as a database-recovery step, which is incorrect. The 4B run generated about 7.2 tokens/second and the answer did not meet the technical correctness gate. None of these candidates is approved as an autonomous engineering authority or trusted evidence verifier. The local runtime and gateway are technically usable, but model quality is not accepted for autonomous engineering decisions.

### 4. Live runtime checkout — critical blocker

The active service entrypoint imports `PhoneRuntime` from `/data/data/com.termux/files/home/hg2-phone`. That checkout reports remote `https://github.com/OAI-GIANG/HG2.git`, HEAD `4d97c34d8bb7c1091265330aef63dd78d0e72c49`, and has a dirty working tree including modified runtime/state/auth files, deleted `hg/edge.py`, and untracked modules/logs. The active `PhoneRuntime` constructs the legacy file-backed `StateStore`.

These local changes were not created by this task and were not modified. To preserve recoverability, a private checkpoint of the complete Git working-tree delta, staged delta, HEAD, remotes, status and all non-ignored untracked files was created at `~/.cache/hg2-runtime-checkpoints/20261020-P2-live-checkout`; its SHA-256 manifest and untracked archive were verified. A separate private snapshot of `~/hg2-state` was created at `~/.cache/hg2-runtime-checkpoints/20261020-P2-live-state`; the archive checksum and tar listing were verified. A disposable extraction of the state snapshot was opened with the candidate `PhoneRuntime`; `health.ok` and `integrity.ok` both passed. These checks prove the candidate can read a copy of the current state, not that a live StateStore cutover, crash/restart cycle, outbox reconciliation, or rollback works. The local dirty changes remain unreconciled, and no live state-owner cutover has been attempted. Live services were not restarted or changed.

## Git / release integration

- P2 evidence/test PR #33: **MERGED** into candidate branch `stt/hg2-brain-orchestrator-r1-20261019`.
- Candidate branch HEAD: `90fb02c735ddd43d8e7f38bafc70c50da40ad283`.
- Existing release PR #29: **OPEN**, CI `ci/circleci: verify` **SUCCESS** (build [300](https://circleci.com/gh/OAI-GIANG/HG2/300)).
- PR #29 base remains `hg-genesis` at `1dca305b4d6e9442e259442486efb5127cc0cb09`; it was not merged. No production deploy or service restart occurred.

## Two grouped blockers — disposition

| Blocker | Current result | Why it remains open |
|---|---|---|
| Trusted evidence semantics and authority | **PARTIALLY REDUCED / NOT CLOSED** | The filesystem verifier still proves bytes/digests, not semantic truth. Its trust-root digest is caller-supplied; a production-provisioned root and trusted semantic oracle/runner have not been established. Supersession decisions remain recorded but not activated. |
| Runtime operation and recovery | **PARTIALLY REDUCED / NOT CLOSED** | Isolated SQLite crash rollback now has a regression test. Verified private snapshots now preserve both the dirty runtime checkout and current state files, and the candidate `PhoneRuntime` passes health/integrity checks on a disposable copy. The live checkout remains unreconciled and uses the legacy `StateStore`; actual rollback, production cutover, outbox reconciliation and long-running offline inference are still unproven. All three local model candidates failed the engineering-quality gate and are not accepted for autonomous decisions. |

## Stop conditions and next gates

1. Reconcile the dirty `hg2-phone` checkout from the verified private snapshot before any cutover. Do not overwrite its changes.
2. Provision an authenticated trust root outside candidate-controlled artifacts, and add a semantic test-evidence runner with pinned suite/environment identities. Keep `semantic_truth_verified=false` for byte-only receipts.
3. Test snapshot, rollback, restart, outbox and `IN_DOUBT` reconciliation against disposable data, then design the PhoneRuntime composition change separately.
4. Complete local model quality/latency/RAM/battery evaluation before binding any model to an autonomous planner. Generated content remains an untrusted proposal.
5. Do not merge `PR #29` into `hg-genesis` or deploy production from this checkpoint.

**Conclusion:** The repository regression remains green, an isolated crash-recovery test has been added, and private snapshots of runtime source/state are verified. The local model path is technically reachable, but all three tested model candidates failed the engineering-quality gate. The two grouped blockers are not yet removed; claiming `CLOSED_VERIFIED` would contradict the evidence.
