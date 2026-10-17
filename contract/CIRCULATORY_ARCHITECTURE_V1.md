# HG2 Circulatory Architecture V1

- Status: DESIGN BASELINE — implementation not yet certified
- Scope: canonical repository OAI-GIANG/HG2
- Runtime authority: PHONE / Termux, exactly one primary
- Design rule: the biological analogy guides separation of responsibilities; it is not permission to add complexity without a concrete contract and test.

## 1. Architectural objective

Rebuild HG2 as one coherent, offline-first system with explicit ownership, bounded interfaces, durable state transitions, auditable evidence, and recoverable operation. Components must be replaceable independently without creating multiple sources of truth. The system must fail closed when identity, authority, integrity, provenance, or state ownership cannot be established.

## 2. The body-to-system map

| Biological analogy | HG2 subsystem | Responsibility | Hard boundary |
|---|---|---|---|
| Heart | Phone Runtime Kernel | Own lifecycle, command dispatch, transaction boundary, health, and scheduling | The phone is the only canonical runtime/state owner |
| Blood | Canonical Event Envelope | Carry typed facts and state transitions with IDs, sequence, timestamps, schema, correlation/causation, and integrity digest | No mutation bypasses the state/event contract |
| Arteries and veins | Local ports, sync outbox, transport adapters | Move commands/results/events between modules and optional remote endpoints | Transport is not authority; retries must be idempotent |
| Organs | Capability modules | Identity, policy, task planning, memory, tools, provider adapters, evidence, backup, user interaction | Each module has one responsibility and a versioned interface |
| Nervous system | Event dispatcher and workflow scheduler | Route events, coordinate task state machines, cancellation, deadlines, and retries | No hidden background side effects; every transition is observable |
| Immune system | Authorization and security policy | Authenticate actors, authorize actions, enforce least privilege, prevent secret leakage, deny by default | Unlisted actions are denied; policy failure is fail-closed |
| Liver / filters | Ingress validation and normalization | Validate schemas, bounds, duplicate keys, content types, provenance, and payload size before mutation | Invalid input never reaches state mutation |
| Kidneys | Integrity verifier and recovery controller | Verify hash chains, checkpoints, backup manifests, restore candidates, and recovery invariants | Never silently repair, overwrite, or promote unverified state |
| Lungs | External model/provider/network adapters | Supply optional external capability when configured | External providers and Internet are optional; no edge holds provider secrets |
| Bone structure | Contracts, schemas, manifest, module graph | Define stable interfaces, dependency direction, versioning, and ownership | No circular dependencies or undocumented cross-module imports |
| Capillaries | Narrow adapters and module ports | Connect a capability to the kernel through small interfaces | No direct writes to another module's private storage |
| Lymphatic system | Telemetry, audit, diagnostics, evidence collection | Detect anomalies, surface degradation, retain traceable evidence | Diagnostics must not expose secrets or mutate canonical state |
| Skin / interface | CLI, local API, UI, voice adapters | Present controls and results to the user | Presentation layer cannot grant authority or write state directly |
| Homeostasis | Health and degradation policy | Keep bounded resource use, detect unhealthy states, select safe degraded modes | Health is evidence, not an authorization bypass |

## 3. Canonical topology

1. PHONE / HG2 runtime: sole primary. Owns canonical state, append-only history, task state, authorization decisions, local durable database/files, and recovery authority.
2. VPS1 / edge relay: optional network ingress/relay only. No canonical state, no provider/model key, no independent task authority, and no implicit promotion to primary.
3. VPS2 / recovery or worker target: optional, explicitly authorized backup/worker target. Never a second primary. Any restored copy remains UNTRUSTED_CANDIDATE until integrity and lineage checks pass and an explicit promotion protocol is satisfied.
4. External providers: optional adapters. Provider credentials remain in the phone's protected local configuration/secret mechanism and are never included in event payloads, logs, backups intended for untrusted relays, or edge requests.
5. Repository and release source: OAI-GIANG/HG2 only. Other local folders, repositories, branches, or old runtime artifacts cannot be execution dependencies for HG2.

## 4. Required command/data flow

User/Input -> Identity -> Authorization -> Schema/Boundary Validation -> Planner/Workflow -> Capability Port -> Result Validation -> State Transaction -> Append-only Event -> Evidence/Audit -> Response

Remote sync, if configured, is a separate post-commit path:

Committed Event -> Outbox -> Authenticated Transport Adapter -> Remote Relay -> Acknowledgement -> Monotonic Cursor/Anchor

Rules:
- A command must be authenticated and authorized before it can cause a side effect.
- Validation occurs before state mutation.
- A state transition and its event/outbox record must commit atomically, or the system must report a recoverable incomplete transaction.
- Retry uses a stable idempotency key; duplicate delivery must not duplicate a side effect.
- Remote failure cannot erase or roll back already committed local state.
- A remote acknowledgement is not proof of canonical authority or successful backup restoration.
- No second runtime may independently advance canonical history.

## 5. State and event contract

Every durable event must define at least:
- schema_version, event_id, event_type, sequence, recorded_at
- actor_id and authority_context (without credentials)
- correlation_id, optional causation_id, and idempotency_key where applicable
- runtime_id, state_owner_id, payload, previous_digest, and record_digest
- evidence/provenance references for decisions whose correctness depends on external input

