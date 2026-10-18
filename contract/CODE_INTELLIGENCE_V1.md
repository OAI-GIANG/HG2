# HG Code Intelligence V1 — Clean-room Contract

Status: isolated feature candidate; not merged, not production-integrated, not release-certified.
Canonical base: `d11e71ed8b34338b8568664b39bc777c926826d5`.
Dependencies: Python standard library only.

## 1. Purpose

Provide a bounded, read-only structural view of Python imports in a repository. The tool adapts selected design principles from Codebase Memory—indexing, source graph, coverage disclosure, impact query, provenance, and stale-index detection—without copying third-party implementation code or adding a runtime dependency.

## 2. Explicit non-goals

- Not a replacement for Codebase Memory or a general multi-language code intelligence engine.
- Does not execute repository code, install packages, use network/API, invoke an AI model, or mutate the analyzed repository.
- Does not claim runtime call graph, data-flow analysis, architectural truth, or a complete impact list.
- Does not connect to HG phone runtime, edge relay, authority, identity, or history.
- Does not change canonical manifest/dependencies or production behavior.

## 3. Inputs

- An existing repository root path.
- Caller-declared source revision; `UNKNOWN` is valid but is not proof of identity.
- Optional repository-relative changed paths.
- Explicit file-count, per-file byte, and total-source-byte limits.

Absolute paths are not disclosed in output. Changed paths that are absolute or contain `..` are rejected. Symlinks are not followed. The default limits are 20,000 entries, 4 MiB per Python file, and 128 MiB total Python source bytes.

## 4. Processing

1. Walk entries deterministically, pruning known generated/cache directories.
2. Exclude secret-shaped paths and key/certificate file extensions without recording their names in output.
3. Hash every recognized source/configuration file within the aggregate resource cap. Record non-Python files as `UNSUPPORTED_LANGUAGE`; these bytes contribute to the snapshot digest but not to the import graph.
4. Read only bounded `.py` files and parse with Python `ast`; no import statements are executed.
5. Record each recognized file's relative path, status, support-kind, size and SHA-256. Source contents are never copied into the report.
6. Resolve Python imports only against exact names in the repository's parsed Python module map. Resolved edges are labelled `INFERRED_LOCAL_MODULE`; unresolved/external imports are not treated as confirmed local dependencies.
7. Calculate known transitive reverse dependents for changed paths.
8. Mark coverage incomplete for syntax/encoding errors, oversize files, unsupported source languages or dynamic import sites.
9. Produce deterministic snapshot and report hashes. Changes to recognized non-Python sources must change the snapshot hash so a previous report can be detected as stale.

## 5. Evidence semantics

- `PARSED`: a source file parsed successfully with Python AST.
- `INFERRED_LOCAL_MODULE`: an import syntax site was observed and its target was mapped to a local Python file. This is a static inference, not proof of runtime execution.
- `UNRESOLVED_OR_EXTERNAL`: a syntactic import could not be resolved to a repository module.
- `STALE`: source revision, source snapshot hash or analyzer version differs between two reports.
- `CALLER_DECLARED_NOT_VERIFIED`: revision metadata was supplied by the caller; the tool did not authenticate it.

A file hash proves byte identity relative to a calculated digest, not authenticity, correctness, or licensing. Missing/unknown coverage must never be represented as complete.

## 6. Output contract

The JSON report contains schema/analyzer version, source label and caller-declared revision state, resource limits, snapshot SHA-256, coverage and limitations, file records, import edges, changed paths, known dependents, unresolved changed paths, impact status, and a report SHA-256. It does not embed source text, secrets, or absolute repository paths.

## 7. Fail-closed conditions

Return BLOCKED / raise a typed error if the root is invalid, a path escapes the root, a required revision field is empty, traversal exceeds the entry limit, aggregate source bytes exceed the cap, or any scan operation cannot safely establish its declared bounds. No partial report is published after a hard resource-limit failure.

If coverage is incomplete, impact is reported as `KNOWN_DEPENDENTS_ONLY_INCOMPLETE_COVERAGE`; if a changed path is missing or unparsed, report `UNRESOLVED_CHANGED_PATH`. The tool never labels those cases as complete impact analysis.

## 8. Acceptance criteria

- Zero repository code execution or network calls by the module.
- Zero content/absolute path disclosure in output.
- 100% of changed-path traversal attempts rejected.
- 100% of registered symlink and secret exclusion cases pass.
- Resource limit exceeded => explicit BLOCKED/error; no partial index returned.
- Identical snapshot + analyzer version + caller revision => identical snapshot/report SHA-256.
- Any source or revision identity change => stale comparison.
- Unsupported languages, parse errors and dynamic imports force incomplete coverage.
- No production wiring, dependency added, or canonical tree change.

## 9. Known limits

Only Python static imports are parsed. Dynamic import, reflection, type/call relationships, generated code, packaging/import-path configuration, language-specific resolution, and runtime behavior are not fully modeled. External dependency inference may be incomplete. A passing unit suite validates this limited contract, not broad code-intelligence quality or production fitness.
