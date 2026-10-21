# HG2 Anti-Forgetting Closure — Evidence Status

Date: 2026-10-19
Repository: OAI-GIANG/HG2
Previous base: 4ea1e4dc98355ca92ae9564c873b0f2b926fc4b2

## Verified in the Termux checkout

- Fixed synthetic memory-recall oracle: 18/18 cases passed; precision 1.000000, recall 1.000000, reciprocal rank 1.000000 for the relevant fixtures; no ACL-forbidden IDs observed.
- Unicode composed/decomposed Vietnamese queries returned the same ordered IDs.
- A synthetic record survived reopening the same canonical StateStore directory unchanged.
- Curated aliases successfully recall the known synthetic “favorite color / which hue is liked” paraphrase. This is explicit metadata, not evidence of general semantic understanding.
- Expired, missing-expiry, digest-mismatched and revoked provenance records are not included in recall when the record opts into provenance metadata.
- Context labels provenance-bearing records conservatively as UNVERIFIED unless revoked, and labels exact source/key conflicts CONFLICT_UNRESOLVED; it does not silently select a conflicting winner.
- The isolated provenance SQLite primitive rejects symlink paths, requires a private parent directory, sets the database file to mode 0600, verifies its append-only event chain and survives an isolated reopen test. It remains a non-canonical primitive; it was not wired as another runtime authority.
- Targeted regression: 36 tests passed.
- Full repository regression after this work: 300 tests passed in 36.999s, exit code 0.
- Fixed oracle was executed with no external API/model call. No package was installed.
- External references consulted: Unicode normalization FAQ, OWASP Authorization Regression Testing Cheat Sheet, NIST AI RMF Development.

## Acceptance matrix

| Gate | Result | Boundary |
|---|---|---|
| P0-A crash-window recovery from previous commit | PASS for injected process-crash windows already documented in the P0-A closure evidence | Not hardware power-cut certification |
| M2 fixed synthetic recall/ACL/Unicode/restart oracle | PASS, 18/18 | Small, synthetic, partly curated; not a human-labelled general semantic benchmark |
| M3 trust and conflict safety tests | PASS in targeted tests | Full independent authority verification is not implemented; no caller may self-promote to VERIFIED |
| Freshness enforcement for provenance-bearing records in retrieval/context | PASS in synthetic tests | Legacy records lacking provenance remain searchable for backward compatibility, clearly marked FRESHNESS_UNKNOWN and UNVERIFIED |
| Isolated provenance SQLite store integrity/restart/permissions | PASS in synthetic tests | Not canonical runtime storage; CONFIDENTIAL/SECRET data still blocked without an encryption-at-rest adapter |
| Live production runtime uses these source changes | BLOCKED / NOT VERIFIED | The running service process has cwd /data/data/com.termux/files/home/hg2-phone and command python3 -u /data/data/com.termux/files/home/hg2-service/entry.py, not this checkout. It was observed only; no environment or secrets were read and no live runtime files were modified |
| Production backup cadence, off-device restore rehearsal and data-loss limits | BLOCKED | Unit tests do not establish a scheduled offsite backup or a real phone restore |
| General semantic paraphrase recall | BLOCKED | Alias metadata addresses known paraphrases only. Broad paraphrases require a larger held-out, human-labelled Vietnamese benchmark and a retrieval design decision |
| Merge/deploy | NOT PERFORMED by design | PR #29 remains OPEN · DRAFT |

## Closure decision

M2/M3 implementation-and-test slice is ready for review if all final hashes, worktree state, push and PR metadata checks pass. The entire anti-forgetting system is NOT CLOSED: live runtime adoption/build identity, authorized restore rehearsal, general semantic recall evidence and independent review remain acceptance blockers. Do not mark these operational gates PASS based on unit tests.
