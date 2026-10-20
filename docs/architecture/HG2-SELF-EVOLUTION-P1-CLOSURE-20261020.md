# HG2 — Self-Evolution P1 Closure Record

- Date: 2026-10-20 (Asia/Ho_Chi_Minh)
- Repository: `OAI-GIANG/HG2` only
- Branch: `stt/hg2-self-evolution-p1-closure-20261020`
- Base commit: `cc7ffb39c58f4c4090a13ccaa414af3b70e109dc`
- Status: **P1 modules implemented and tested in isolation; not connected to live PhoneRuntime; production cutover and continuous self-evolution NOT CLOSED.**
- Review boundary: literature-backed STT multi-perspective critique; no human independent review and no GitHub independent-review feature used.

## MTC-1.0

### OBJECTIVE
Resolve a single task-state contract, provide source-backed evidence verification, and add scoped/versioned experience records without adding a second brain, task database, or runtime mutation loop.

### SCOPE
- One logical task-state owner for any new workflow integration: `SQLiteStateStore` with the existing `WorkflowService`.
- The existing file-backed `StateStore` remains unchanged for current PhoneRuntime/history. No state migration or cutover was attempted.
- Add a filesystem evidence verifier with a configured identity, trust-root digest, allowlisted roots, digest-pinned references and explicit “bytes verified, semantic truth not verified” semantics.
- Upgrade the R1 evolution gate to require a verifier identity and receipt reference for each cited evidence item; bool-only callbacks are invalid.
- Add an experience-memory envelope on top of `SQLiteProvenanceMemoryStore`, preserving provenance, scope, task linkage, time validity, lineage, conflict ids, and proposed supersession.
- All new tests use temporary directories/databases. No production data path, secret or live service was opened for mutation. No package installed.

### INPUT
Pinned HG2 branch source at the commit above, existing R1 source and test oracle, existing SQLite task store, file-backed history contract, provenance-memory implementation and its regression tests, and published technical references listed below.

### OUTPUT
- `hg/workflow_store_adapter.py`
- `hg/evidence_verifier.py`
- `hg/experience_memory.py`
- hardened `hg/evolution.py` evidence-verifier contract
- focused tests and full-suite log under `evidence/HG2-SELF-EVOLUTION-P1-20261020/logs/`
- this closure record, machine-readable audit and SHA-256 manifest

## 1. Findings from existing architecture inventory

| Component | Existing contract | Disposition |
|---|---|---|
| `hg/history.py::StateStore` | Append-only JSONL/hash chain with head + state projection files and explicit crash recovery; no SQLite task projection transaction or service mutation permit API | KEEP for existing PhoneRuntime/history; do not use directly for WorkflowService; no automatic migration |
| `hg/workflow.py::WorkflowService` | Task state machine with idempotency, principal-scoped authorization and one-shot mutation permits; requires a richer store port | KEEP; expose through typed adapter, not direct runtime cutover |
| `hg/sqlite_state.py::SQLiteStateStore` | SQLite WAL, `synchronous=FULL`, `BEGIN IMMEDIATE`, task projection replay, idempotency, approvals/outbox and integrity verification | SELECT as the task store for new integration. It is the only backend accepted by the new workflow adapter |
| `hg/durable_transactions.py::DurableTransactionStore` | Higher-level transaction/step/evidence ledger, `IN_DOUBT` and recovery states | KEEP for coordination transactions; not a drop-in task database and not dual-written |
| `hg/provenance_memory.py::SQLiteProvenanceMemoryStore` | Append-preserving provenance records and hash-linked store-event log, record integrity, explicit conflict detection, conservative trust policy | REUSE as existing immutable memory store; experience schema wraps it rather than adding another SQLite database |
| `hg/evolution.py` (R1) | Deterministic candidate evaluator that could previously accept a bare boolean callback as verifier success | HARDEN: require a typed decision tuple and non-empty receipt reference; invalid or missing verification returns INCONCLUSIVE |
| `hg/model_gateway.py` | Hosted OpenAI-compatible model adapter, configured by environment variables | KEEP optional; R1/P1 do not require a paid provider and do not claim free general-purpose generation |

