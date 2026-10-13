# HG2 four-source provenance and license review

Date: 2026-10-14
Scope: inspect ZIP metadata and embedded README/license material without extracting archives or executing archive code. No source implementation from these archives is copied into HG2.

## Archive byte identity

| Local archive | SHA-256 | Byte count | ZIP entries | CRC | Intended upstream indicated by embedded metadata | Exact ZIP-to-commit identity |
|---|---|---:|---:|---|---|---|
| `codebase-memory-mcp-main.zip` | `9f537d98fdcc1e6e9f5b9f834cc49ca8c097dc130bc88a83c4b2f5b9e3ef35c4` | 105,632,497 | 4,113 | PASS | https://github.com/DeusData/codebase-memory-mcp | UNKNOWN |
| `awesome-mcp-servers-3-main.zip` | `a2f620afa4e41dc33689c3cef9d46fd17fb9fe7cdaf7bc18bed33a82197d7b78` | 506,644 | 14 | PASS | Likely https://github.com/punkpeye/awesome-mcp-servers; the archive's README/licence credit Frank Fiegel / Glama but does not encode a Git commit | UNKNOWN |
| `public-apis-master.zip` | `e4cfb5a7593bcde80448c72f4cab7d1366bc87bc16a19e9f32732f805d202127` | 17,269 | 16 | PASS | Name suggests https://github.com/public-apis/public-apis, but archive has no README or populated API catalog and therefore does not establish equivalence to that repository | UNKNOWN / CONTENT MISMATCH RISK |
| `myopenvdp-master.zip` | `964b23fc6e87bbf48cb178e732270984380583ee1e88c9d0f182c6e28aa40f45` | 724,344 | 183 | PASS | README references `yeswehack/my-open-vdp`; official repository found at https://github.com/yeswehack/myopenvdp | UNKNOWN |

A repeat SHA-256, byte-size, entry-count, uncompressed-size and `ZipFile.testzip()` pass was performed on the four files in `/storage/emulated/0/Download` after the CI repair. These values identify the actual local ZIP bytes. ZIP member listing has no `.git` history or archive-attestation record tying these exact bytes to an immutable upstream Git commit/tree. A branch name embedded in an archive filename (e.g. `-main` or `-master`) is not proof of the commit used to create the ZIP.

## Public references checked

- Codebase Memory: https://github.com/DeusData/codebase-memory-mcp — embedded README identifies this repository. Its `THIRD_PARTY.md` points to many separate Tree-sitter grammar repositories and vendored libraries.
- Awesome MCP Servers: https://github.com/punkpeye/awesome-mcp-servers — the public project owned by Frank Fiegel / Glama is consistent with the embedded README and translations; this only establishes likely project identity, not the archive commit.
- Public APIs: https://github.com/public-apis/public-apis — current public repo has a populated README/catalog, whereas the supplied ZIP has no `README.md` and only 16 entries. Do not treat this local ZIP as the official full catalog without new byte-level/source-tree evidence.
- MyOpenVDP: https://github.com/yeswehack/myopenvdp — README describes a standalone VDP application. Its own description requires SMTP configuration and PGP public keys; no such HG2 need was evidenced.
- CircleCI config validation reference: https://cli.circleci.com/reference/ — `circleci config validate` is the official local YAML/pipeline-config validation command. The local device did not have the CircleCI CLI installed; actual CircleCI hosted status was used as the config-execution proof instead.
- GitHub reviewer request guidance: https://docs.github.com/en/pull-requests/how-tos/create-pull-requests/requesting-a-pull-request-review — GitHub states requesting a review requires write access and the requested person/team must have repository read access.

## Current upstream references observed on 2026-10-14 (not source-ZIP identity)

Read-only GitHub API calls returned these branch-tip references at inspection time:

- `DeusData/codebase-memory-mcp` (`main`): `6de4a35c28646d6fb3ee0c12090b435a0d984593` (committer date `2026-10-13T19:11:14Z`).
- `punkpeye/awesome-mcp-servers` (`main`): `cc7f1f42c3fa8ced6fd5c0e02ea366ef7ed8cf1b` (committer date `2026-10-09T19:23:13Z`).
- `public-apis/public-apis` (`master`): `73035eafdb7e15a078afb7d8b8487f53d5104e9a` (committer date `2026-10-13T04:59:15Z`).
- `yeswehack/myopenvdp` (`master`): `03e90e225cb8aee90bd36c5684b97b5298dcbbbb` (committer date `2024-06-04T10:20:00Z`).

These are current/reference branch tips observed over GitHub API, not claims that any supplied archive was created from those commits. Because the archives contain no matching `.git` commit, no immutable provenance sidecar, and (in the Public APIs case) no populated catalog README, exact source revision equivalence remains UNKNOWN. To prove equivalence later, an authoritative original source commit/attestation must be supplied or the ZIP contents must be fully compared against an identified immutable tree.

## License and reuse disposition

1. **Codebase Memory** — root LICENSE says MIT, but `THIRD_PARTY.md` and vendored per-component files expose a wider set of licence terms, including MIT, Apache-2.0, CC0/public-domain-style terms, BSD variants, SQLite public domain, TRE, LZ4 and other notices. The component-by-component list is not exhaustively mapped into a separate SBOM/legal matrix for this absorption. No code, grammar, binary, dependency, or license text is copied into the candidate. A future implementation that reuses any component must first pin an exact source revision and complete a component-specific notice/compatibility review.
2. **Awesome MCP Servers** — embedded root LICENSE identifies MIT and copyright © 2024 Frank Fiegel / Glama. It is used as a pointer catalogue only; no listed server is added or installed.
3. **Public APIs** — embedded root LICENSE identifies MIT, copyright © 2022 public-apis. The supplied archive is incomplete relative to the intended catalog and is not used by HG2; no scripts/dependencies are run or installed.
4. **MyOpenVDP** — embedded root LICENSE identifies MIT, copyright by the YesWeHack project. Its code and configuration are excluded; no SMTP settings, key material, certificates, frontend/backend packages, or uploads are used.

The Code Intelligence candidate is independently authored standard-library Python; `manifest.json` remains unchanged and no package was added. Since no third-party implementation is reused, a complete legal opinion on the upstream engine is not a prerequisite for this clean-room candidate; it remains a prerequisite for any later code/dependency reuse.

## Source identity and acceptance conclusion

- Local byte integrity: PASS for all four archives.
- Intended upstream URLs: evidence supports two directly and the others as likely/hypothesized identities as marked above.
- Exact source commit/tree of each supplied ZIP: **UNKNOWN**; no surviving `.git` or immutable archive provenance proves it.
- Public APIs archive's equivalence to full official repository: **NOT ESTABLISHED**; its missing README/catalog is the explicit reason it was discarded.
- Full upstream component licence audit: **NOT COMPLETE** for Codebase Memory; not needed for this clean-room implementation because no upstream code was reused.
- No archive was extracted; no archive code or dependencies were executed.

**Release gate:** preserve UNKNOWN source revision/provenance and keep merge/deploy on HOLD. No archive identity is silently inferred from a filename.
