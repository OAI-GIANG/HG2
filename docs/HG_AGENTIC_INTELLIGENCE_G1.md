# HG Agentic Intelligence Evolution — Foundation G1–G6

**Status:** Foundation candidate implemented and locally tested. **Not production-accepted; not released.**

## Pinned baseline and candidate boundary

- Canonical repository: `OAI-GIANG/HG2`, branch `hg-genesis`.
- Base SHA used for this candidate: `9d83a113ccdf1aeda656e494593fa55b9078c803`.
- Changes belong on `stt/hg-agentic-intelligence-g1-20261017`; do not copy them into a dirty/detached Termux checkout or directly move `hg-genesis`.
- All examples of successful external verification in tests use callbacks labelled `TEST_ONLY`. They verify wiring and state-machine behavior only; they are not real authority, key, identity, signature, attestation, or provider material.

## Capability matrix

| Capability | Implementation candidate | What local tests establish | What remains unproven |
|---|---|---|---|
| G1 — Task Contract / Task Compiler | `hg/task_contract.py`, `hg/task_compiler.py` | Strict bounded parser, typed fields, duplicate-key rejection, deterministic internal digest, allowlist/auth predicates, stable DAG order, cycle and unresolved-edge rejection; NL draft-provider output is treated as untrusted | Cross-language canonicalization standard, model provider configuration, trusted author/approval, runtime execution |
| G2 — Capability-aware routing | `hg/capabilities.py` | Bounded records; action/version checks; missing verifier fails closed; route proposal never enables execution | Authenticated registry source, trusted actor/approval, revocation source, production provider adapter |
| G3 — Evidence-carrying claims | `hg/evidence.py` and `SQLiteEvidenceStore` | Envelope validation, size limits, digest consistency, SQLite persistence/idempotency, event-chain and row/event projection tamper detection, injected attestation-verifier seam | Authenticated capture, trusted builder/runtime identity, independently verifiable attestation keys/policy and immutable oracle authority. A callback result is reported as an adapter result only and does not promote the claim to `VERIFIED`. |
| G4 — Transactional coordination | `hg/durable_transactions.py`; `hg/transactions.py` remains an in-memory teaching/test model | File-backed SQLite WAL state, transaction CAS/version checks, state/event projection checks, event-chain verification, same-key multi-process begin, restart recovery to `IN_DOUBT`, fail-closed authorization/evidence gates, rollback under injected database error | Actual task side effects, production recovery/rollback semantics, device power-loss testing, filesystem guarantees on target storage, remote exactly-once effect |
| G5 — Provenance-aware memory | `hg/provenance_memory.py` and `SQLiteProvenanceMemoryStore` | Digest check, durable non-secret memory records, immutable IDs, conflict reporting without auto-resolution, event-chain and row/event projection tamper detection, verifier seam | Trusted memory authority, verified expiry/revocation, runtime integration, encrypted CONFIDENTIAL/SECRET storage. Sensitivity labels are caller-supplied metadata; there is no content classifier/DLP. An arbitrary per-call provenance callback cannot promote a record to trusted/`VERIFIED`. |
| G6 — Adaptive verification budget | `hg/verification_budget.py` | Risk-adjusted units, mandatory check floor, C0 failure precedence, budget exhaustion does not create PASS | Calibrated production risk model, observed cost telemetry, policy owner and runtime enforcement |

## Task Contract v1

The exact top-level field set is defined in code: `schema_version`, `task_id`, `objective`, `scope`, `input`, `output`, `acceptance_criteria`, `evidence_requirements`, `risks`, `stop_conditions`, `next_action`, `dependencies`, `required_capabilities`, `authorization_requirement`, `created_at`, `created_by`, `contract_digest`, and nullable `approval_ref`.

Version is `hg.task-contract.v1`. Unknown/missing fields, unsupported types, duplicate JSON keys, non-standard numeric constants, invalid UTF-8, over-limit payload/nesting, invalid timestamps, scope overlap, duplicate IDs, bad digest shape/mismatch, disallowed actions and undeclared authentication requirements fail closed. NL input may be transformed only by an explicitly injected draft provider. Its response is treated as an untrusted proposal and must pass contract validation; if no provider exists the result is `TASK_DRAFT_PROVIDER_UNAVAILABLE`.