### State ownership decision
Do not dual-write a single task to the file journal, SQLite task projection and durable transaction ledger. New task workflows use one `SQLiteStateStore` instance for event, task projection, idempotency and outbox. The original PhoneRuntime keeps its current state owner until a separate, evidence-backed migration/cutover with snapshot verification, rollback and device runtime testing. The adapter intentionally refuses legacy `StateStore`.

SQLite atomicity applies to updates inside the SQLite transaction; it does not make remote-provider calls atomic with local state. The high-level transaction ledger and task store therefore remain distinct logical contracts, with recovery/reconciliation at the side-effect boundary. See the SQLite documentation references below.

## 2. Evidence verifier contract

`FilesystemEvidenceVerifier`:
- accepts an explicit verifier ID, trust-root digest, allowlisted local roots and maximum byte size;
- rejects configured roots that are symlinks, reference traversal, missing/ambiguous files, target symlinks, non-regular files, oversized content, read/open races detected by inode/device mismatch, unsupported URL schemes and digest mismatches;
- the trusted decision callback requires references of the form `evidence:<sha256>/<relative-path>` or `path:<sha256>/<relative-path>`; a bare path is not enough for the evolution gate;
- returns a receipt reference tied to the verifier ID, trust-root digest, actual SHA-256, byte length and resolved file path;
- explicitly sets `semantic_truth_verified=false`. Matching bytes proves only that the observed file matched the expected digest, not that its contents are factually correct, that an actor is authentic, or that a test result is semantically valid.

The R1 evaluator now rejects:
- absent/unidentified verifier: `INCONCLUSIVE / EVIDENCE_VERIFIER_REQUIRED`;
- verifier raises: `INCONCLUSIVE / EVIDENCE_VERIFIER_ERROR`;
- malformed bool-only response: `INCONCLUSIVE / EVIDENCE_VERIFIER_INVALID_RESPONSE`;
- verifier denial or digest mismatch: `INCONCLUSIVE / EVIDENCE_REFERENCE_UNVERIFIED`.
Eligible/decision records contain the verifier identity and one non-empty receipt reference for every cited evidence object. A production caller must still trust and constrain the verifier implementation and its configured root. The in-test callback is a test stub, not a production trust root.

### Boundaries
- This initial verifier handles local files only. Network URL retrieval, signature identity and semantic test-log evaluation need separate pinned adapters.
- The configured root digest is supplied by the trusted caller; this constructor does not independently certify who owns that trust root.
- A local SHA-256 manifest is integrity evidence, not proof of external authorship or independent review.
- No automatic promotion/activation, remote-write execution, merge to `hg-genesis` or deployment exists here.

## 3. Experience memory contract

`hg/experience_memory.py` wraps the existing provenance store and adds:
- schema version `hg.experience-memory.v1`;
- source reference + source digest + authority reference + observation time and validity interval;
- logical scope, task ID, experience type (`OBSERVATION`, `HYPOTHESIS`, `DECISION`, `FAILURE`, `LESSON`, `PLAN_RESULT`);
- parent-memory IDs, `supersedes`, `superseded_by`, explicit `ACTIVE/SUPERSEDED/REVOKED` status and conflict IDs;
- canonical record digest and restart-stable immutable storage, using the provenance store's existing conflict and append-event log;
- scope/time-bound retrieval that leaves conflicting records unresolved;
- supersession proposal validation which checks memory key, scope, source and link but does not rewrite/delete the old record or autoactivate its successor.

All experience records are created with `trust_level=UNVERIFIED`, and the store rejects self-promotion. A source verifier returning a self-asserted pass is not used to make a record `VERIFIED`. Supersession remains a proposal unless a separate trusted authority and evidence procedure is integrated; this P1 slice does not implement an atomic “old revoked + new promoted” operation. This avoids misleading claims of supersession closure.

## 4. Test evidence

Environment: Android/Termux via Remote Desktop Commander; Python from the active Termux environment; standard library and existing repository dependencies only. Test data uses temporary directories/databases. `ResourceWarning` is promoted to error in the full suite.

- Focused P1 + R1 + Brain/registry/harness tests: **100 passed**, 0 failed, 0 errors (`logs/focused-regression.log`; 0.887s).
- Full repository regression on final P1 source after rebase: **379 passed**, 0 failed, 0 errors (`logs/full-regression.log`; 46.404s).
- AST parsing of all four new/changed Python modules and their new tests: PASS.
- `git diff --check`: PASS.
- `SHA256SUMS`: regenerated after the rebase and rechecked before commit.
- No test from the temporary databases mutates production state, and no runtime service is wired to this adapter.

