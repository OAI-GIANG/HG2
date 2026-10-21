# HG2 — Memory Reliability & Anti-Forgetting Audit R1

- Audit ID: HG2-MRAF-READONLY-AND-ORACLE-20261019-R1
- Date: 2026-10-19
- Repository: OAI-GIANG/HG2 only
- Base commit: c2161feb76b2be8964a109910475a5b1a018eb1a
- Branch: stt/hg2-brain-orchestrator-r1-20261019
- Environment observed: Android/Termux, aarch64, Python 3.14.6
- Scope: source and test inspection; synthetic oracle and fault injection only in TemporaryDirectory. No production data modified, no live provider calls, no merge/deploy.
- PR #29: OPEN · DRAFT; head c2161feb76b2be8964a109910475a5b1a018eb1a.

## 1. Executive result

**OVERALL: MRAF_ACCEPTANCE_FAIL / P0-A_RECOVERY_BLOCKED.**

HG2 has basic persistent memory CRUD, hash-chained event history, checksums, idempotency/version checks, scoped lexical recall, tombstones, provenance metadata in a separate module, exact-key conflict detection, a standalone transactional SQLite state implementation, and a backup/replica implementation. These are not equivalent to a complete, runtime-integrated anti-forgetting system.

Critical source evidence:
- `hg/phone_runtime.py` constructs `StateStore` then `MemoryStore(self.store)`.
- `hg/history.py:224-260` appends and fsyncs the event journal, then writes `state.json` and `head.json` separately.
- `hg/sqlite_state.py` has transactional event/projection/meta operations but `SQLiteStateStore` is not the PhoneRuntime store.
- `hg/provenance_memory.py` defines `SQLiteProvenanceMemoryStore`, but no instantiation is wired from active `hg/*` runtime modules found in this inspection.
- `hg/memory.py:194-245` implements ACL-filtered lexical token-overlap retrieval; it does not enforce `observed_at` / `expires_at`.

## 2. Classification legend

- IMPLEMENTED: code path identified; distinguish standalone code from active runtime wiring.
- TESTED: matching test executed and passed under the recorded conditions.
- VERIFIED: claim directly rechecked from source/test evidence; not a claim of production operation.
- OPERATIONAL: live target device/service behavior observed. This audit does not assign OPERATIONAL to production anti-forgetting components.
- PARTIAL: components exist but full acceptance contract is not met.
- MISSING: no active implementation/evidence found in inspected scope.
- UNKNOWN: state cannot be resolved from available evidence.

## 3. Findings

### F-01 — P0 — split-file state persistence causes unrecoverable startup after some write failures
Status: CONFIRMED.
Evidence: `hg/phone_runtime.py:22-24`; `hg/history.py:224-260`; `hg/sqlite_state.py:125+`.
The current PhoneRuntime uses file-backed StateStore. The append-only journal is written and fsynced before projection and head checkpoint are written as separate replacements. Synthetic injections at the state write, head write and journal fsync boundaries showed the journal can advance while the head remains old. Reopening raised `HistoryError: log does not match head checkpoint`.
Interpretation: fail-closed detection is present; safe recovery/reconstruction and availability are not. P0-A remains blocked.

### F-02 — P1 — lexical retrieval misses paraphrased memory
Status: CONFIRMED.
Evidence: `hg/memory.py:194-222`; existing `tests/test_memory.py:test_retrieve_and_context_manifest`; MRAF-C2 synthetic query.
A synthetic memory with title “favorite color” and content “cerulean” was queried with “which hue is liked”. The current lexical-overlap implementation returned no matches. This demonstrates a functional forgetting mode even when the record remains durable.

### F-03 — P1 — freshness/provenance metadata does not govern current recall
Status: CONFIRMED.
Evidence: `hg/provenance_memory.py:34-128,130-164`; `hg/memory.py:194-245`; `hg/phone_runtime.py:22-24`.
Provenance fields capture source/authority/timestamps/expiry and leave trust UNVERIFIED by default. But this separate store is not wired into the active PhoneRuntime memory path, and current recall does not check expiry. No active expiry suppression test or end-to-end periodic revalidation was found.