### Digest limitation

`canonical_json()` is an internal deterministic serialization using Python JSON with sorted keys and compact separators. **It is not asserted to implement RFC 8785/JCS** and is not sufficient by itself for interoperability with external signers. RFC 8785 defines ECMAScript-compatible primitive serialization, I-JSON constraints, UTF-16 property-name ordering and UTF-8 output. Before cross-language signatures/attestations are introduced, choose a tested JCS implementation or bind signatures to exact content bytes with a well-defined signed envelope and verify conformance vectors.

## Durable store and transaction semantics

`SQLiteEvidenceStore` and `SQLiteProvenanceMemoryStore` retain envelopes/records and append-only-by-API event chains inside a SQLite database. `DurableTransactionStore` uses SQLite WAL, `synchronous=FULL`, bounded `busy_timeout`, `BEGIN IMMEDIATE`, unique idempotency keys, version-checked updates and an event hash chain. Fault injection confirms a state transition is rolled back when the associated event insert fails. Four concurrent local processes attempting the same idempotency key produce one transaction and one initial event in the tested environment.

These are **local database tests**, not a power-loss certification. SQLite's WAL documentation distinguishes `synchronous=FULL` from `NORMAL`: FULL adds a WAL sync at commit to improve power-loss durability, but device storage/filesystem and hardware behavior still require testing on the actual target. Local event hashes provide tamper detection relative to the stored chain; without an externally anchored checkpoint/signature, an attacker who can rewrite the entire database may be able to recompute it. Transaction state `COMMITTED` means the coordinator accepted its protocol gates; the candidate does not execute task steps or prove exactly-once external side effects. Missing prepare/evidence/commit verifier adapters block. On process restart, unresolved `RUNNING`/`EVIDENCE_PENDING` records become `IN_DOUBT` rather than being promoted to success.

## Configured natural-language compiler entrypoint

The explicit CLI is scripts/hg-agentic-compile. It reads the task request from stdin, loads the operator-managed provider configuration only from a regular file owned by the current user with no group/other permissions, pins the provider to HTTPS host api.deepseek.com, and emits a locally validated Task Contract plus declaration plan. It does not send shell commands or invoke task tools. Using it sends the supplied request to the configured API and may incur token usage.

Example, once live JSON-output acceptance is confirmed:

    printf '%s' 'Draft a read-only task contract to summarize a local health result.' | ./scripts/hg-agentic-compile

The request/output from the model is untrusted. A 200 HTTP response alone is not an acceptance result; finish reason, JSON parse, full contract schema, policy reference, action allowlist and digest all require success. The local smoke call mentioned above did not pass output validation, so do not claim a successful live NL compiler E2E yet.

## Strict verification performed on Android/Termux

Environment observed: Android/ARM64, Python 3.14.6, SQLite 3.53.4. No extra Python package was installed for this work.

Commands:

```sh
PYTHONDONTWRITEBYTECODE=1 python -W error::ResourceWarning -m unittest -v tests.test_task_contract
PYTHONDONTWRITEBYTECODE=1 python -W error::ResourceWarning -m unittest -v tests.test_agentic_primitives
PYTHONDONTWRITEBYTECODE=1 python -W error::ResourceWarning -m unittest -v tests.test_durable_transactions
PYTHONDONTWRITEBYTECODE=1 python -W error::ResourceWarning -m unittest -v tests.test_agentic_integration
PYTHONDONTWRITEBYTECODE=1 python -W error::ResourceWarning -m unittest -v tests.test_model_provider
PYTHONDONTWRITEBYTECODE=1 python -W error::ResourceWarning -m unittest discover -s tests -v
```

Most recent complete suite run during this working session: **151 tests PASS, exit 0**, with `ResourceWarning` treated as an error; all changed candidate modules and test files also passed in-memory Python syntax compilation. Re-run against the exact final commit and check the hosted CI result before relying on this count for that SHA.