The full suite proves these changes did not regress the checked repository tests on this Termux environment. It does not establish OEM background reliability, production deployment readiness, general model reasoning capability, or zero-cost open-ended generation.

## 5. External sources and design implications

| Source | Design use | Limit |
|---|---|---|
| SQLite, Atomic Commit — https://www.sqlite.org/atomiccommit.html | Use transaction boundaries for event + task projection and test fault points; do not equate that to atomic remote calls | Depends on the documented SQLite/filesystem/hardware assumptions |
| SQLite, Write-Ahead Logging — https://www.sqlite.org/wal.html | WAL is suitable for a same-host phone-local store when the database and WAL lifecycle are handled correctly | WAL is not a network-filesystem protocol; runtime cutover needs target-device verification |
| Python sqlite3 transaction control — https://docs.python.org/3/library/sqlite3.html | Keep explicit transaction and commit/rollback semantics; test on the actual Python version | Documentation does not certify the HG2 adapter |
| W3C PROV Primer — https://www.w3.org/TR/prov-primer/ | Model sources, activities and agents as provenance; distinguish provenance from truth | A provenance record is not itself a trusted signature or semantic verifier |
| OWASP GenAI Excessive Agency — https://genai.owasp.org/llmrisk/llm062025-excessive-agency/ | Least privilege, narrow tool access and policy checks outside model output; high-impact operations remain separately authorized | This does not constitute a security audit of HG2 |
| NIST SSDF v1.1 — https://csrc.nist.gov/pubs/sp/800/218/final | Keep regression, evidence and recurrence-prevention gates in the development lifecycle | Guidance, not certification |

## 6. Risks and remaining gates

| Item | Status | Required next evidence |
|---|---|---|
| Single task store contract | IMPLEMENTED + TESTED in temporary SQLite store | Integrate adapter only after explicit PhoneRuntime composition design; confirm one store instance, no shadow store |
| Workflow crash recovery | BASIC restart/projection checks TESTED; runtime cutover UNVERIFIED | Kill/restart at store boundaries, concurrent writers, outbox reconciliation, exact phone filesystem/WAL recovery |
| Evidence file verifier | IMPLEMENTED + TESTED for local allowlisted files | Trust-root provisioning and independent semantic log/oracle verifier |
| Experience memory schema | IMPLEMENTED + TESTED; conflict and lineage handling present | Atomic supersession/activation design with authenticated approval; exact source verification and expiry injection tests |
| Supersession promotion | NOT IMPLEMENTED | Never change trust/status automatically until atomic, policy-authorized successor operation and rollback tests exist |
| Model-driven idea generation | BLOCKED_UNVERIFIED | Find/install no model unless a free license, source digest, runtime compatibility and phone resource budget are verified |
| Offline general-purpose generation | NOT AVAILABLE in inspected Termux shell | Prove compatible local LLM/runtime; the cached TTS model is not treated as a reasoning model |
| Autonomous queue/scheduler and self-recovery | NOT IMPLEMENTED | First bind task storage and side-effect state machine with IN_DOUBT reconciliation; test background kill/reboot/low storage/network loss |
| Production/continuous self-evolution | NOT CLOSED | Measured long-running task evidence, held-out evaluation, rollback, reviewer-free policy gates and stable Android operations |

## 7. Stop conditions and claims policy

Stop/reject on unknown state owner, mismatch between task projection and replay, corrupt event chain, expired/missing authority, non-pinned evidence, verifier bool-only result, unknown scope/capability, unverified source/license, failed C0 oracle, regression, uncertain external side effect or unbounded resource use.

An evaluation status of `PROMOTION_ELIGIBLE` is not an authorization to promote. A stored experience is not automatically trusted knowledge. A passing unit/full regression run does not make the live runtime operational. A configured or cached speech model does not prove a free general-purpose reasoning model exists.

**P1 closure status:** Implementation and current repository regression are ready for integration testing on an isolated branch. **Full P1 closure remains blocked** on trusted production evidence semantics, runtime state-owner cutover/recovery proof, authorized supersession promotion, and general-purpose offline model availability. No production deployment or continuous autonomous self-evolution is claimed.
