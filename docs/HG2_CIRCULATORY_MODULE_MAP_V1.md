# HG2 Circulatory Module Map V1

This is a responsibility map, not a claim that all listed modules already exist.

| Logical module | Body analogy | Owns | Must not own |
|---|---|---|---|
| Kernel/runtime | Heart | Lifecycle, composition root, local command execution | Remote authority, provider-specific logic |
| Identity | Blood group / self-recognition | Product/runtime/device IDs, provenance labels | Grants or mutable user data |
| Policy/approval | Immune system | Authorization predicates, approval state, grants/denials | Executing tools or storing secrets in decisions |
| Contracts/serializer | Bone marrow / blood schema | Versioned command/event/result schemas and canonical bytes | Business side effects |
| State/history | Circulating blood + tissue memory | Transactions, append-only history, snapshots/checkpoints | Network calls or user interface |
| Workflow | Nervous system | Task graph, lifecycle, retry/cancel/deadline state | Direct access to private adapter internals |
| Capability ports | Organ interfaces | Typed contracts for each capability | Choosing policy or mutating canonical state independently |
| Provider adapters | Lungs | External inference/service calls | Canonical state or secret export to relays |
| Local tool adapters | Hands/muscles | Explicitly granted local operations | Arbitrary ambient authority |
| Sync/outbox | Arteries and veins | Ordered outbound delivery, inbox deduplication, cursor/anchor | Becoming the source of truth |
| Edge relay | Peripheral circulation | Authenticated relay, limited metadata | Provider keys, task authority, canonical history |
| Evidence verifier | Kidneys | Integrity checks, provenance checks, gate results | Auto-repairing failed evidence |
| Backup/recovery | Renal filtration / repair | Backup manifests, quarantine, restore drills | Implicit primary promotion |
| Observability | Lymphatic surveillance | Redacted logs, metrics, audit traces | Secrets or canonical writes |
| UI/voice/CLI | Skin and senses | Input/output presentation | Authorization bypass or direct state writes |
| Android packaging | Body enclosure | Build/install/update mechanics | Modifying domain state or changing authority |

## Allowed dependency direction

UI/Adapters -> Capability Ports -> Workflow/Policy/Contracts -> State Interfaces

The kernel composes implementations. Domain contracts and policy do not import concrete network servers, Android UI, process execution, or provider SDKs. State access is granted through narrow interfaces and policy-checked commands.

## Canonical circulation

input -> identity -> policy -> validation -> workflow -> capability -> result validation -> local transaction -> append-only event -> evidence -> response

Optional remote circulation starts only after local commit:

event/outbox -> authenticated transport -> relay -> acknowledgement -> monotonic cursor
