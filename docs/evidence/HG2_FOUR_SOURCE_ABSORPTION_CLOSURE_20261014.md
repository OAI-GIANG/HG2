# HG2 Four-Source Absorption — Scoped Closure Record

Date: 2026-10-14
Repository: OAI-GIANG/HG2
PR: https://github.com/OAI-GIANG/HG2/pull/15
Branch: fix/hg2-code-intelligence-coverage-failclosed-20261014
Pre-closure HEAD inspected: 9966be2556b76bd10bc52d0742053ffe14106b59
Pre-closure tree: 13466929238992c3eeb8b8e67c45c16fad5131f6

## 1. Decision

**CLOSED — FOUR-SOURCE INVESTIGATION, PROVENANCE, DISPOSITION, AND SELECTIVE DESIGN-ABSORPTION SCOPE.**

**NOT CLOSED / NOT CLAIMED — upstream-code reuse, full multi-language code intelligence, phone-runtime integration, product/release acceptance, merge, or deployment.**

This is the evidence-based closure of the requested four-archive absorption task as a selective adoption task: inspect and authenticate all four sources, choose an explicit disposition for each, implement the safe relevant design principles in an isolated clean-room candidate, and verify the bounded behavior. It is not a claim that all four upstream projects were copied into HG2 or that every feature advertised by them is implemented. Three sources were deliberately not selected for runtime/code integration; that is a documented disposition, not an unfinished copy operation.

## 2. Source-by-source acceptance

| Archive | Immutable provenance | Final disposition | Acceptance |
|---|---|---|---|
| codebase-memory-mcp-main.zip | DeusData/codebase-memory-mcp, commit bb636d1ff7a47f70bccfc6d6e5d0e43e92ce7a0c, tree 3c9cfb82f2125bf0ebe32d2a0c6485272bee91ce; 3537/3537 included paths/blobs match | **ABSORB DESIGN ONLY** through independently authored Python static source indexing, bounded import graph, impact candidates, coverage disclosure, staleness and deterministic digests | PASS within bounded contract |
| awesome-mcp-servers-3-main.zip | appcypher/awesome-mcp-servers, commit 70acc2194806cd47878737bb41a958f6958b388c, tree 76ee292e2fa651083c65a6f7f23bd924e463ab40; 11/11 match | **KEEP REFERENCE-ONLY**; not a runtime product | PASS — disposition recorded |
| public-apis-master.zip | public-apis/public-apis, commit 73035eafdb7e15a078afb7d8b8487f53d5104e9a, tree d4ab700098d9417c77d490b79a861e09d5352d01; 12/23 included, remaining 11 exactly explained by upstream export-ignore rules | **DISCARD FROM CURRENT SCOPE**; archive lacks the advertised populated API catalog | PASS — disposition recorded |
| myopenvdp-master.zip | yeswehack/myopenvdp, commit 03e90e225cb8aee90bd36c5684b97b5298dcbbbb, tree 13a0c8cbd312feb11d21aaec2025f14d709428e8; 141/141 match | **DISCARD FROM HG2 CORE**; no evidenced VDP requirement and adds web intake/upload/SMTP/PGP surface | PASS — disposition recorded |

Archive byte SHA-256, CRC, exact commit/tree and blob-level results are recorded in:
- docs/evidence/HG2_SOURCE_PROVENANCE_RESULT_20261014.json
- docs/evidence/HG2_SOURCE_PROVENANCE_VERIFICATION_LOG_20261014.txt
- docs/evidence/HG2_SOURCE_PROVENANCE_LICENSE_AUDIT.md
- docs/evidence/HG2_SOURCE_PROVENANCE_RECEIPT_20261014.json
- verifier: docs/evidence/scripts/verify_hg2_source_archive_provenance.py

Verifier outcome: PASS_ALL_FOUR_ARCHIVES_PROVEN_TO_EXACT_COMMIT_CONTENT. It reads archive members in place; no archive code was executed or extracted.

## 3. Implemented and tested in the isolated candidate

The candidate includes tools/hg_code_intelligence.py, its contract and usage documentation, test suite, fixtures, and benchmark tooling. Its bounded capabilities are:
- parse Python imports without executing repository code;
- build a limited static local import graph and identify known reverse dependents;
- hash recognized source/config files and report typed coverage/incompleteness;
- explicitly flag unsupported files, dynamic imports, parse errors, resource skips and incomplete impact;
- detect staleness from revision/snapshot/analyzer metadata;
- enforce resource and path controls, avoid symlinks, and exclude secret-shaped paths.

Verification at final evidence HEAD:
- Full regression: PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests — **35 tests passed**, exit 0. Existing ResourceWarning messages were emitted by legacy test paths; they did not fail the suite.
- Synthetic preregistered benchmark V2: **8/8 pass**.
- Real-repository benchmark V2: **2/2 pinned repositories pass** all registered thresholds.
- Real-repository benchmark V1: **failed 2/2 exact-edge checks**, preserved unchanged and not counted as a pass.
- Hosted CI: CircleCI run #95 on 9966be2556b76bd10bc52d0742053ffe14106b59 — **SUCCESS**.
- Provenance verifier rerun on device — **PASS for all four archives**.
- manifest.json SHA-256 remains 748649af5d45e10d7df322e430aa01240a6f303c5f2bcb6a363aa5cf8c221abf; canonical diff remains empty.

## 4. Explicit residual limits

1. The candidate is a clean-room design absorption, not reuse of Codebase Memory source, binaries, grammars, dependencies, MCP server, daemon, UI, or installer.
2. The Codebase Memory third-party component license closure is not exhaustive. Since no upstream implementation or dependency was copied, this remains a future-reuse limitation, not a blocker to this clean-room candidate.
3. The analyzer is Python-only and static. The real-repository benchmark establishes only the bounded import/known-impact contract on two pinned repositories. It does not prove full repository coverage, semantic/data-flow analysis, runtime call graphs, all-language support, or complete impact.
4. The tool remains isolated under tools/, is not listed in the canonical manifest.json, and is not imported by phone runtime. Runtime integration and release readiness were not requested by the accepted selective scope and remain separate work.
5. PR #15 remains OPEN/DRAFT. No merge, deployment, release, canonical-ref mutation, or manifest change occurred.

## 5. Acceptance gate

| Criterion | Result |
|---|---|
| Four archives individually identified and dispositioned | PASS |
| SHA-256/ZIP CRC integrity | PASS |
| Exact upstream commit/tree and included blob correspondence | PASS |
| Public APIs export-ignore omissions explained | PASS |
| Selected Codebase Memory design principles implemented clean-room | PASS, bounded |
| Regression, synthetic benchmark, real-repository V2, hosted CI | PASS, scope-limited |
| Failed V1 benchmark retained transparently | PASS |
| No third-party implementation/dependency copied | PASS |
| Canonical manifest/ref invariant preserved | PASS |
| Independent review / independent approval requirement | NOT A GATE; no substitute gate added |
| Full upstream-feature parity / phone-runtime integration / release readiness | NOT CLAIMED; separate scope |

## 6. Final disposition

FOUR_SOURCE_INVESTIGATION_CLOSED / SOURCE_PROVENANCE_VERIFIED / SELECTIVE_DESIGN_ABSORPTION_VERIFIED_WITHIN_BOUNDED_CONTRACT / PRODUCT_INTEGRATION_NOT_CLAIMED / PR_OPEN_DRAFT.

The task can be closed under the selective absorption scope recorded here. It must not be relabeled as full functional parity with the four upstream projects or as product/release acceptance.
