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

Quality limitation: both Qwen2.5-1.5B and a second official Qwen3-1.7B Q4_K_M candidate were exercised on the same Vietnamese SQLite-recovery prompt. Qwen2.5 produced incorrect recovery guidance; Qwen3 produced incorrect/unsupported commands (including an unverified `sqlite3 -check` suggestion) and incomplete reasoning. Qwen3 artifact: source `Qwen/Qwen3-1.7B-GGUF`, pinned revision `cd3d34a469f89b12676edce7d272750201959466`, declared Apache-2.0, size 1,107,408,544 bytes, SHA-256 `228fb5627f7510b8b3516cdb6435e4b0d2a2bf330fe5b0ab19284a3570a8bb1f`. The tested small models are only candidates for low-risk drafting/idea generation behind strict evaluation gates; neither is approved as an autonomous engineering authority or trusted evidence verifier.

### 4. Live runtime checkout — critical blocker

The active service entrypoint imports `PhoneRuntime` from `/data/data/com.termux/files/home/hg2-phone`. That checkout reports remote `https://github.com/OAI-GIANG/HG2.git`, HEAD `4d97c34d8bb7c1091265330aef63dd78d0e72c49`, and has a dirty working tree including modified runtime/state/auth files, deleted `hg/edge.py`, and untracked modules/logs. The active `PhoneRuntime` constructs the legacy file-backed `StateStore`.

These local changes were not created by this task and were not modified. A state-owner cutover or replacing the runtime checkout now would risk destroying unpreserved work or changing the running service. Cutover is therefore blocked until the dirty checkout is reconciled and a verified snapshot/rollback plan is proven. Live services were not restarted or changed.

## Two grouped blockers — disposition

| Blocker | Current result | Why it remains open |
|---|---|---|
| Trusted evidence semantics and authority | **PARTIALLY REDUCED / NOT CLOSED** | The filesystem verifier still proves bytes/digests, not semantic truth. Its trust-root digest is caller-supplied; a production-provisioned root and trusted semantic oracle/runner have not been established. Supersession decisions remain recorded but not activated. |
| Runtime operation and recovery | **PARTIALLY REDUCED / NOT CLOSED** | Isolated SQLite crash rollback now has a regression test, and a local model gateway call works. The live runtime checkout is dirty and uses the legacy `StateStore`; no production cutover, snapshot/rollback, outbox reconciliation, or long-running offline inference test was performed. The tested 1.5B model failed one engineering-quality prompt and is not accepted for autonomous decisions. |

## Stop conditions and next gates

1. Preserve and reconcile the dirty `hg2-phone` checkout before any cutover. Do not overwrite its changes.
2. Provision an authenticated trust root outside candidate-controlled artifacts, and add a semantic test-evidence runner with pinned suite/environment identities. Keep `semantic_truth_verified=false` for byte-only receipts.
3. Test snapshot, rollback, restart, outbox and `IN_DOUBT` reconciliation against disposable data, then design the PhoneRuntime composition change separately.
4. Complete local model quality/latency/RAM/battery evaluation before binding any model to an autonomous planner. Generated content remains an untrusted proposal.
5. Do not merge `PR #29` into `hg-genesis` or deploy production from this checkpoint.

**Conclusion:** The repository regression remains green and an isolated crash-recovery test has been added. The free local model path is technically reachable, but the first model tested is not reliable enough for autonomous engineering decisions. The two grouped blockers are not yet removed; claiming `CLOSED_VERIFIED` would contradict the evidence.
