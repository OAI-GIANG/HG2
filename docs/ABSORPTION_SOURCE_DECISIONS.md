# HG2 Free Absorption — Source Decision Record

Date: 2026-10-14
Canonical base: `d11e71ed8b34338b8568664b39bc777c926826d5`
Policy: evidence-first; clean-room adaptation; no third-party code copied.

## Archive inventory (read directly from the supplied Android Download files)

| Archive | Bytes | SHA-256 | ZIP entries | Uncompressed bytes | CRC | Root license indicator | Decision |
|---|---:|---|---:|---:|---|---|---|
| `codebase-memory-mcp-main.zip` | 105,632,497 | `9f537d98fdcc1e6e9f5b9f834cc49ca8c097dc130bc88a83c4b2f5b9e3ef35c4` | 4,113 | 1,418,692,476 | PASS | MIT root `LICENSE`; `THIRD_PARTY.md` records many vendored grammars/components with different license terms | ABSORB DESIGN, not code |
| `awesome-mcp-servers-3-main.zip` | 506,644 | `a2f620afa4e41dc33689c3cef9d46fd17fb9fe7cdaf7bc18bed33a82197d7b78` | 14 | 1,817,136 | PASS | MIT root `LICENSE` | KEEP as reference catalog |
| `public-apis-master.zip` | 17,269 | `e4cfb5a7593bcde80448c72f4cab7d1366bc87bc16a19e9f32732f805d202127` | 16 | 53,072 | PASS | MIT root `LICENSE` | DISCARD for current absorption |
| `myopenvdp-master.zip` | 724,344 | `964b23fc6e87bbf48cb178e732270984380583ee1e88c9d0f182c6e28aa40f45` | 183 | 1,180,692 | PASS | MIT root `LICENSE`; app-specific dependency manifests exist | DISCARD from HG2 core |

Archive hashes and CRC results were calculated in-place with Python's standard-library `hashlib` and `zipfile`; archive code was not executed and files were not extracted. SHA-256 identifies these local archive bytes. Exact upstream commit-to-archive equivalence was not verified; source revision/authenticity status remains UNKNOWN. No public network/API was used for that comparison.

## Source-specific findings

### Codebase Memory

Observed in `README.md`, `THIRD_PARTY.md`, `docs/INDEX_RESOURCE_LIMITS.md`, `docs/CONFIGURATION.md`, and top-level file inventory:

- Describes indexing, Python/other-language parsing, knowledge graph, architecture/search/impact/coverage/dead-code queries and optional graph UI.
- Archive contains vendored tree-sitter runtime and many grammar sources; root README claims multiple platform releases and lists macOS/Linux/Windows but not Android/Termux. Android compatibility is UNKNOWN.
- Archive unpacks to about 1.42 GB. Its install path may alter agent configuration, and UI/agent hook surfaces add scope beyond a read-only analyzer.
- License root indicates MIT, but `THIRD_PARTY.md` describes component-specific licenses. Complete dependency/license compliance review is not done.
- Absorbed: concepts only—bounded source index, local import graph, coverage disclosure, impact candidates, provenance, staleness and reproducibility.
- Not absorbed: native binary, vendored grammars, MCP server, daemon/UI, installer, agent configuration writes, hooks, local-model features or dependencies.

### Awesome MCP Servers

Observed README states this is a curated catalog of MCP servers. Archive has only 14 entries, mainly README translations, one English catalogue, license and contribution material. It is useful as a lookup source, not a runtime capability. Keep reference-only; evaluate each server separately only if a future evidenced gap requires it.

### Public APIs

Archive has 16 entries and no `README.md` or populated API catalog. It contains CONTRIBUTING instructions, validation scripts/tests, and `scripts/requirements.txt`; link validation imports `requests` and could touch the network if run. No script or dependency was run/installed. Because the advertised data catalog is absent from this archive, no capability is absorbed.

### MyOpenVDP

README/license and frontend/backend package manifests identify a standalone VDP disclosure web app. It requires SMTP config and PGP public keys and contains a Traefik certificate/private-key-shaped fixture in the archive. Fixture contents were not displayed or validated as active credentials. The app adds external report intake, file uploads, SMTP and web exposure. No such HG2 requirement is evidenced; no code, key, certificate, SMTP config, frontend or backend is reused.

## Canonical capability evidence

At exact canonical commit `d11e71ed8b34338b8568664b39bc777c926826d5`, read-only `git ls-tree -r` reported:

- `README.md`
- `contract/ARCHITECTURE_V1.md`
- `hg/__init__.py`, `hg/authority.py`, `hg/edge.py`, `hg/history.py`, `hg/identity.py`, `hg/phone_runtime.py`
- `manifest.json`
- `tests/test_core.py`

The canonical README and `contract/ARCHITECTURE_V1.md` describe a phone-primary single runtime and an edge relay. `manifest.json` says Python >=3.10, `dependencies: {}`, and `standard library only`. The canonical tree contains no repository index, source dependency graph, code coverage model, or patch-impact analyzer. That is a verified absence from this tree; production need/impact must still be decided from the scoped feature request and not inferred from absence alone.

## Outcome

The selected implementation is a clean-room developer-side candidate in `tools/hg_code_intelligence.py`, covered by `tests/test_code_intelligence.py`. It reads Python files only, never executes them, emits hashes/relative paths/typed coverage and local import edges, and marks non-Python/dynamic-import/parse-error conditions incomplete. It is not wired into the phone runtime. The root MIT license indicators and upstream provenance do not authorize any third-party code reuse; this candidate contains no copied source code or added package dependency.

## Open risks and residual limitations

- Exact upstream revisions for all four archives remain UNKNOWN.
- Codebase Memory third-party license scopes have not received a complete legal/compliance audit; no code is reused.
- Android compatibility of Codebase Memory's native engine is UNKNOWN and not needed by this candidate.
- The candidate graph is Python-only and not a complete impact oracle. It must not be used to claim production safety or replace tests/review.
- Benchmark against ground truth on representative repositories is still required before proposing merge or release.