### F-04 — P1 — contradiction detection is narrow
Status: PARTIAL.
Evidence: `hg/provenance_memory.py:166-183` and `SQLiteProvenanceMemoryStore.list_conflicts`.
Exact same-source/same-key records with different value digests are labelled `CONFLICT_UNRESOLVED`; the system does not choose a winner, which is safe. This does not prove broad semantic contradiction detection across different sources or phrasings.

### F-05 — P1 — replica/backup implementation exists, production restore is not proven
Status: PARTIAL / OPERATIONAL UNKNOWN.
Evidence: `hg/replica.py:102-232`; `tests/test_replica.py:test_sqlite_backup_restore_preserves_replica_evidence`; `docs/HG2_DURABLE_REPLICA_RUNBOOK_V1.md`.
The replica supports atomic idempotent batch ingest and is documented as backup/relay only. Unit tests do not establish an active backup schedule, valid offsite copy, or a real target-phone restore drill.

### F-06 — P1 — automatic consolidation/anti-forgetting workflow missing
Status: MISSING in inspected active runtime.
No runtime-integrated review queue/scheduler, expiry enforcement, semantic memory consolidation, recall-quality maintenance or forgotten-memory recovery protocol was found. The R3 plan describes desired contracts but documentation is not runtime evidence.

### F-07 — P1 — standalone SQLite state store should not be mistaken for active fix
Status: IMPLEMENTED + TESTED standalone; not integrated.
Evidence: `hg/sqlite_state.py`, `tests/test_sqlite_state.py`.
SQLite transaction tests verify rollback and integrity checks. However, it is not wired into PhoneRuntime, and replacing the canonical store without an explicit migration plan would create risk of an accidental second state authority.

## 4. MRAF M1–M5 matrix

| Capability | Status | Implemented | Gaps |
|---|---|---|---|
| M1 Durable capture | PARTIAL | versioned records, checksums, journal, idempotency, update versions, tombstones | crash consistency across journal/state/head; target restore evidence |
| M2 Intent-aware recall | PARTIAL | ACL-filtered lexical retrieval, context manifest, bounded context | paraphrase false negative; no frozen semantic recall oracle or quality thresholds |
| M3 Provenance & contradiction safety | PARTIAL | separate provenance schema, unverified-default trust, exact-key conflict detection, SQLite chain/store integrity checks | standalone/not wired; no independent authority binding; no general semantic contradiction verifier |
| M4 Consolidation & freshness review | MISSING | expiry metadata and missing-metadata blockers exist in standalone schema | no active expiry suppression, scheduler/review queue, evidence-backed supersession or consolidation |
| M5 Restore & auditable recovery | PARTIAL | integrity checks, tamper tests, SQLite transaction/replica primitives | active file-backed store cannot safely reconstruct after tested split-write failures; no live restore/reboot/low-storage evidence |

## 5. Fixed acceptance oracle

Version: `HG2-MRAF-ORACLE-1.0`
Scope: synthetic data, temporary directories only.

| Case | Expected criterion | Observed result | Verdict |
|---|---|---|---|
| MRAF-C1-RESTART-ROUNDTRIP | Memory record survives valid restart exactly | Saved record equals reopened record | PASS |
| MRAF-C2-SEMANTIC-RECALL-GAP | Paraphrase query recalls related memory | No matching IDs under lexical retrieval | FAIL — confirmed recall limitation |
| MRAF-C3-CORRUPT-HEAD-FAIL-CLOSED | Corrupt head not accepted as healthy | Raises HistoryError “head checkpoint unreadable” | PASS for corruption detection only |
| MRAF-C4-TORN-APPEND-FAIL-CLOSED | Torn journal not accepted as healthy | Raises HistoryError “history log missing final newline” | PASS for corruption detection only |
| MRAF-C5-CONFLICT-UNRESOLVED | Exact-key contradictory values remain unresolved | CONFLICT_UNRESOLVED | PASS |
| MRAF-C6-UNVERIFIED-NOT-PROMOTED | Missing source/authority/time/expiry cannot gain trust by caller label | UNVERIFIED with blockers | PASS |
| MRAF-C7-NO-SILENT-OVERWRITE | Same ID with different provenance record rejected | MEMORY_ID_CONFLICT; stored event chain integrity passed | PASS |

