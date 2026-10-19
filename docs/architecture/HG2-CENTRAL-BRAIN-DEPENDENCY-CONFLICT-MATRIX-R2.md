# HG2 Central Brain — Dependency, Duplication & Conflict Matrix R2

Scope: source and orchestration contracts in OAI-GIANG/HG2 only. “Observed” means in the inspected candidate source, not an assertion about every deployed environment.

## 1. Dependency and source-of-truth matrix

| Item A | Item B | Observed relationship / possible conflict | Risk | Decision |
|---|---|---|---|---|
| PhoneRuntime.store / StateStore | MemoryStore | PhoneRuntime constructs MemoryStore(self.store); same store object | LOW if invariant remains | KEEP; test identity/reuse |
| PhoneRuntime.store / StateStore | DurableOutbox | PhoneRuntime constructs DurableOutbox(self.store) | LOW if invariant remains | KEEP; replication outbox is not task queue |
| StateStore | optional SyncContext | Sync configuration passes store=self.store and checks identity | LOW if invariant remains | KEEP; preserve one state authority |
| StateStore | DurableTransactionStore | Separate module opens its own explicit file-backed SQLite database; PhoneRuntime does not instantiate it | HIGH if both become authoritative | INVESTIGATE before Brain integration |
| StateStore | WorkflowService | WorkflowService persists through an abstract supplied store and uses policy/principal checks; Brain currently calls the in-memory orchestrator directly | HIGH integration gap | IMPROVE through explicit mapping, not parallel state ownership |
| hg/task_contract.py | hg/contracts.py | Both define versioned validation/digest concepts for different domains (task declaration vs Brain request/result) | MEDIUM duplication/contract drift | KEEP distinct semantics; document adapters and shared canonicalization expectations |
| hg/brain_orchestrator.py | hg/server.py | Server builds request and adapter inventory in route; orchestrator contains static capability ownership | MEDIUM authority/config duplication | Consolidate registry contract only after versioned migration |
| BRANCH_CAPABILITIES | API-local inventory | Static master allowlist says what a domain may own; route inventory says what adapters are currently supplied | HIGH if declaration is mistaken for operational readiness | KEEP allowlist as maximum; runtime availability must be bound/verified |
| evidence_verifier callback | request-local memory manifest dictionary | Verifier proves the current route's digest is present and canonical in an in-memory map; it is not an independent semantic/external-provenance verifier | HIGH evidence overclaim risk | Separate integrity, provenance, semantic and runtime verifiers |
| source_revision in Brain request | build source_manifest_sha256 | Route sends runtime source-manifest digest; orchestrator enforces only SHA-shaped 40/64 hex | MEDIUM semantic ambiguity | Use typed names in a new request schema; never conflate manifest digest with Git commit SHA |
| correlation_id | idempotency key | Correlation groups related events, but route currently generates new request/correlation IDs per request | HIGH duplicate request/provider cost risk | Add client-stable idempotency key bound to normalized input digest |
| model.call.started | model.call.completed | Before remediation, only completion was emitted; after patch, start append precedes gateway call and completion follows response | HIGH contract violation repaired in candidate | TEST start order plus append failure; do not infer production operation |
| manifest.json modules | actual source/import graph | Manifest lists ten modules but omits server, contracts, memory, gateway, workflow and several source-present modules | UNKNOWN until manifest purpose clarified | INVESTIGATE semantics; add test only after defining expected coverage |
| hg/provenance.py / runtime manifest | Git identity/signature | Source-manifest SHA identifies observed bytes but does not by itself establish signed commit or remote process identity | HIGH if conflated | KEEP identities separated in evidence |
| Model response | verification decision | Generated text currently returns RESPONSE_ONLY and aggregate PARTIAL | LOW while preserved; HIGH if silently promoted to SUCCESS | KEEP PARTIAL semantics; independent quality verification OPEN |
| logical domain names “branch” | Git branch names | Same word used for distinct concepts | MEDIUM maintenance/operational confusion | Use “logical domain” in docs; change wire schema only in a versioned migration |

## 2. Duplicate or overlapping functionality

### Reuse rather than copy
- Canonical event/history: hg/history.py; do not make a separate brain event ledger authoritative.
- Task declaration validation: hg/task_contract.py; reuse where schemas match rather than creating a second task language.
- Task lifecycle and authorisation: hg/workflow.py; map explicitly to brain steps and statuses.
- Transaction uncertainty/evidence gating: hg/durable_transactions.py is a candidate reference implementation, not automatically the runtime store to add.
- Memory/context: hg/memory.py and MemoryStore are existing runtime capability implementations.
- Provider I/O: hg/model_gateway.py is the narrow gateway; do not let planner call the network independently.

### Possible schema/registry duplication
1. BRANCH_CAPABILITIES controls allowed ownership.
2. The HTTP route hard-codes required_capabilities and supplies an inventory.
3. manifest.json carries module names.
4. policy.py/authority.py govern mutation permission.
5. workflow.py and durable_transactions.py have separate lifecycle vocabularies.

These are not necessarily defects; they are separate control planes. A contract must clarify how each one relates and which is authoritative. Do not merge the lists blindly: capability scope, runtime module inventory, permission policy and workflow state are different things.

## 3. Dependency cycles and execution reachability

- No cycle was claimed absent from the whole repository: this pass was not a complete static dependency-graph computation.
- The current Brain coordinator is synchronous and receives injected callables, reducing implicit dynamic dispatch.
- The first /api/ask route calls memory then synthesis in its selected order. The synthesis adapter requires the memory context result, making the dependency sequential in practice; the request contract does not yet encode a formal DAG node dependency.
- Runtime registry health, dynamic module imports and all indirect call paths require further static/dynamic inspection before any component is deleted or declared unreachable.
- No destructive dependency pruning is authorized by this matrix.

## 4. Required resolution order

1. Define manifest semantics: curated core-module list or exhaustive import/source inventory.
2. Define DomainCapability, PlanStep, Task, ExecutionReceipt, and EvidenceRef as versioned contracts, including explicit identity semantics.
3. Choose one canonical task-state transaction boundary that reuses PhoneRuntime.store.
4. Define trusted registry binding and independent verifier ownership.
5. Bind one low-risk, side-effect-free capability end-to-end; test duplicate requests and restart recovery.
6. Only then consider additional adapters, concurrency or deprecation of legacy paths.
