# HG2 Central Brain — Component Disposition Matrix R2

Target: OAI-GIANG/HG2 only.
Method: source listing, static source review, local unit/integration evidence and branch/status inspection on Termux. Runtime/prod claims are limited to the observed boundary.

| Component / evidence | Observed role | Current status | Decision | Reason and action |
|---|---|---|---|---|
| hg/brain_orchestrator.py | Static capability owner map, stable route order, synchronous execution, typed aggregate | IMPLEMENTED; TESTED by local tests; in-memory only | IMPROVE | Keep pure coordinator; add durable plan/step lifecycle only after contracts and single-state-owner design are accepted |
| hg/contracts.py | Versioned Brain request/result contracts, canonical digest and evidence callback validation | IMPLEMENTED; TESTED | KEEP | Extend only via new schema version; distinguish runtime manifest SHA from Git commit SHA |
| hg/server.py / POST /api/ask | Authenticated local HTTP endpoint; memory + model adapter; Brain aggregate | IMPLEMENTED; local fake-gateway E2E TESTED | IMPROVE | Add pre-call audit invariant; later bind task idempotency and persisted workflow |
| hg/model_gateway.py | OpenAI-compatible synchronous provider request; redirect denial; local response manifest | IMPLEMENTED; unit-tested | IMPROVE | Keep as narrow adapter; caller must append redacted start event before ask; adapter timeout remains required |
| hg/phone_runtime.py and runtime StateStore | Phone-owned state/history path | IMPLEMENTED in source; no deployed service proof here | KEEP | Canonical local state authority; no second authoritative brain database |
| hg/history.py | Append-only hash-linked local event records and projection integrity checks | IMPLEMENTED; test suite covers corruption/recovery cases | KEEP | Use as canonical event/state authority; fail closed on divergence |
| hg/workflow.py / WorkflowService | Persisted task state transitions with authority, idempotency, deadline and bounded retry contract | IMPLEMENTED; unit-tested; not wired to Brain plans | IMPROVE / INVESTIGATE | Candidate for task lifecycle; mapping of Brain plan/step states to existing lifecycle required |
| hg/durable_transactions.py | Separate SQLite transaction ledger, digest-bound plan/steps, evidence-gated commit and IN_DOUBT recovery | IMPLEMENTED; unit-tested; not bound to current Brain API state | INVESTIGATE | Do not instantiate beside StateStore as a second authority. Decide whether to adapt, integrate transactionally or leave unused for Brain |
| hg/task_contract.py | Validated immutable task declaration; does not itself authorize or execute | IMPLEMENTED; tested | KEEP | Reuse declaration semantics where compatible; do not mistake declaration for authorization |
| manifest.json | Source/module inventory and build identity input | IMPLEMENTED; used by source/provenance test | KEEP / IMPROVE | Ensure new contracts/tests are included as designed; build identity labels manifest digest distinctly from commit SHA |
| tests/test_brain_orchestrator.py | Core allowlist, status, budget, evidence and error tests | IMPLEMENTED; baseline suite includes it | KEEP / IMPROVE | Add malformed aggregate/property tests and future durable restart tests as relevant |
| tests/test_server.py | Local HTTP integration with PhoneRuntime and fake gateway | IMPLEMENTED; baseline tested | IMPROVE | Add start-audit order and storage-failure negative test |
| test doubles / fake gateway | Deterministic local E2E evidence | TESTED only | KEEP | Good for repeatable integration; cannot substitute for live provider or production runtime proof |
| Static BRANCH_CAPABILITIES | Five logical owners and allowed capability IDs | IMPLEMENTED | KEEP as bootstrap; REPLACE only via versioned migration | A static allowlist is not a trusted health-aware registry; registry contract needed before operational expansion |
| Three unbound domains: planning_coordination, tools_execution, security_verification | Logical entries only; no API adapters bound | PROPOSED/UNBOUND | INVESTIGATE / IMPROVE | Do not report OPERATIONAL; add bounded adapters only after contracts, permission gate and independent test |
| Memory synthesis route output | Memory receipt is verified against request-local manifest; model output reports RESPONSE_ONLY | TESTED local route | KEEP | Honest PARTIAL status is safer than SUCCESS; semantic correctness remains unverified |
| Sync/outbox dispatcher | Replication/publication support in existing architecture | IMPLEMENTED elsewhere in HG2 source | KEEP separate from Brain router | Outbox is not automatically a job scheduler; use only after explicit interface contract |
| docs/architecture/HG2-INDEPENDENT-ARCHITECTURE-R2.md | Earlier candidate architecture document | IMPLEMENTED as documentation | REVISE / LINK | R2 master plan supersedes incomplete scope; retain candidate history instead of overwriting silently |
| Other local worktrees and untracked review/cache files | Separate branches or untracked artifacts were present outside active candidate checkout | OUT OF SCOPE / UNMODIFIED | KEEP untouched | No cleanup/reset across worktrees; never remove untracked evidence or user files by assumption |

## Delete/deprecate decisions

No DELETE, branch pruning, schema deletion or service removal is authorized by this matrix. Incomplete evidence defaults to INVESTIGATE. Before any future destructive disposition:
- map static and dynamic imports, entry points, manifest registration and tests;
- identify persisted data and compatibility;
- provide a migration plus canary and rollback;
- verify exact object identity and authority;
- run negative tests proving the removed capability cannot still be reached.
