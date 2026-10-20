# HG2 Central Brain — Migration, Checkpoint & Rollback Plan R2

Status: proposed controlled-change plan. The steps below are not proof that deployment or live-state migration has occurred.

## 1. Scope and non-goals

- Only OAI-GIANG/HG2.
- Current target: candidate branch stt/hg2-brain-orchestrator-r1-20261019.
- No merge to hg-genesis, production deploy, live-state migration, deletion, branch pruning or changing branch-protection rules in this change.
- Keep the current phone-owned StateStore; do not introduce a second authoritative Brain database.
- Preserve all other Termux worktrees and untracked files.

## 2. Checkpoint procedure for every patch

### Before edit
1. Resolve exact worktree root, branch, HEAD, tree hash, remote refs and base commit.
2. Record git status --porcelain=v2 --branch, staged diff and unstaged diff. Abort if unexpected files or state appear.
3. Save the baseline test command, exit code, complete log and SHA-256 outside the repository.
4. Hash the files to be changed; write down the explicit path allowlist.
5. Record risk, root cause, expected behavior, acceptance/negative test and rollback trigger.

### During edit
1. Change only the approved path allowlist.
2. Keep the first increment small enough to revert as a single commit.
3. Do not run git clean, blanket reset, recursive deletion or broad package installation.
4. Do not write prompts, provider responses, credential values or user memory into test logs.
5. Use a separate temporary cache directory if compile/test tools create bytecode.

### After edit
1. Run focused tests, then the entire suite with ResourceWarning promoted to an error.
2. Run Python compile, JSON/schema validation and git diff --check.
3. Verify the exact changed-file set and re-hash each modified artifact.
4. Record command, environment, exit code, duration, result count, log hash and limitations.
5. Compare state and source digests before and after test execution to detect drift.

## 3. Transactional Brain migration path

M0 — Design only: map Brain request/plan/result states to existing WorkflowService/StateStore event types. Define a single owner for task state, a stable idempotency key, step IDs, plan digest, evidence refs and recovery policy.

M1 — Isolated contract: implement validators and state-transition tests using temporary state. Prove duplicate keys, changed payload, stale version, unknown step, dependency cycle and missing verifier fail closed.

M2 — Same-state-owner integration: bind the minimum workflow increment to the canonical PhoneRuntime StateStore transaction/event boundary. No dual writes to StateStore and a new standalone DB. If the boundary cannot be made atomic, stop and redesign before external effects.

M3 — Crash matrix: inject failure before persist, after plan persist/before dispatch, after adapter dispatch/before receipt, during evidence verification, during completion append and after commit-before-HTTP-response. Every uncertain external outcome becomes IN_DOUBT and is reconciled, not blindly replayed.

M4 — Local end-to-end canary: one read-only, side-effect-bounded use case in Termux. Restart the process and prove the same plan and idempotency identity are recovered. Record exact runtime resource use.

M5 — Operational candidate: only after a human reviews E0–E7 evidence and the exact deployed phone/runtime is verified. Keep provider/production actions disabled until the next release gate explicitly allows them.

## 4. Rollback decision table

| Trigger | Immediate response | Rollback / recovery |
|---|---|---|
| Syntax, JSON or focused test failure before commit | Stop; preserve logs | Revert only the current patch hunks or return to the pre-change commit after verifying no unrelated changes |
| Full suite regression | Stop promotion | Revert the single current change commit; rerun old baseline tests; keep failed log as evidence |
| Unexpected modified/untracked files | Do not clean/reset | Inventory hashes and leave unrelated files untouched; investigate source of drift |
| Source/history/projection integrity mismatch | Deny mutation and stop | Preserve all artifacts; recover only from a verified checkpoint with explicit operator approval |
| Pre-call audit cannot persist | Do not call provider | Return BLOCKED; no provider retry until persistence is restored and verified |
| Side effect timed out or receipt missing | Treat outcome as IN_DOUBT | Reconcile external operation by stable operation ID; retry only if proven idempotent |
| Restore/checkpoint hash mismatch | Stop recovery | Do not overwrite canonical state; locate another independently verified copy and repeat integrity verification |
| Remote push or PR update failure | Preserve local commit and evidence | Do not force-push; inspect remote ref and reconcile before retry |

## 5. State rollback vs code rollback

- Code rollback restores a prior Git revision; it does not rewind an already executed provider/tool side effect.
- Data recovery must use the dedicated verified backup/checkpoint contract. Do not infer that a git revert restores runtime state.
- Hash match confirms bytes match the known copy; provenance/authority and completeness require additional checks.
- For non-compensable actions, document containment and reconciliation rather than promising full reversal.
- No restore or migration was executed in this R2 design/test pass.

## 6. Release gate

Promotion is blocked unless all are true:
- baseline and candidate test results are reproducible;
- pre-call audit negative test and regression tests pass;
- durable Brain state/restart test has no second authority;
- authorization and independent verification are bound to each action;
- exact-runtime operational evidence is collected;
- checkpoint/rollback is rehearsed with hashes and no real user data loss;
- open HIGH/P0 risks are addressed or formally accepted by authorized human owner.
