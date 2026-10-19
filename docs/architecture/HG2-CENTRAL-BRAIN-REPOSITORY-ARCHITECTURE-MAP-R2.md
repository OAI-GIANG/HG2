# HG2 Central Brain — Repository Architecture Map R2

- Repository scope: OAI-GIANG/HG2 only.
- Inspected checkout: branch stt/hg2-brain-orchestrator-r1-20261019, pre-change HEAD 67afde1ca027b4012ce0dde190dda00918da3aff.
- Method: source inspection, manifest inspection, local unit/integration test records. No claim about live service or provider is inferred from source alone.

## 1. Runtime topology established by source

Authenticated client
  -> hg/server.py: HGHTTPServer / HGRequestHandler
     -> authentication, bounded JSON body, endpoint and scope checks
     -> GET/POST /api/memory -> hg/memory.py
     -> POST /api/ask -> hg/brain_orchestrator.py
        -> memory_knowledge worker -> MemoryStore(self.store)
        -> research_synthesis worker -> model.call.started event
           -> event must persist first
           -> hg/model_gateway.py -> external provider
        -> typed aggregate (provider response remains RESPONSE_ONLY / overall PARTIAL)
        -> redacted model.call.completed audit
     -> POST /api/durable/sync -> existing durable/outbox sync path
  -> hg/history.py: StateStore, canonical local history/state owner

PhoneRuntime composition observed in hg/phone_runtime.py:
  - self.store = StateStore(state_dir)
  - self.memory = MemoryStore(self.store)
  - self.model_gateway = ModelGateway(...)
  - self.durable = DurableOutbox(self.store)
  - optional SyncContext and authenticated sync gate reuse self.store

The diagram describes inspected source wiring. Tests exercise the local API path using a deterministic fake model gateway; this is not evidence of a deployed runtime.

## 2. File/component map

| Path | Responsibility observed | Current implementation boundary | Status |
|---|---|---|---|
| hg/server.py | Authenticated local HTTP API, request parsing, memory/model routes and API-level Brain composition | POST /api/ask binds memory + synthesis adapters and writes audit events | IMPLEMENTED; local E2E TESTED |
| hg/brain_orchestrator.py | Static capability ownership, deterministic route planning, synchronous adapter dispatch, typed aggregation | Caller supplies required capability IDs and available adapters; no persistent plan/step history | IMPLEMENTED; TESTED |
| hg/contracts.py | Versioned Brain request/result envelopes, canonical JSON/digest, evidence-reference validation | Envelope/schema and injected-verifier contract; not a source of trusted evidence itself | IMPLEMENTED; TESTED |
| hg/phone_runtime.py | Composes local state, memory, model gateway, outbox and optional authenticated synchronization | One StateStore instance is shared through injected composition | IMPLEMENTED in source; exact deployed runtime UNKNOWN |
| hg/history.py | Canonical state/history, append-only hash-linked events, integrity checks | StateStore is the canonical store used by PhoneRuntime | IMPLEMENTED; tests cover integrity/recovery paths |
| hg/memory.py | Scoped memory operations/context building | Receives grants from authenticated API call and uses canonical store | IMPLEMENTED; local tests |
| hg/model_gateway.py | OpenAI-compatible synchronous provider adapter and response manifest | External call is synchronous; caller must write pre-call audit; external outcome/answer correctness are separate claims | IMPLEMENTED; fake-gateway integration tested |
| hg/durable.py | Outbox delivery support | Composed over the canonical StateStore; replication/publication is not a task scheduler | IMPLEMENTED; related tests |
| hg/sync.py, hg/sync_auth.py, hg/sync_bootstrap.py, hg/sync_dispatcher.py | Synchronization context, authenticated batch gate/bootstrap and dispatch | Reuse of canonical state owner is an invariant; no assumption of a Brain job queue | IMPLEMENTED in source; feature-specific tests |
| hg/task_contract.py | Validates task declarations and digest/shape constraints | Contract declaration alone does not authorize or execute work | IMPLEMENTED; TESTED |
| hg/workflow.py | Task lifecycle transitions, policy/principal checks, deadlines, idempotency and bounded attempts | Not yet wired to durable Brain plan/step execution | IMPLEMENTED; TESTED; integration OPEN |
| hg/durable_transactions.py | Separate file-backed SQLite transaction ledger, step/evidence lifecycle, recovery to IN_DOUBT | Constructor accepts an explicit database path; PhoneRuntime does not instantiate it in inspected composition | IMPLEMENTED; TESTED in isolation; Brain integration INVESTIGATE |
| hg/policy.py, hg/authority.py | Service mutation authorization and base authority decisions | Must remain independent from model-generated plans/results | IMPLEMENTED in source; Brain policy binding incomplete |
| hg/provenance.py, hg/provenance_memory.py | Build/runtime/source provenance and memory provenance functions | Provenance digest is not equivalent to semantic verification or proof of a live remote process | IMPLEMENTED in source; claim-specific verification required |
| hg/sqlite_state.py | Alternative SQLite state implementation/support | Not selected by the inspected PhoneRuntime composition | IMPLEMENTED file; active runtime role UNKNOWN |
| manifest.json | Names ten listed modules and declares no external dependencies | List excludes several source-present components such as server, memory, model_gateway, contracts, workflow, task_contract, durable_transactions and sqlite_state; intended completeness is not established by the manifest itself | IMPLEMENTED; scope needs clarification |
| tests/test_brain_orchestrator.py | Unit tests for route, missing capabilities, result validation, aggregation and limits | Synthetic adapters/verifier; not production adapters | TESTED |
| tests/test_server.py | Local HTTP integration with PhoneRuntime/StateStore and fake gateway | New tests prove start-audit ordering and fail-closed behavior when the append raises | TESTED |
| evidence/ | Test logs and hash-bound result records | Every artifact must be checked against its specific claim and tested commit | PRESENT; per-artifact validity varies |

