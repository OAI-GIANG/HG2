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

An isolated `hg.maep_host_binding.MaepHostBinding` seam is now available for a static phase/action allowlist and handler registry. It binds through `CanonicalWorkflowAdapter` to the same canonical `SQLiteStateStore` and sealed principal, checks the principal scope before forwarding to the host authorizer, validates callback response shapes, and delegates evidence verification. This is a binding seam only: no production handler registry, host-bound action authorizer, or authenticated production evidence verifier is wired to the live HTTP runtime. The default runtime therefore remains unable to execute MAEP tasks and must return BLOCKED; this prevents bypassing `hg.authority` or claiming trust that has not been established.

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

The current active HTTP runtime still uses the legacy PhoneRuntime state store; the existing workflow adapter explicitly does not perform that runtime cutover. This branch does not add an unauthenticated API route or silently migrate live state.

## Legacy state migration contract

- `HG_STATE_MIGRATION_ENVELOPE_V1` preserves the exact `history.jsonl` bytes and records SHA-256 metadata for related legacy state files. V1 alone is not a complete byte-preserving archive of all durable state files.
- `HG_STATE_MIGRATION_ENVELOPE_V2` packages exact bytes, byte lengths, and SHA-256 digests for `history.jsonl`, `head.json`, `state.json`, and `runtime_id`. It rejects missing/extra files, malformed JSON, duplicate object keys, non-finite JSON constants, runtime identity mismatch, tampered bytes, and attempts to enable production import.
- Both versions explicitly mark legacy authority as `LEGACY_AUTHORITY_UNATTESTED`, keep `production_import_authorized=false`, and state that no migration has been performed. A valid envelope proves byte integrity relative to its own contents; it does not authenticate the source, prove semantic truth, reconstruct the SQLite event chain, or prove projection parity.
- Fixture verification does not replace a consistent live backup, restore rehearsal, cross-backend fault injection, shadow parity, or an authorized cutover/rollback plan.

## Verification and remaining blockers

- Unit tests exercise all 14 stages with test-only authorization/evidence adapters, checkpoint reload, denied authorization, missing entry/exit evidence, interrupted execution, stale checkpoint conflict, reconciliation, and closure rejection.
- Android/Termux, Python 3.14.6: full suite PASS, 395 tests in 44.734s, exit code 0. Log: ~/.local/state/hg2-maep-integrated-20261021/full-suite.log; SHA-256: 2692ad293c200c4d8a2c63dc0c625661edfbc38ddb3c97678756b655ea30fab4. Exit-code file SHA-256: 9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa. Fifteen MAEP-related test entries were present in the suite log; test-only adapter success does not prove production runtime readiness.
- Current runtime observations showed hg2-model and hg2-runtime running but hg-backend and hg-runtime down. No MAEP API endpoint or production handler binding has been verified.
- hg.task_compiler remains declaration-only (executable: false), and hg.durable_transactions remains a transaction ledger, not a task-step executor. The production integration must connect actual host capabilities and the durable transaction ledger without treating their test callbacks as trust roots.
- No production claim of CLOSED_VERIFIED is justified until the real handler/authority/evidence adapters, runtime path, recovery, and end-to-end acceptance checks are implemented and verified.

## Change boundary

The MAEP orchestration core and SQLite adapter were originally developed on branch `stt/hg2-maep-integrated-20261021` in `~/.cache/hg2-maep-integrated-20261021/worktree`. This continuation added migration-envelope V2, regression evidence, and the static host-binding seam on the isolated branch `stt/hg2-master-cleanup-20261021` in `~/.cache/hg2-master-cleanup-20261021/worktree`. The original checkout and live production state were not modified. Neither branch is authorized for merge or deployment until host adapters, migration/recovery, and runtime acceptance are verified.

## External references

- SQLite transaction atomicity and crash guarantees: https://www.sqlite.org/transactional.html
- Python sqlite3 transaction control: https://docs.python.org/3.13/library/sqlite3.html
- Git worktree isolation semantics: https://git-scm.com/docs/git-worktree

These references inform the durability and isolation approach; they do not substitute for device-specific runtime evidence or authenticated host adapters.