**Oracle verdict: FAIL.** C2 fails by design: the test exposes a real limitation. C3/C4 passing means corrupted state is detected and denied, not that it is automatically recovered.

## 6. P0-A fault injection

Version: `HG2-MRAF-FAULT-INJECTION-1.0`

| Injection boundary | Observed result | Gate |
|---|---|---|
| `_write_state` throws after journal append | emit throws; journal advances; restart rejects log/head mismatch | FAIL — recovery gate |
| `_write_head` throws after journal + projection | emit throws; restart rejects log/head mismatch | FAIL — recovery gate |
| journal `fsync` throws | emit throws; restart rejects log/head mismatch | FAIL — recovery gate |

The tests used only disposable TemporaryDirectory state. They prove this fault window is detected; they do not prove power-loss durability, safe rollback, or reconstruction. P0-A remains BLOCKED.

## 7. Existing tests actually executed

Command:
```sh
PYTHONDONTWRITEBYTECODE=1 python -W error::ResourceWarning -m unittest tests.test_memory tests.test_provenance tests.test_integrity_v2 tests.test_core tests.test_sqlite_state tests.test_durable tests.test_replica -v
```

Result: **68 tests passed in 4.291 seconds**, exit code 0.

Prior full-suite evidence at the same base commit: **258 passed in 25.952 seconds**, log SHA-256 `31a5fabac0ee673231adf1329038fb72c79fddb0c6bd632c0fd254c243b36fef`. This is existing prior evidence, not a full MRAF acceptance pass.

## 8. Recommended closure order

1. P0-A first: make active canonical state atomic or define and authorize deterministic reconstruction from a verified event journal. Do not simply wire the existing SQLiteStateStore without a migration, ownership and rollback plan.
2. Freeze crash/fault oracle at every write, flush, fsync, rename, restart and replay boundary. Include corruption cases where repair must be refused.
3. Bind provenance and freshness policy into the actual memory read path without creating a second state authority. Expired/missing freshness must be explicit and fail closed according to memory type.
4. Add fixed semantic retrieval corpus covering exact terms, paraphrase, Vietnamese diacritics, ambiguity, false positives, ACL leakage, stale records, contradiction and supersession. Track both recall and precision.
5. Define explicit memory lifecycle states: ACTIVE, STALE, CONFLICT_UNRESOLVED, SUPERSEDED, REVOKED, TOMBSTONED. No silent promotion or overwrite.
6. Add authorized snapshot/restore rehearsal on the target phone and verify recovered record counts, event chain/head, projection agreement, known retrieval probes and tombstones.
7. Only then implement scheduled consolidation; it must be deterministic, auditable, idempotent, and unable to transform untrusted memory into verified fact.

## 9. SHA-256 source provenance

Hashes were captured from source/evidence bytes inspected at base commit `c2161feb76b2be8964a109910475a5b1a018eb1a`.

