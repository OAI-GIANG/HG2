# HG2 Four-Source Provenance and License Review

Date: 2026-10-14
Scope: identify exact upstream source revisions for the four supplied ZIP archives and record license/reuse limits. Archive members were read in place; no archive was extracted and no archive code or dependency was executed.

## Method

1. Read the 40-character SHA-1 in each ZIP file comment as a commit candidate; do not infer a source revision from archive filename or branch tip.
2. Resolve that exact SHA through the GitHub commit API and record the immutable commit/tree identity and commit date.
3. Fetch the recursive Git tree for the exact tree SHA. The verifier rejects truncated API tree results.
4. Compare every archive member's relative path and computed Git blob SHA-1 against the immutable tree.
5. Allow missing paths only when they are matched by export-ignore rules in the archived .gitattributes. For each file read, Python zipfile performs CRC validation.
6. Compute SHA-256 over the original ZIP bytes separately.

Reproducible verifier: docs/evidence/scripts/verify_hg2_source_archive_provenance.py
Machine-readable result: docs/evidence/HG2_SOURCE_PROVENANCE_RESULT_20261014.json
Captured output: docs/evidence/HG2_SOURCE_PROVENANCE_VERIFICATION_LOG_20261014.txt

## Exact source identity results

| Archive | SHA-256 | Bytes | ZIP entries | Upstream repository | Immutable commit | Tree SHA-1 | Files included / tracked blobs | Result |
|---|---|---:|---:|---|---|---|---:|---|
| codebase-memory-mcp-main.zip | 9f537d98fdcc1e6e9f5b9f834cc49ca8c097dc130bc88a83c4b2f5b9e3ef35c4 | 105632497 | 4113 | https://github.com/DeusData/codebase-memory-mcp | bb636d1ff7a47f70bccfc6d6e5d0e43e92ce7a0c | 3c9cfb82f2125bf0ebe32d2a0c6485272bee91ce | 3537 / 3537 | PASS |
| awesome-mcp-servers-3-main.zip | a2f620afa4e41dc33689c3cef9d46fd17fb9fe7cdaf7bc18bed33a82197d7b78 | 506644 | 14 | https://github.com/appcypher/awesome-mcp-servers | 70acc2194806cd47878737bb41a958f6958b388c | 76ee292e2fa651083c65a6f7f23bd924e463ab40 | 11 / 11 | PASS |
| public-apis-master.zip | e4cfb5a7593bcde80448c72f4cab7d1366bc87bc16a19e9f32732f805d202127 | 17269 | 16 | https://github.com/public-apis/public-apis | 73035eafdb7e15a078afb7d8b8487f53d5104e9a | d4ab700098d9417c77d490b79a861e09d5352d01 | 12 / 23 | PASS — export-ignore exclusions |
| myopenvdp-master.zip | 964b23fc6e87bbf48cb178e732270984380583ee1e88c9d0f182c6e28aa40f45 | 724344 | 183 | https://github.com/yeswehack/myopenvdp | 03e90e225cb8aee90bd36c5684b97b5298dcbbbb | 13a0c8cbd312feb11d21aaec2025f14d709428e8 | 141 / 141 | PASS |

The commit dates returned by GitHub are:
- Codebase Memory: 2026-10-13T16:33:21Z.
- Awesome MCP Servers: 2026-05-27T05:34:54Z.
- Public APIs: 2026-10-13T04:59:15Z.
- MyOpenVDP: 2024-06-04T10:20:00Z.

For Codebase Memory, Awesome MCP Servers and MyOpenVDP, all archive paths and Git blob IDs match the immutable commit tree. For Public APIs, all 12 included file paths and blob IDs match the commit tree; the remaining 11 tracked paths are explained by export-ignore rules.

## Public APIs export-ignore analysis

The archived .gitattributes file contains these export-ignore rules: /.github, /build, .travis.yml, and README.md. The 11 paths omitted from the commit tree are exactly nine paths under .github plus README.md and scripts/README.md. Both README paths match README.md; the .github paths match /.github. There are no unexplained missing paths, extra paths, or blob mismatches.

Therefore, the absence of the README/catalog in this ZIP is explained by the repository's export-ignore configuration. It is not evidence that the archive points to the wrong upstream commit or tree. This archive represents the commit's Git-archive export, not a full checkout containing export-ignored files.

## License and reuse disposition

1. Codebase Memory: the root license identifies MIT, while THIRD_PARTY.md and vendored component notices describe multiple third-party licenses. The component-by-component license closure has not been exhaustively audited into a separate SBOM/legal matrix. No implementation, grammar, binary, dependency, or license text from this archive was copied into the HG2 candidate. Any future reuse of components requires a component-specific notice/compatibility review.
2. Awesome MCP Servers: the root license identifies MIT and credits Frank Fiegel / Glama. The archive is used only as a pointer catalogue; no listed server was installed or copied.
3. Public APIs: the root license identifies MIT. The archive is a verified Git-archive export with its declared exclusions; no scripts or dependencies were run or installed.
4. MyOpenVDP: the root license identifies MIT and credits the YesWeHack project. Its code and configuration are excluded; no SMTP settings, key material, certificates, frontend/backend packages, or uploads were reused.

The Code Intelligence candidate is independently authored standard-library Python. No upstream implementation or dependency from these four archives was copied into the candidate. The incomplete Codebase Memory third-party license closure remains a documented limitation for any future reuse, but it is not an unresolved source-commit provenance blocker for the current clean-room candidate.

## Conclusion

- Original archive SHA-256: PASS for all four.
- ZIP member CRC: PASS for all files read by the verifier.
- Exact immutable source commit/tree identity: PASS for all four.
- Archive path/blob correspondence: PASS for all four, with Public APIs export-ignore exclusions explicitly explained.
- Unexplained missing files or blob mismatches: none.
- Overall source-provenance disposition: SOURCE_PROVENANCE_VERIFIED.
- This result is not a claim of overall product acceptance and does not authorize merge, deploy, or canonical-ref mutation. PR #15 remains OPEN/DRAFT under the current instruction.
