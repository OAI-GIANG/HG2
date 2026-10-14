# HG2 Absorption — Evidence Closure and Design Gate Report

Date: 2026-10-14
Candidate branch: `feature/hg2-code-intelligence-absorb-20261014`
Exact base: `d11e71ed8b34338b8568664b39bc777c926826d5`
Candidate status: IMPLEMENTED IN ISOLATED WORKTREE / LOCAL TESTS PASS / MERGE-DEPLOY HOLD
Canonical baseline and release status: unchanged.

## 1. Executive decision

This task produced a bounded clean-room code-intelligence candidate and an evidence record for all four supplied archives. It did not install or integrate the external engine, install dependencies, or deploy a runtime capability.

- Codebase Memory: selectively absorb design principles only. The clean-room candidate implements Python static import indexing, a limited import graph, known reverse-dependency impact candidates, coverage disclosure, staleness detection, and deterministic digests.
- Awesome MCP Servers: keep as a reference catalog only.
- Public APIs: discard for this absorption because this archive contains no actual API catalog.
- MyOpenVDP: discard from HG2 core because no VDP requirement is evidenced and it adds a web intake/SMTP/PGP/file-upload surface.

The implementation is isolated under `tools/`; it is not listed in `manifest.json`. Phone runtime, `hg/authority.py`, `hg/history.py`, identity and edge paths are untouched. No third-party implementation code or dependency was copied/added.

## 2. Source archive inventory

The four archives were read in-place on the authorized Android/Termux device using Python standard-library `hashlib` and `zipfile`. SHA-256 and CRC checks were calculated locally; code in the ZIPs was not executed and archives were not extracted. Hashes identify the local archive bytes only. Exact upstream commit/tree provenance remains UNKNOWN.

| Archive | Bytes | SHA-256 | Entries | Uncompressed bytes | CRC | License indicator | Decision |
|---|---:|---|---:|---:|---|---|---|
| `codebase-memory-mcp-main.zip` | 105,632,497 | `9f537d98fdcc1e6e9f5b9f834cc49ca8c097dc130bc88a83c4b2f5b9e3ef35c4` | 4,113 | 1,418,692,476 | PASS | MIT root LICENSE; THIRD_PARTY.md describes numerous vendored components with distinct license terms | ABSORB DESIGN only |
| `awesome-mcp-servers-3-main.zip` | 506,644 | `a2f620afa4e41dc33689c3cef9d46fd17fb9fe7cdaf7bc18bed33a82197d7b78` | 14 | 1,817,136 | PASS | MIT root LICENSE | KEEP reference-only |
| `public-apis-master.zip` | 17,269 | `e4cfb5a7593bcde80448c72f4cab7d1366bc87bc16a19e9f32732f805d202127` | 16 | 53,072 | PASS | MIT root LICENSE | DISCARD for current absorption |
| `myopenvdp-master.zip` | 724,344 | `964b23fc6e87bbf48cb178e732270984380583ee1e88c9d0f182c6e28aa40f45` | 183 | 1,180,692 | PASS | MIT root LICENSE; app dependency manifests | DISCARD from HG2 core |

### Source-specific findings

**Codebase Memory.** The README describes indexing, code graphs, architecture/search/impact/coverage/dead-code queries and optional graph UI. The archive unpacks to about 1.42 GB and vendors Tree-sitter runtime/grammars with per-component license obligations. Installation can change agent configuration and additional hooks/UI extend the scope. Its documented native platforms are macOS/Linux/Windows; Android/Termux compatibility is UNKNOWN. No source implementation was copied.

**Awesome MCP Servers.** The archive is a catalogue of MCP servers, not a single runtime. Keep it as a lookup reference; each server requires its own gap, security, dependency and license review before any future adoption.

**Public APIs.** The supplied archive contains no README or populated API catalog; it has contributing material, validation scripts/tests and requirements. Link validation could contact the network if run, but it was not run. The archive therefore adds no evidenced HG2 capability.