## 3. Capability map

| Logical domain ID | Allowed capabilities in current static map | API binding observed | Readiness |
|---|---|---|---|
| memory_knowledge | memory.search, memory.recall, provenance.inspect | memory.search adapter builds authorized memory context | LIMITED local binding; full domain not OPERATIONAL |
| research_synthesis | research.analyze, synthesis.propose, source.compare | synthesis.propose adapter calls ModelGateway | Response generation only; branch result is RESPONSE_ONLY |
| planning_coordination | task.decompose, dependency.plan | None bound by /api/ask | UNBOUND |
| tools_execution | tool.execute, artifact.build | None bound by /api/ask | UNBOUND |
| security_verification | policy.check, evidence.verify, conflict.review | A request-local evidence callback exists; it is not a complete independent domain adapter | UNBOUND as an operational domain |

“Domain” refers to logical capability ownership. It does not mean a separate Git branch, process, model, or command authority.

## 4. Important boundaries and gaps

1. The orchestrator selects from the required capabilities provided in the request. It does not yet classify arbitrary user intent into a capability graph.
2. The plan/result ledger returned by Brain is in-memory. The inspected API does not persist/replay the whole plan and each step in a durable task workflow.
3. The API route uses two adapters only; three domains are declared but not operationally bound.
4. The model.call.started record is required before the model gateway is invoked. A write failure returns BLOCKED without invoking the gateway.
5. model.call.completed records a completed provider response; the response does not prove semantic truth or external action.
6. DurableTransactionStore and WorkflowService are useful existing primitives, but neither is automatically the correct integration point. First decide one state authority and atomically bind the workflow lifecycle.
7. The public HTTP implementation requires independent deployment review for binding, TLS/edge placement, credentials, access policies and recovery; local loopback tests do not settle deployment safety.
8. The source module inventory in manifest.json may be a curated core list. Confirm its intended invariant before adding every file to it or treating it as a complete dependency registry.

## 5. Canonical state rule

Preserve the PhoneRuntime invariant: exactly one canonical StateStore for local state/history. Memory, outbox and optional sync reuse that store in the inspected composition. Do not simply instantiate DurableTransactionStore alongside it as a second authoritative task ledger. The design decision must either extend/integrate task events within the same transaction boundary or document a rigorously reconciled projection that is not a competing source of truth.

## 6. Evidence boundary

- Source inspection establishes code structure, not live operation.
- Unit tests establish the behavior tested under the recorded runtime.
- Local HTTP fake-gateway tests establish API wiring and selected fail-closed behavior.
- Provider correctness, intent-classification accuracy, five-domain operations, live deployment and restore from the actual phone state remain UNVERIFIED unless separate evidence proves them.