| File | SHA-256 |
|---|---|
| `hg/history.py` | `0f311e069905574c512c358f27db3ae6679dd4e88ab36a83bd1d05209bc63fc8` |
| `hg/memory.py` | `4c1e5b1346bc757ad6308d23a56850e5c79d3292ef07a47d2f551c406c97ec54` |
| `hg/phone_runtime.py` | `d415b3249f3332ff406b35c5883e2c26603ad680b5da0b3490999da58592a730` |
| `hg/provenance_memory.py` | `f0b5c89160ff62f606dd0a3229e7374577d0393bc78243077b9a571ae7f1882b` |
| `hg/sqlite_state.py` | `bfe4b33156c2a0ee2356ac1eb3dc0416dcbd0f6a77326c87a2d1a95ddf4366d6` |
| `hg/replica.py` | `bff7234ce97b25c2051e959aaad907f420e16c9470b5959b2d6947b3e3c057e5` |
| `tests/test_memory.py` | `d99f8bca1c511c1aadef8affd6b4fefea9c1e2227ffcfd021d687fe47a726562` |
| `tests/test_provenance.py` | `051fa1e67605beef9233685e9a4fe8ba4adca056f88a4b449788ac980afc243f` |
| `tests/test_integrity_v2.py` | `5c157608203405a7f5c862e15e420ecd6c33e792d9de8475c4f4f070806c60fd` |
| `tests/test_core.py` | See verified SHA-256 output in the audit shell log; copied digest was truncated and is intentionally not asserted here. |
| `tests/test_sqlite_state.py` | `bdde3e077b3ec2e4157ab1972585e343775b127d556669db3646efe128de43c8` |
| `tests/test_durable.py` | `4f30269117d2e23d687d73e7338ee1f192a4f15663fcd1cef5409953e9b939cc` |
| `tests/test_replica.py` | `bd1c82a13c158cb5fe2d69040971b2949096ae972d1a29191fd00ae840d012ee` |
| prior full regression log | `31a5fabac0ee673231adf1329038fb72c79fddb0c6bd632c0fd254c243b36fef` |
| existing SHA manifest | `3c90e826c393d9301d00617743e3a3c0b212e66e24fcae73edf3aa00407f98e7` |

Note: verify exact file hashes with the generated SHA256SUMS before relying on any copied row. A digest proves byte consistency, not semantic correctness.

## 10. Governance and stop condition

- PR #29 remains OPEN · DRAFT, head `c2161feb76b2be8964a109910475a5b1a018eb1a`.
- No merge or deployment performed.
- Before creating this audit artifact, the code checkout was clean after removing test-generated `hg/__pycache__`. Final worktree has only the new untracked directory `evidence/HG2-MRAF-AUDIT-20261019/`; source code and prior evidence are unchanged.
- No independent human review obtained.
- At the original audit point, P0-A, M2 recall quality, M4 freshness/consolidation and real restore proof were still open. Follow-up section below supersedes P0-A only; overall MRAF acceptance remains FAIL until M2/M4 and production restore/independent review are addressed.

## Follow-up closure — P0-A atomic state recovery (2026-10-19)

This section supersedes only the earlier P0-A status above; it does not close the remaining MRAF findings.

- Result: **P0-A PASS for the explicitly tested recoverable crash windows**. Full regression: 281 tests passed; fault-injection suite: 22 tests passed; pre/post crash observation oracle: 27/27 cases passed.
- Canonical authority remains `history.jsonl`. `state.json` is a derived projection and `head.json` is an anti-rollback/checkpoint anchor. `SQLiteStateStore` remains unintegrated and is not a second state authority.
- The active `StateStore` now uses atomic temp-file writes with flush/fsync/replace/directory-fsync; validates the complete journal before reconciliation; permits only the verified one-event-ahead recovery window when projection matches a known state; preserves partial invalid tail bytes by digest and writes a recovery receipt before truncation; and records recovery in the journal idempotently. A durable bootstrap marker makes first-genesis creation recoverable.
- The in-memory writer is poisoned after any append/projection/checkpoint write error; later `emit()` calls on that same instance fail until a fresh `StateStore` verifies/reconciles disk state, preventing the checkpoint lag from being extended by a second event.
- Abrupt subprocess termination was injected after each ordinary write fsync boundary, state/head replace, partial/flush writes, and each bootstrap fsync boundary. Restart + replay checks passed with exactly one genesis and no duplicate completed event in the fixed oracle.
- Ambiguous complete JSON without final newline, missing/corrupt/unanchored checkpoint, chain corruption, non-matching projection, or checkpoint lag greater than one event remain fail-closed. No automatic best-guess repair is attempted.
- Evidence: `evidence/HG2-P0A-ATOMIC-STATE-RECOVERY-20261019/closure-report.md`; manifest verification by `sha256sum -c` passed. Full regression log SHA-256: `de50366c49a8e4b193ee833331538a0ae3ef0747f1aaee185b574f42a16c63a9`.
- This is injected process-crash evidence, not a physical power-cut/OEM/filesystem certification. M2 semantic recall, M4 freshness/consolidation, production restore rehearsal and independent human review remain open; overall MRAF acceptance is still FAIL.