**MyOpenVDP.** The README describes a standalone disclosure web application requiring SMTP config and PGP public keys, with front-end/back-end, upload and captcha surfaces. Certificate/private-key-shaped fixtures exist in the archive; they were not displayed or validated as active credentials. There is no demonstrated HG2 requirement for VDP intake. No VDP code or configuration was reused.

## 3. Canonical baseline evidence

Read-only `git ls-tree -r` at exact canonical commit `d11e71ed8b34338b8568664b39bc777c926826d5` returned:

- `README.md`
- `contract/ARCHITECTURE_V1.md`
- `hg/__init__.py`
- `hg/authority.py`
- `hg/edge.py`
- `hg/history.py`
- `hg/identity.py`
- `hg/phone_runtime.py`
- `manifest.json`
- `tests/test_core.py`

Canonical `manifest.json` specifies Python >=3.10, an empty dependency object, and standard library only. The canonical README/architecture contract describes a phone-primary runtime and edge relay. There is no repository index, source dependency graph, code coverage model or patch-impact analyzer in that exact tree.

This verifies absence from that tree; it does not by itself prove a production need. The candidate is a separate opt-in developer-side tool and is not wired into HG runtime.

## 4. Candidate implementation and contract

Files added on isolated branch:

- `tools/hg_code_intelligence.py`
- `tests/test_code_intelligence.py`
- `contract/CODE_INTELLIGENCE_V1.md`
- `docs/HG_CODE_INTELLIGENCE_USAGE.md`
- `docs/ABSORPTION_SOURCE_DECISIONS.md`
- `docs/ABSORPTION_GATE_REPORT.md`

The implementation is clean-room Python standard-library code. It:

1. Parses Python import statements with AST without executing repository code.
2. Resolves exact local Python module names into an explicitly limited static graph.
3. Reports known reverse dependents for changed paths.
4. Recognizes a bounded set of code/configuration source files, hashes all recognized source contents, and marks non-Python files as unsupported rather than pretending to analyze them.
5. Marks impact incomplete if there are unsupported source files, dynamic import sites, parse errors or resource skips.
6. Detects stale indexes by comparing source revision, snapshot hash and analyzer version.
7. Enforces file-count/source-byte limits, avoids following symlinks, excludes secret-shaped paths, rejects path traversal, and returns no partial report on hard resource-limit failures.
8. Labels the source revision as caller-declared and unverified, and does not disclose source contents or absolute repository paths in the report.

It does not perform a full multi-language graph, semantic call graph, data-flow analysis or runtime behavior proof. No dependency was added. The candidate is not in the canonical manifest and is not imported by phone runtime.

## 5. Verification results

Environment: Android/ARM64, Termux, Python 3.14.6. Results apply only to this isolated worktree/environment.

| Check | Result | Interpretation |
|---|---|---|
| Candidate-specific unit suite | PASS — 17 tests | Includes path traversal, non-execution, symlink and secret exclusion, resource caps, parsing errors, graph/impact, dynamic imports and aliases, dotfile paths, reproducibility/staleness including changed unsupported source bytes. |
| Full repository suite | PASS — 29 tests | Baseline and candidate tests passed. Existing ResourceWarnings originate in unmodified `tests/test_core.py`. |
| CLI smoke on candidate tree | PASS | 10 recognized source files; 9 Python files parsed; 1 non-Python file flagged unsupported. Coverage correctly reported incomplete. Two known local dependents were found for changed `hg/history.py`, with incomplete-impact status. This is only a smoke test. |
| Smoke snapshot SHA-256 | `3ec5e3f760301eff158063130519b14ccf91b6be2f5816df9ec6eb574ccf7497` | Revision label was `candidate-worktree-uncommitted`; not an authenticated source identity. Digest included recognized non-Python source bytes. |
| Smoke report SHA-256 | `a0c08b444ef8c1cc82dd7829536f6bcd59f3643674d44739f20b714c0a903f4d` | Report was written outside the analyzed repository. |
| Runtime integration | NOT DONE | Deliberately not imported by phone runtime or added to manifest. |
| Representative impact benchmark | NOT RUN | No frozen ground-truth corpus/registered thresholds for broad code intelligence exists yet. |
| Upstream commit/tree equivalence | UNKNOWN | Local ZIP hashes/CRC are verified; exact upstream revision equivalence was not checked. |
| License compliance for upstream code reuse | UNKNOWN / NOT APPLICABLE to current clean-room code | No third-party code or package is reused. Full component-level legal review is incomplete. |

