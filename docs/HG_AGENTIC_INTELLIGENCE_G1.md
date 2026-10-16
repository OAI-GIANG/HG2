# HG Agentic Intelligence Evolution — G1 Contract/Compiler

Status: implementation candidate spanning G1-G6 primitives; local test evidence only; not release approval.

## Scope

G1 implements a strict, pure Task Contract v1 validator and a declaration-only Task Compiler. It does not execute tasks, grant authority, inspect credentials, resolve external capabilities, or make runtime claims. Every compiled plan has `executable=false`.

## Contract fields

The complete top-level field set is declared in `hg/task_contract.py`: `schema_version`, `task_id`, `objective`, `scope`, `input`, `output`, `acceptance_criteria`, `evidence_requirements`, `risks`, `stop_conditions`, `next_action`, `dependencies`, `required_capabilities`, `authorization_requirement`, `created_at`, `created_by`, `contract_digest`, and nullable `approval_ref`.

Schema version is exactly `hg.task-contract.v1`. Unknown fields, absent fields, wrong types, duplicate JSON keys, NaN/Infinity, invalid UTF-8, oversized documents, excessive nesting and invalid SHA-256 digest are rejected. `contract_digest` is SHA-256 of sorted-key compact UTF-8 JSON for the whole object excluding `contract_digest` itself; it does not authenticate a signer or prove truth.

## Validation and state boundary

The compiler can output only `VALIDATED` or an error. `VALIDATED` means structural and graph checks passed; it does not imply `AUTHORIZED`, `RUNNING`, or `PASS`. Capability and approval registries do not exist in G1, so plans explicitly list these unresolved prerequisites when relevant. Declared forbidden actions are rejected using the current known HG authority policy.

## Dependency graph

Input is bounded by `MAX_TASKS`; all IDs must be unique, every hard/soft reference must resolve to a task in the input graph, and self-dependencies/cycles fail closed. Kahn's algorithm with a min-heap and sorted successor iteration produces deterministic topological order independent of input insertion order. An unsatisfied dependency status causes a pure gate result `BLOCKED`; it never executes work.

## Agentic capability matrix (design/implementation boundary)

| Capability | Candidate primitive | Current proof | Not established |
|---|---|---|---|
| Task Compiler | `hg/task_contract.py`, `hg/task_compiler.py` | Strict schema, bounded JSON, digest, graph validation; unit tests | Authorization/execution adapter, approved schema compatibility |
| Capability-aware routing | `hg/capabilities.py` | Shape validation and deterministic blocked routing | Trusted source, signature, revocation, live provider registry |
| Evidence-carrying claims | `hg/evidence.py` | Envelope integrity and revision/oracle consistency tests | Trusted capture, external attestation, trust promotion |
| Transactional execution | `hg/transactions.py` | In-memory state transition/idempotency model tests | Durable journal, multi-process CAS, rollback or exactly-once side effects |
| Provenance-aware memory | `hg/provenance_memory.py` | Missing provenance, caller promotion and conflict tests | Trusted memory authority, expiry verifier, persisted state integration |
| Adaptive verification budget | `hg/verification_budget.py` | Mandatory floor, critical fail precedence and budget exhaustion tests | Calibrated production risk model, real cost telemetry |

None of these G2-G6 primitives is wired into `phone_runtime.py`; no provider or external operation is invoked. This is deliberate because capability trust, evidence authentication and durable transaction semantics are not yet established.

## Test matrix

`tests/test_task_contract.py` covers strict JSON, absent/unknown fields, wrong types, digest mismatch, scope conflict, approval prerequirement, allowlist enforcement, capability-not-assumed, missing criteria/evidence, DAG order, cycles, self-cycle, missing dependency, duplicate IDs, determinism, shared dependency, resource ceiling, and fail-closed observed status. `tests/test_agentic_primitives.py` covers capability provenance, evidence trust boundaries, transaction idempotency/recovery, provenance memory conflicts, and risk-adaptive verification budget. Expected error codes and state boundaries are explicitly asserted.

Run on Android/Termux with Python 3.14.6:

```sh
PYTHONDONTWRITEBYTECODE=1 python -W error::ResourceWarning -m unittest -v tests.test_task_contract
```

Historical CP0 26-criteria source provenance remains an independent unresolved blocker. Synthetic HNI V2.1 fixtures remain synthetic and `NOT_RUN`; they are not authentic source provenance and are not proof of real model/runtime intelligence behavior.

## Known blocked integration points

- No verified approval verifier or trusted actor identity binding.
- No capability registry or revocation source.
- No execution coordinator, evidence/claim verifier, or immutable oracle registry.
- No durable task state transition contract and no proof of multi-process atomic/idempotent execution.
- Existing history hash chain records events but does not alone establish external provenance or transaction semantics.

## External references consulted

- JSON Schema Validation: https://json-schema.org/draft/2020-12/json-schema-validation
- Python `json` decoder `object_pairs_hook`: https://docs.python.org/3/library/json.html
- Python `graphlib.TopologicalSorter` and cycle/order semantics: https://docs.python.org/3/library/graphlib.html
- SLSA build provenance explains why provenance must identify trusted builder, inputs and output subjects: https://slsa.dev/spec/v1.2/provenance

These references inform the design only; no external reference is treated as evidence that a missing HG2 runtime capability exists.
