# HG Selective Absorption V2 — Verified Reference Pack
Status: REFERENCE-ONLY / NOT MERGED INTO HG
Canonical target: OAI-GIANG/HG2, branch hg-genesis, commit d11e71ed8b34338b8568664b39bc777c926826d5.
Generated: 2026-10-13
Policy: MTC-1.0; evidence-first; fail-closed; zero unauthorized change; provenance required.

## Decision
Absorb only the verified engineering principles below as reference guidance. Do not copy third-party implementation code. No implementation patch is justified because no genuine HG capability gap has been demonstrated. All unverified archive identities/revisions/license claims are excluded from implementation eligibility.

## Verified archive identity and inspected material

### Skills archive
- Local archive: skills-main.zip
- SHA-256: 7dc3a809672560304a662310fb619b848ac8684c564ad528d0bfde8d064a6855
- Archive integrity: ZIP read/CRC check succeeded in the prior inventory.
- Metadata: package identifies mattpocock/skills and declares MIT. Upstream commit corresponding to this archive is UNKNOWN; therefore source-to-archive equivalence is NOT VERIFIED.
- Inspected: skills/engineering/code-review/SKILL.md; skills/engineering/tdd/SKILL.md; skills/engineering/domain-modeling/ADR-FORMAT.md.
- Accepted as reference only: review checklist, test-first workflow, explicit architecture decision records.
- Implementation: none.

### REA archive
- Local archive: rea-main.zip
- SHA-256: f08a0801fc8a789c510844a73fec538110b6d85893f85d0044c4ca1fa0db065f
- Metadata: package identifies morluto/rea and declares MIT. Upstream commit corresponding to this archive is UNKNOWN; source-to-archive equivalence is NOT VERIFIED.
- Inspected: src/contracts/toolEffects.ts; src/server/admittedToolOperation.ts; src/server/analysisAdmission.ts; src/server/recordDerivedEvidence.ts; src/contracts/toolContractTypes.ts; src/server/contractToolHandler.ts; src/process/ExecFileOutput.ts.
- Accepted as reference only: explicit side-effect declarations; operation admission; cancellation/timeout and output limits; derived-evidence provenance.
- HG guardrail: first compare these concepts against existing authority, runtime, history and state paths. Reuse existing mechanisms if adequate; no parallel engine.

### Jacobian archive
- Local archive: jacobian-main.zip
- SHA-256: 452d85b77433677ea8cc1e0eae8495003b757fd42c5df522d8bf6d7a70329d2b
- Metadata: package identifies morluto/jacobian and declares MIT. Upstream commit corresponding to this archive is UNKNOWN; source-to-archive equivalence is NOT VERIFIED.
- Inspected: src/jacobian/mcp/models.py; src/jacobian/mcp/tools.py; src/jacobian/mcp/remote.py; tests/mcp/test_remote_mcp_auth.py; tests/mcp/test_mcp_catalog_and_policy.py. Tests were not executed.
- Decision: excluded from active HG absorption until a concrete math use case and acceptance tests are demonstrated.

### ArtCraft Services archive
- Local archive: artcraft-services-main.zip
- SHA-256: d51adcdca28bba540e071cffbd734e3ea4c6f8a21bc9646593a53c1df94065eb
- Archive: 20,842 entries; 1,016,395,055 bytes uncompressed. No .git metadata; exact source commit UNKNOWN.
- Root license is titled "ArtCraft License (WIP)". No code reuse authorized.
- Static security findings retained as risk lessons only; not runtime-confirmed:
  1. User-controlled URL download flow may permit SSRF unless protected by controls outside inspected functions.
  2. Download response is materialized in memory before size is enforced; resource exhaustion risk.
  3. Some webhook handlers contain TODO/paths where authentication is not evidenced at handler level; outer middleware/gateway not fully verified.
  4. Credential-shaped values exist in archive configuration; validity was not tested and values are intentionally not reproduced.
  5. Some handlers log raw payloads/request data; exposure depends on log access and upstream redaction.
  6. Image/video idempotency sequencing differs and may cause duplicate ingestion work; duplicate billing was not proven.
- Decision: security lessons may inform threat-model reviews. Exclude code, dependency, runtime, and service integration.

## Absorbed reference principles for HG (no code changes)
1. For each operation, document authority, scope, side effects, resource bounds, timeout/cancellation and failure semantics.
2. Record provenance for derived evidence and bind claims to exact input/source revision.
3. Use code review, test-first workflow and ADRs for future authorized changes.
4. Add counterexample tests only for a demonstrated requirement: unauthorized action, malformed input, timeout/cancellation, resource limit, retry/idempotency, invalid provenance.
5. Use existing HG authority/runtime/history/state mechanisms where adequate. Do not create duplicate subsystems.
6. Treat hash verification, static review, test execution, semantic correctness and independent review as distinct evidence classes.

## Capability Gap Ledger
- Authority/operation side-effect contract: UNKNOWN; inspect all relevant operation paths before asserting a gap.
- Hash-chain/history integrity: existing hg/history.py has append-only hash-chain, sequence, checkpoint and verify; atomicity/completeness across every path remains UNKNOWN.
- Edge request controls: hg/edge.py evidence previously read includes Bearer auth, 8192-byte body limit, JSON/device-ID validation; full network/egress policy remains UNKNOWN.
- Cancellation/resource limits across all HG operations: UNKNOWN.
- Specialized math, media, PDF/Word and reverse-engineering capabilities: no concrete unmet HG requirement demonstrated.
- Current decision: NO PATCH JUSTIFIED.

## Three gates
G1 SOURCE EVIDENCE: not fully passed. Archive hashes are known; exact upstream commit-to-archive matching is not verified. ArtCraft Services license is WIP.
G2 VERIFIED CAPABILITY GAP: not passed. No GENUINE-GAP demonstrated with requirement + exact HG code evidence + consequence + minimal remedy.
G3 BENEFIT/RISK AND ACCEPTANCE: not opened for implementation because G2 has not passed.

## Explicitly excluded from active absorption
The following archive contents are not approved for code reuse or implementation by this reference pack: designcraft-main.zip, awesome-reverse-engineering-main.zip, artcraft-main.zip, photocraft-main.zip, artcraftx-main.zip, lightcraft-main.zip, filmcraft-main.zip, pdfcraft-main.zip, wordcraft-main.zip. They may be reconsidered only after exact source/revision/license verification and a demonstrated HG use case. Their prior local archive hashes remain inventory identifiers only, not provenance proof.

## Change and verification status
- No source code copied from third-party projects.
- No HG source code changed.
- No dependencies installed; no backend or production API called.
- No tests run for this reference pack.
- No independent review claimed.
- The initial GitHub integration branch-creation request was denied (HTTP 403 Resource not accessible by integration). The document was subsequently committed and pushed from authorized Termux Git CLI to the isolated reference branch; it has NOT been merged into canonical.
- Canonical `hg-genesis` was independently compared before and after the push and remained at d11e71ed8b34338b8568664b39bc777c926826d5 at the time of verification.

## Acceptance / rollback / stop
Accept only as a local reference document. Do not merge or treat as product implementation. Stop any code reuse if license/provenance remains unclear or if G2 cannot prove a genuine gap. Rollback is simply discard this local document; no canonical rollback is needed because no repository mutation occurred.
