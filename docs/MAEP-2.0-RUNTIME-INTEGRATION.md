# HG2-MAEP-2.0 — Runtime Integration Record

**Status:** IMPLEMENTED_BUT_UNVERIFIED for the orchestration core; BLOCKED for end-to-end production execution.

## What is implemented

- hg.maep.MaepOrchestrator defines the ordered stages S0–S13.
- MTC task intake requires an objective, scope, input, output, measurable acceptance criteria, evidence requirements, risks, stop condition, next action, and closure conditions.
- Checkpoints are written as maep.task_checkpoint events to the existing StateStore hash-chained history. They include CURRENT_STATE, CHECKPOINT, task status, stage outcomes, and a monotonically increasing revision.
- Each stage requires an explicit handler, an authorization decision, a read-only prepare() entry gate, a stage run() callback, verifiable exit-gate evidence, and stage evidence.
- Missing handlers, authorization, or evidence verification fail closed.
- An interrupted stage saved as RUNNING is treated as in doubt and is not blindly re-executed.
- reconcile_interrupted() permits a retry only when a verifier supplies evidence that the side effect was NOT_PERFORMED. Reconciliation is bounded to three attempts per phase.
- CLOSED_VERIFIED requires every prior phase to be complete or explicitly not applicable with evidence, every required acceptance criterion to be PASS with verified evidence, and every closure condition to have a passing evidence-backed check.
- Checkpoint revision conflicts and malformed checkpoints fail closed.
- PhoneRuntime.maep_orchestrator() binds the engine to the phone runtime's existing StateStore, avoiding a second canonical history store.

## Host adapter contract

A handler entry for each enabled phase must have:

- action: a stable action identifier for the host's authorization policy.
- prepare(state, context): read-only entry checks; returns {"passed": true, "evidence_ids": [...]} only when the entry gate is met.
- run(state, context): executes only the action authorized for this phase and returns a status, exit criteria with evidence, and stage evidence.
- The supplied context["idempotency_key"] must be passed to the real side-effect adapter/transaction ledger. The orchestrator does not itself guarantee that an arbitrary callback is idempotent.
- authorizer(action, context) and evidence_verifier(evidence_ids, context) must return (bool, decision_reference) from real host-bound policy and evidence verification. Test callbacks are not production trust roots.

No handler registry, host-bound action authorizer, or authenticated production evidence verifier is wired by this change. Therefore the default runtime cannot execute tasks and will return BLOCKED; this is intentional and prevents the new controller from bypassing hg.authority or claiming trust it cannot prove.

## Usage from the phone runtime

~~~python
from hg.phone_runtime import PhoneRuntime

runtime = PhoneRuntime()
orchestrator = runtime.maep_orchestrator(
    handlers=trusted_host_handlers,
    authorizer=host_action_authorizer,
    evidence_verifier=host_evidence_verifier,
)
state = orchestrator.create_task(mtc_record)
state = orchestrator.run_until_blocked(state["task_id"])
~~~

trusted_host_handlers, host_action_authorizer, and host_evidence_verifier above are intentionally placeholders: they must be implemented and reviewed against the actual phone runtime's capability boundary before production use. Do not replace them with unconditional True callbacks.

## Verification and remaining blockers

- Unit tests exercise all 14 stages with test-only authorization/evidence adapters, checkpoint reload, denied authorization, missing entry/exit evidence, interrupted execution, stale checkpoint conflict, reconciliation, and closure rejection.
- Android/Termux, Python 3.14.6: full suite PASS, 341 tests, exit code 0. Log: ~/.local/state/hg2-maep-20261021/final-suite.log; SHA-256: 48e614a9dd2a6ef37c3e637467027f57f6a8713cc63c3ab26702a98758558083. Exit-code file: ~/.local/state/hg2-maep-20261021/final-suite.exit_code.
- Current runtime observations showed hg2-model and hg2-runtime running but hg-backend and hg-runtime down. No MAEP API endpoint or production handler binding has been verified.
- hg.task_compiler remains declaration-only (executable: false), and hg.durable_transactions remains a transaction ledger, not a task-step executor. The production integration must connect actual host capabilities and the durable transaction ledger without treating their test callbacks as trust roots.
- No production claim of CLOSED_VERIFIED is justified until the real handler/authority/evidence adapters, runtime path, recovery, and end-to-end acceptance checks are implemented and verified.

## Change boundary

Implementation work is isolated to branch stt/hg2-maep-2.0-20261021 in ~/.cache/hg2-maep-20261021/worktree. The original checkout's untracked docs/review/ reports and Python cache files were preserved. This branch must not be merged or deployed until host adapters and runtime acceptance are verified.

## External references

- SQLite transaction atomicity and crash guarantees: https://www.sqlite.org/transactional.html
- Python sqlite3 transaction control: https://docs.python.org/3.13/library/sqlite3.html
- Git worktree isolation semantics: https://git-scm.com/docs/git-worktree

These references inform the durability and isolation approach; they do not substitute for device-specific runtime evidence or authenticated host adapters.