The integration test connects all six layers using callbacks named `TEST_ONLY_*`. Its success confirms test wiring, not production trust or runtime execution. An attestation or provenance callback may report that its check passed, but the evidence/memory helpers retain `UNVERIFIED` unless the hosting trust boundary is independently established; no callback in these tests is a configured production trust root. The configured model endpoint was checked without displaying credentials: the read-only model-list request returned HTTP 200 and listed deepseek-flash and deepseek-v4-pro, but not the previous deepseek-chat identifier. The only changed non-secret provider setting in the phone-local mode-0600 configuration is HG_MODEL_ID=deepseek-flash; the API key and all other tokens were left unchanged and never printed. One minimal live request to deepseek-flash returned HTTP 200 but did not yield parseable JSON under a 24-token output cap. A follow-up live generation was not completed, so live model compilation remains NOT_RUN; only mocked adapter tests establish local request shaping/validation. The code now uses a 2048-token default, JSON mode and rejects any non-stop finish reason. HNI V2.1 package tests deliberately assert that the 26 synthetic fixture records remain `NOT_RUN`; those fixtures are not an authenticated source for the historical CP0 criteria.

## External design references

- RFC 8785 — JSON Canonicalization Scheme: https://www.rfc-editor.org/rfc/rfc8785.html. Used to identify the gap between internal sorted JSON and interoperable signing canonicalization.
- in-toto Statement v1: https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md. The statement binds attestations to immutable subjects with digest identifiers.
- SLSA Provenance v1.2: https://slsa.dev/spec/v1.2/provenance. Reference for source/build provenance; does not substitute for an HG trust policy or prove this candidate's runtime origin.
- SQLite WAL: https://www.sqlite.org/wal.html and PRAGMA `synchronous`: https://www.sqlite.org/pragma.html. Reference for WAL/sync semantics; not device-specific durability evidence.
- Python graphlib: https://docs.python.org/3/library/graphlib.html. Reference for directed acyclic graph/topological-order concepts; our stable order is implemented with Kahn's algorithm and a lexical heap tie-break.
- DeepSeek Chat Completions API: https://api-docs.deepseek.com/api/create-chat-completion/ and JSON Output: https://api-docs.deepseek.com/guides/json_mode/. These document the HTTPS chat-completions endpoint and JSON response mode. They do not replace local validation, prove live endpoint output acceptance, or make model output trusted.
- DeepSeek model catalog/pricing: https://api-docs.deepseek.com/quick_start/pricing/. It identifies currently advertised model IDs and states that model use is billed by token count; prices may change.

## Remaining mandatory acceptance gates

1. **Trust authority:** select and verify a real, authorized identity/approval mechanism; callback-only tests do not satisfy this.
2. **Capability registry:** authenticate source, version, validity window and revocation; prove that untrusted task data cannot provide its own trust adapter.
3. **Evidence attestation:** independently verify signed provenance bound to artifact/source digest, build identity, runtime identity, oracle/version and raw evidence. A hash without authenticated capture is only an integrity check.
4. **Durable execution:** test actual target storage under abrupt process death/power loss, recovery, rollback and multi-process contention; verify remote peer idempotency before any external task effect.
5. **Memory:** define trusted authority, expiry/revocation policy and encryption-at-rest before confidential data; current storage rejects `CONFIDENTIAL`/`SECRET` records.
6. **Budget:** establish a governed production risk model, mandatory floors and telemetry; a unit-test score is not runtime policy evidence.
7. **Historical CP0:** the phone contains `CP0-SOURCE-RECOVERY-FINDINGS-PHASE1.md`, which records a bounded read-only search and expressly says no PRIMARY_SOURCE for all 26 original criteria was found in the inspected scope. A fresh exact-phrase search via `gh search code` with the OAI-GIANG owner filter returned no indexed matches for the searched names. This is not an exhaustive proof of nonexistence; it is also not primary-source provenance. Find the original immutable artifact, source revision, custody and authorized 26-criterion text. If absent, retain the blocker; do not silently replace it with synthetic fixtures.
8. **Release:** run the full suite and hosted CI at the exact final candidate SHA and keep canonical `hg-genesis` unchanged until all applicable acceptance gates have evidence.

**Disposition:** implementation foundation can be considered ready for review only after final candidate verification; `TECHNICAL_ACCEPTANCE=BLOCKED`, `RELEASE=NOT_RELEASED` while trust/runtime/CP0 gates above remain open.