The canonical serializer must be deterministic. Digests prove byte/content integrity only; they do not prove who is authorized, whether an assertion is true, or whether a runtime is canonical. Sequence/cursor movement must be monotonic and anchored to verified history. Unknown schema versions fail closed.

## 6. Module boundaries and dependency direction

Target modules (names are logical boundaries; final file layout is decided after contract tests):
- kernel: lifecycle, composition root, health, command boundary
- identity: product/runtime/device identity and provenance labels
- policy: authorization predicates, grants, denials, approval state machine
- contracts: schemas, canonical serializer, typed event/command/result envelopes
- state: transactional persistence, append-only history, snapshots, migration
- workflow: task graph/state machine, retries, cancellation, deadlines
- capabilities: capability registry and narrow execution ports
- adapters: external provider, filesystem, network, relay, and UI adapters
- sync: outbox/inbox, authenticated batches, cursor/anchor, replay protection
- evidence: evidence capture, manifests, verification, audit exports
- recovery: backup, restore, rollback, promotion guard
- observability: redacted logs, metrics, health, diagnostics

Dependency rule: outer adapters depend inward on contracts/ports; core policy and domain logic must not import network servers, UI, OS process execution, or concrete providers. The composition root wires dependencies. No module may bypass policy or write another module's state directly.

## 7. Security and failure rules

- Deny by default; explicitly forbidden actions remain forbidden regardless of caller claims.
- No arbitrary shell, arbitrary filesystem, arbitrary network fetch, deployment, or provider invocation unless a separately defined capability and authorization contract explicitly grants it.
- No secrets in source, manifests, events, exception messages, logs, test fixtures, or evidence bundles.
- Validate sizes, types, schema versions, duplicate JSON keys, nested secret sinks, and replay/idempotency before mutating state.
- On hash-chain, checkpoint, anchor, or provenance mismatch: stop the affected mutation/sync/recovery path and preserve evidence; do not auto-heal.
- On network outage: continue supported local operations; queue optional sync with bounded retry.
- On storage exhaustion or failed durable commit: do not report success.
- On conflicting primary identity or non-monotonic cursor: block sync/promotion and require verified recovery.
- Logs and diagnostics are redacted and never become an alternate source of truth.

## 8. Reliability invariants

1. Exactly one canonical state owner at any time.
2. Local-first operation remains available without Internet for local capabilities.
3. Every accepted mutation has a durable, replayable, verifiable record.
4. Invalid or unauthorized commands have no side effect.
5. Replaying an event or retrying a request is idempotent within its declared scope.
6. State, history, head/checkpoint, and outbox cannot silently diverge.
7. Restore does not overwrite canonical state before candidate verification and explicit authorization.
8. Every external dependency has a timeout, bounded retry policy, and explicit degraded state.
9. Module interfaces and schemas are versioned; migrations are explicit and reversible or backed by verified restore.
10. Tests and evidence must distinguish PASS, FAIL, BLOCKED, NOT_RUN, and NOT_APPLICABLE; missing evidence is never a pass.

## 9. Migration order (no big-bang rewrite)

1. Freeze baseline and inventory the current module/API/state/test surface.
2. Add architecture contract, module ownership map, dependency rules, and architecture tests.
3. Establish event/command/result envelopes, canonical serialization, and schema-version rules.
4. Harden transaction boundaries, idempotency, outbox, cursor/anchor, and recovery invariants.
5. Extract authorization/approval and secret boundaries into explicit policy ports.
6. Split workflow/capability adapters from the kernel without changing behavior.
7. Add evidence and observability contracts; make every gate produce machine-readable results.
8. Implement backup/restore and offline/degraded-mode tests.
9. Add compatibility adapters and migrations; never silently import legacy state.
10. Run regression, fault-injection, replay, corruption, offline, and recovery tests.
11. Produce an installable APK only after a separate Android packaging/build contract is proven; verify artifact provenance and installation.
12. Merge/release only after all required acceptance gates have evidence.

## 10. Acceptance gates

- A1: canonical repository and baseline identified by exact commit/tree digest.
- A2: module graph has no forbidden cycles or direct storage bypasses.
- A3: all accepted commands pass identity, policy, schema, and idempotency checks.
- A4: invalid/denied input cannot mutate state or emit success.
- A5: state/history/checkpoint/outbox atomicity and replay invariants pass fault injection.
- A6: offline local workflows pass with remote services unavailable.
- A7: VPS1/VPS2 cannot become canonical state owners; no secrets reach relays.
- A8: corruption, rollback, replay, and anchor conflicts fail closed with evidence.
- A9: backup/restore is proven by independent digest and functional recovery tests.
- A10: every gate has machine-readable evidence tied to exact source commit and environment.
- A11: test suite passes on the exact candidate commit; no untracked build artifacts or unexplained diffs.
- A12: release artifact is traceable to the verified candidate and install-tested on the target Android environment.

No gate is passed by documentation alone. This document defines intended architecture; implementation and runtime compliance remain unverified until evidence exists.
