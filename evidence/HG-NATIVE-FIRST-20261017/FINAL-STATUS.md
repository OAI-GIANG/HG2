# HG AGENTIC INTELLIGENCE EVOLUTION — NATIVE-FIRST CONTINUE

**Status:** Expanded deterministic oracle set and synthetic control-policy comparison implemented on candidate. Production technical acceptance remains `BLOCKED`; `NOT_RELEASED`.

## Candidate / preservation

- Repository: `OAI-GIANG/HG2`, PR #21, branch `stt/hg-agentic-intelligence-g1-20261017`.
- Canonical base: `9d83a113ccdf1aeda656e494593fa55b9078c803`; canonical branch unchanged.
- No merge, deploy or release. Historic V2.1 fixtures are unchanged and remain `NOT_RUN`. CP0 remains `BLOCKED_INPUT`; the new rubric makes no source-equivalence claim.

## New measurable checks

- Dataset `HNO-SYNTH-001`, oracle `HNO-ORACLE-1.0.0`: 20/20 expected results matched, including explicit DAG topological-order and cycle-detection cases. The Brier expected value was recalculated and pinned as 0.23 after the first run detected an incorrect expected value.
- Synthetic control-policy comparison: baseline 5/20 (0.25) vs candidate 20/20 (1.0), delta `+0.75`, 15 paired cases improved and zero regressions. The predeclared synthetic gate (delta >= 0.25 and zero regressions) passes. `observed_model_runs=0`; no live model quality improvement is claimed.
- Termux strict unittest suite: 174/174 PASS, `ResourceWarning` treated as error. The raw full log is retained.
- CircleCI config was extended to run the strict suite, historical fixture integrity check, 20-case deterministic oracle and synthetic control-policy benchmark. GitHub reports no status/check run for exact candidate `02c543dc4851d3e45f92a6e520054fb6b3aee41d` after repeated read-only checks; last known passing CircleCI job #141 belongs to the previous HEAD `65a3fd9147ca79a45d66a01c1eca3f75ed34b793`. Hosted CI acceptance for this integration revision is not proven.

## Runtime provenance / trust-root findings (read-only)

- Termux `sv status` reports `hg-backend` (PID 10805) and `hg-runtime` (PID 10809) running. This establishes service-process presence only, not correctness or release readiness.
- A Python process (PID 10804) has working directory `$HOME/hg2-phone`; that checkout is detached at `4d97c34d8bb7c1091265330aef63dd78d0e72c49` and is dirty with modifications, a deleted source file, and untracked files. This is not the native-first candidate and is not a clean provenance anchor.
- The candidate worktree is separate. No restart, restore, cutover, or runtime mutation was performed. Runtime provenance remains `BLOCKED_MISMATCH` until the actually running code/process/build is mapped to an approved immutable source and a controlled recovery plan exists.
- `~/.config/hg/secret.env` was inspected only for metadata (present, 0600, 271 bytes); its content was not read or hashed. File permissions do not establish key validity, signer identity, or a trust root. Production trust remains `BLOCKED`.
- Existing tests confirm SQLite idempotency, concurrent duplicate handling, restart recovery to `IN_DOUBT`, and that test-only verifier callbacks cannot promote untrusted evidence to trusted. These are test-harness outcomes, not a real-phone abrupt-power-loss result. Actual target-device power-loss recovery remains `NOT_RUN`.

## Open acceptance gates

- Live natural-language model E2E: `NOT_ACCEPTED`.
- Production actor/approval/capability/evidence trust roots: `BLOCKED`.
- Oracle quality still needs blinded expert labels, disagreement/reliability analysis and holdout semantic evaluation. Current oracle PASS means only deterministic expected output matched.
- Target-device power-loss test: `NOT_RUN`; production runtime provenance, backup/restore, rollback and side-effect acceptance remain `BLOCKED`.
- Local capture is not externally attested; SHA-256 does not authenticate the host, clock, or runner.

**Disposition:** Continue native-first development. Do not merge, deploy, release or close the mission while mandatory gates remain open.
