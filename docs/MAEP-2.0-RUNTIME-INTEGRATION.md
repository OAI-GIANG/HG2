# HG2-MAEP-2.0 — Runtime Integration Record

**Status:** IMPLEMENTED_BUT_UNVERIFIED for the orchestration core; BLOCKED for end-to-end production execution.

## What is implemented

- hg.maep.MaepOrchestrator defines the ordered stages S0–S13.
- MTC task intake requires an objective, scope, input, output, measurable acceptance criteria, evidence requirements, risks, stop condition, next action, and closure conditions.
- Checkpoints are written as maep.task_checkpoint events to the existing canonical SQLiteStateStore event log using a sealed-principal audit.append mutation permit. They include CURRENT_STATE, CHECKPOINT, task status, stage outcomes, and a monotonically increasing revision.
- Each stage requires an explicit handler, an authorization decision, a read-only prepare() entry gate, a stage run() callback, verifiable exit-gate evidence, and stage evidence.
- Missing handlers, authorization, or evidence verification fail closed.
- An interrupted stage saved as RUNNING is treated as in doubt and is not blindly re-executed.
- reconcile_interrupted() permits a retry only when a verifier supplies evidence that the side effect was NOT_PERFORMED. Reconciliation is bounded to three attempts per phase.
- CLOSED_VERIFIED requires every prior phase to be complete or explicitly not applicable with evidence, every required acceptance criterion to be PASS with verified evidence, and every closure condition to have a passing evidence-backed check.
- Checkpoint revision conflicts and malformed checkpoints fail closed.
- CanonicalWorkflowAdapter.maep_orchestrator() binds the engine to the existing SQLiteStateStore and sealed principal. The adapter rejects the legacy append-only StateStore; MAEP therefore does not create a second canonical state database.

## Host adapter contract

A handler entry for each enabled phase must have:

- action: a stable action identifier for the host's authorization policy.
- prepare(state, context): read-only entry checks; returns {"passed": true, "evidence_ids": [...]} only when the entry gate is met.
- run(state, context): executes only the action authorized for this phase and returns a status, exit criteria with evidence, and stage evidence.
- The supplied context["idempotency_key"] must be passed to the real side-effect adapter/transaction ledger. The orchestrator does not itself guarantee that an arbitrary callback is idempotent.
- authorizer(action, context) and evidence_verifier(evidence_ids, context) must return (bool, decision_reference) from real host-bound policy and evidence verification. Test callbacks are not production trust roots.

No handler registry, host-bound action authorizer, or authenticated production evidence verifier is wired by this change. Therefore the default runtime cannot execute tasks and will return BLOCKED; this is intentional and prevents the new controller from bypassing hg.authority or claiming trust it cannot prove.

## Integration with the canonical workflow store

~~~python
from hg.workflow_store_adapter import CanonicalWorkflowAdapter

adapter = CanonicalWorkflowAdapter(
    sqlite_state_store,
    principal=authenticated_principal,
    actor_id=authenticated_principal.principal_id,
    clock=clock,
)
orchestrator = adapter.maep_orchestrator(
    handlers=trusted_host_handlers,
    authorizer=host_action_authorizer,
    evidence_verifier=host_evidence_verifier,
)
state = orchestrator.create_task(mtc_record)
state = orchestrator.run_until_blocked(state["task_id"])
~~~

The adapter must receive a real sealed principal with the audit.append scope and the canonical SQLiteStateStore. The handlers, host_action_authorizer, and host_evidence_verifier above are intentionally placeholders: they must be bound to the existing BrainOrchestrator/UnifiedHarness and the actual host capability boundary before production use. Do not replace them with unconditional True callbacks.

The current active HTTP runtime still uses the legacy PhoneRuntime state store; the existing workflow adapter explicitly does not perform that runtime cutover. This branch adds optional authenticated routes, but they require an injected orchestrator whose exact SQLiteStateStore object is also runtime.store and whose sealed principal matches the HTTP principal. The server rejects a second MAEP store with MAEP_RUNTIME_STORE_MISMATCH. The production main() does not inject MAEP because PhoneRuntime still uses StateStore; the live release therefore cannot use these routes and will fail closed at the route-scope gate (403) or the missing-runtime-binding gate (503), depending on configured scopes. No live state was migrated or modified.

## Verification and remaining blockers