Coverage-complete refers only to all recognized files within this bounded analyzer being supported/parsed. It does not prove complete runtime dependency coverage or full multi-language analysis.

## 6. Gap register closure state

| Gap | Result | Rationale |
|---|---|---|
| GAP-01 repository indexing | Capability absent from exact baseline tree; candidate exists | Product-impact benchmark still needed. |
| GAP-02 code dependency graph | No graph engine in baseline tree; candidate provides Python static-import graph only | Not a general semantic/dependency graph. |
| GAP-03 coverage/provenance | Candidate reports per-file status, hashes and explicit incomplete coverage | Must be validated against representative repositories. |
| GAP-04 patch impact | Candidate reports known reverse Python import dependents | Cannot claim complete patch impact; unsupported languages/dynamic imports force incomplete status. |
| GAP-05 evidence/uncertainty | Candidate labels inferred edges and caller-declared revision; unsupported files are explicit | Semantic trust of source and runtime behavior remain out of scope. |
| GAP-06 staleness/reproducibility | Snapshot digest includes hashes of all recognized source/config files; stale comparison is tested | Caller revision is not authenticated; filesystem changes during scan are not transactionally snapshotted. |
| GAP-07 counterexample/impact validation | Not implemented as a general engine; safety counterexamples exist in unit suite | HOLD for a future ground-truth benchmark; do not claim counterexample completeness. |

No broad product-performance gap is treated as release-certified. The code-indexing absence itself is verified in the baseline tree, but the broader quality/utility gates remain held.

## 7. Remaining gates and release decision

| Gate | Status | Closure condition |
|---|---|---|
| Local archive integrity | PASS | SHA-256 and ZIP CRC checked for all four supplied archives. |
| Exact upstream archive revision | UNKNOWN | A future source-reuse review needs exact revision/tree evidence. |
| Candidate unit correctness | PASS | 29/29 unit suite on isolated worktree. |
| Representative coverage/impact quality | HOLD | Freeze ground-truth repositories including local imports, dynamic imports, unsupported languages and expected impacts; preregister measurable thresholds, then evaluate. |
| Runtime compatibility of Codebase Memory engine | UNKNOWN | Not applicable to current standard-library-only candidate; upstream engine remains excluded. |
| Production / release readiness | HOLD / NOT RELEASE-READY | Requires representative benchmark, accepted residual risks and a separately authorized integration decision. |

## 8. Final disposition

`ABSORPTION CANDIDATE CREATED / LOCAL TESTS PASS / EVIDENCE RECORDED / CANONICAL UNCHANGED / MERGE-DEPLOY HOLD`.

This closes the source-selection and candidate-construction phase. It does not certify general code intelligence or authorize merge/deployment. The canonical `hg-genesis` ref remains at `d11e71ed8b34338b8568664b39bc777c926826d5` in the inspected local repository.


## Final evidence correction — 2026-10-14

This addendum supersedes earlier statements in this report that upstream provenance was UNKNOWN and that representative benchmarks were still unrun. The four archive commit/tree/blob comparisons are now verified in docs/evidence/HG2_SOURCE_PROVENANCE_RESULT_20261014.json; the bounded real-repository benchmark V2 passed 2/2 pinned repositories and synthetic benchmark V2 passed 8/8 cases. The full current regression suite passed 35 tests, and CircleCI run #95 passed on final evidence HEAD 9966be2556b76bd10bc52d0742053ffe14106b59.

The benchmark evidence remains deliberately limited: the V1 real-repository run failed and is preserved as failed; V2's expected edges were manually re-audited after that failure; broad multi-language, semantic, runtime, and repository-wide impact completeness are not established. No upstream code or dependency was copied. See docs/evidence/HG2_FOUR_SOURCE_ABSORPTION_CLOSURE_20261014.md for the authoritative scoped closure decision.
