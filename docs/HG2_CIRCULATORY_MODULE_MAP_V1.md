# HG2 Circulatory Module Map V1

This is a responsibility map, not a claim that all listed modules already exist.

| Logical module | Body analogy | Owns | Must not own |
|---|---|---|---|
| Brain/orchestrator (hg.agent) | Brain | Coordinate one bounded user turn and compose runtime/provider/tool router | Canonical state ownership, policy decisions, raw storage writes |
| Kernel/runtime (hg.phone_runtime) | Heart | Lifecycle, canonical state composition root, local command execution | Remote authority, provider-specific logic |
| Authentication (hg.auth) | Senses identifying a caller | Validate credentials and issue sealed scoped principals | Authorizing actions or mutating state |
| Policy/approval (hg.policy) | Immune system | Single authorization decision point, approval state, grants/denials | Executing tools or storing secrets in decisions |
| Identity | Self-recognition | Product/runtime/device IDs, provenance labels | Grants or mutable user data |
| Contracts/serializer | Bone marrow / blood schema | Versioned command/event/result schemas and canonical bytes | Business side effects |
| State/history | Circulating blood + tissue memory | Transactions, append-only history, snapshots/checkpoints | Network calls or user interface |
| Workflow | Nervous system | Task graph, lifecycle, retry/cancel/deadline state | Direct access to private adapter internals |
| Capability ports | Organ interfaces | Typed contracts for each capability | Choosing policy or mutating canonical state independently |
| Provider adapter (hg.provider) | Lungs | One bounded external inference transport, HTTPS and response validation | Canonical state, authorization decisions, secret export to relays |
| Tool router (hg.toolplane) | Nervous system | Bounded provider/tool call loop, allowlist, redacted audit, route mutations through runtime/policy | Raw-store constructors, direct session creation, arbitrary ambient authority |
| Local tool capabilities | Hands/muscles | Explicitly granted typed operations | Arbitrary shell/filesystem/network access |
| Sync/outbox | Arteries and veins | Ordered outbound delivery, inbox deduplication, cursor/anchor | Becoming the source of truth |
| Edge relay | Peripheral circulation | Authenticated relay, limited metadata | Provider keys, task authority, canonical history |
| Evidence verifier | Kidneys | Integrity checks, provenance checks, gate results | Auto-repairing failed evidence |
| Backup/recovery | Renal filtration / repair | Backup manifests, quarantine, restore drills | Implicit primary promotion |
| Observability | Lymphatic surveillance | Redacted logs, metrics, audit traces | Secrets or canonical writes |
| UI/voice/CLI | Skin and senses | Input/output presentation | Authorization bypass or direct state writes |
| Android packaging | Body enclosure | Build/install/update mechanics | Modifying domain state or changing authority |

## Allowed dependency direction

UI/Inputs -> Authentication -> Brain/Agent -> Policy -> Tool Router/Workflow -> Capability/Provider Ports -> Runtime/State Interfaces

The kernel composes implementations. Domain contracts and policy do not import concrete network servers, Android UI, process execution, or provider SDKs. State access is granted through narrow interfaces and policy-checked commands.

## Canonical circulation

input -> authentication -> brain/agent -> policy -> validation -> workflow/tool router -> capability/provider -> result validation -> local transaction -> append-only event -> evidence -> response

Optional remote circulation starts only after local commit:

event/outbox -> authenticated transport -> relay -> acknowledgement -> monotonic cursor


## Single-owner implementation notes

- hg.policy owns action allowlists and principal-bound decisions; hg.auth only authenticates credentials and defines configurable scopes. The scope registry is imported by policy rather than restated. Both provider.invoke and session.create require a sealed principal; boolean verifier results do not count as authentication.
- hg.authority remains a thin compatibility facade for old import paths; it is not an independent policy owner and is excluded from the active module registry.
- hg.contracts owns shared canonical JSON, strict duplicate-key parsing and content digest helpers. Provider responses and tool arguments reuse these primitives instead of private copies.
- hg.agent composes the application turn; hg.phone_runtime remains the only composition root for canonical state. hg.toolplane accepts the runtime interface and routes session creation through it.
- The manifest registers exactly one active model/provider transport: hg.provider. A separate model_gateway or model_provider must not be added without first replacing, not duplicating, this owner.