- Unit tests exercise all 14 stages with test-only authorization/evidence adapters, checkpoint reload, denied authorization, missing entry/exit evidence, interrupted execution, stale checkpoint conflict, reconciliation, and closure rejection.
- Android/Termux, Python 3.14.6: Phase 2 full suite PASS, 481 tests in 47.886s, exit code 0. Log: ~/.local/state/hg2-maep-phase2-20261021/full-suite.log. The log and exit-code SHA-256 values are recorded in the Phase 2 checkpoint; test-only adapter success does not prove production runtime readiness.
- No production MAEP handler registry, host-bound action authorizer, or authenticated evidence verifier is wired. The optional HTTP routes were tested only against a disposable SQLite-backed runtime object; the live release does not inject MAEP.
- hg.task_compiler remains declaration-only (executable: false), and hg.durable_transactions remains a transaction ledger, not a task-step executor. The production integration must connect actual host capabilities and the durable transaction ledger without treating their test callbacks as trust roots.
- HTTP API tests prove authentication, route scopes, task create/read, duplicate rejection, fail-closed missing handlers, store identity mismatch rejection, and 503 when the runtime has no MAEP binding. These use a disposable SQLite store and test-only credentials; they do not establish production capability bindings.
- The live release remains on fcc561ae919b64572c5a9b549d5664b7fbfd4676; /api/health returned 200 with a valid 13-event legacy StateStore chain. hg-backend and hg-runtime are down; hg2-runtime and hg2-model are running. No service was restarted. Read-only hashes for head.json, history.jsonl, runtime_id, state.json, and the runtime lock file matched across two samples one second apart; this is a stability observation, not a quiescent backup or migration snapshot.
- No production claim of CLOSED_VERIFIED is justified until the real handler/authority/evidence adapters, state ownership migration, runtime path, recovery, and end-to-end acceptance checks are implemented and verified.

## Change boundary

Phase 2 work is isolated to branch stt/hg2-maep-phase2-20261021 in ~/.cache/hg2-maep-phase2-20261021/worktree, based on stt/hg2-master-cleanup-20261021 at 08a4be822cd1e562fdd7003fce0c270111ff33a5, then applying MAEP commit 2cfcf251df443df5f65262ff2b143e1f6f55dfa2. The earlier stt/hg2-maep-integrated-20261021 branch remains unchanged. The original checkout and master-cleanup worktree, including their untracked evidence, were preserved. This Phase 2 branch must not be merged or deployed until migration, host adapters, and runtime acceptance are verified.

## External references

- SQLite transaction atomicity and crash guarantees: https://www.sqlite.org/transactional.html
- Python sqlite3 transaction control: https://docs.python.org/3.13/library/sqlite3.html
- Git worktree isolation semantics: https://git-scm.com/docs/git-worktree

These references inform the durability and isolation approach; they do not substitute for device-specific runtime evidence or authenticated host adapters.

## Phase 2 authenticated API seam

The candidate exposes the following opt-in routes only when an orchestrator is explicitly injected:

- GET /api/maep/tasks/{task_id}: requires an authenticated read token and workflow.task.read.
- POST /api/maep/tasks: requires an authenticated write token plus workflow.task.create and audit.append.
- POST /api/maep/tasks/{task_id}/run: requires an authenticated write token plus workflow.task.transition and audit.append. The MAEP host authorizer remains a second mandatory gate for every phase action.

The server constructor verifies that the orchestrator's exact SQLiteStateStore object is the runtime's exact store object and that the sealed principal ID matches the configured HTTP principal. A second store or mismatched principal is rejected before serving. Missing runtime binding returns 503 after authentication and scope checks. The live main() does not inject MAEP because the current PhoneRuntime owns a legacy StateStore; this is intentional fail-closed behavior, not a production-ready endpoint.

## State migration and rollback decision

- M0 — Inventory: process 14210 is running release source fcc561ae919b64572c5a9b549d5664b7fbfd4676, entrypoint hg/server.py, Python 3.14.6. The live state directory is ~/hg2-state. The runtime health response verified a 13-event hash chain. Metadata-only hashes for head.json, history.jsonl, runtime_id, state.json, and the lock file matched across two samples one second apart.
- M1 — Semantic parity: NOT PASSED. StateStore event envelope/recovery and SQLiteStateStore event envelope, authorization permits, projections, and import semantics are different. No complete lossless mapping has been implemented or proven.
- M2 — Backup/rehearsal: LIVE BACKUP NOT RUN. Never copy the active journal and metadata files as if they were an atomic snapshot. Existing tests only verify synthetic backup/restore and isolated SQLite transaction recovery; they do not prove cross-backend migration.
- M3 — Fault injection: NOT PASSED for cross-backend migration. Required cases include process interruption at each import/checkpoint boundary, duplicate IDs, malformed or unsupported events, memory projection parity, sync cursor/outbox parity, and restart.
- M4 — Shadow comparison: NOT RUN. A disposable translated target must be read-only and non-dispatching until semantic digests and projections match.
- M5 — Cutover/rollback: NOT AUTHORIZED / NOT RUN. Do not stop or restart the live service, do not dual-write, and do not point the release at a second database. A future cutover requires a quiescent verified backup, a rehearsed restore, one atomic backend selection, and rollback to the immutable pre-cutover source snapshot.
- M6 — Retirement: NOT APPLICABLE. No old store or component has been deleted.

SQLite's official documentation states that transactions are atomic and durable under defined configurations, and specifically notes WAL files are part of persistent state and must be kept with the database during copy/move. This supports retaining transactional writes and complete SQLite backup handling; it does not establish semantic parity between the HG2 stores.
