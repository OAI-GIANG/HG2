# HG2 Provenance Contract V1

Status: IMPLEMENTED IN THE CANDIDATE; AUTHENTICATION BOUNDARY REMAINS EXPLICIT.

## 1. Purpose

Bind candidate bytes, Git identity, test execution, output bytes, and process-local loaded-module fingerprints into a reproducible evidence chain. This contract is fail-closed: missing or mismatched links cannot produce PASS.

This contract does not turn local hashes into identity proof. A local report remains `LOCAL_UNATTESTED`; the hosted build provider or a separate trusted attestor must authenticate which builder produced and published the report.

## 2. Candidate snapshot

The manifest schema is `HG2_PROVENANCE_MANIFEST_V1`. It records:

- Repository identity label, Git commit SHA and Git tree SHA.
- Dirty/clean state and digest/count of the raw Git porcelain status.
- Deterministic, sorted path inventory: normalized relative path, size, executable-bit state, and SHA-256 of stable bytes.
- Digest of the canonical inventory and versioned file-exclusion policy.
- Candidate ID and manifest ID.

Candidate ID is domain-separated and derived from the repository identity, commit/tree, working-tree state, inventory digest, and policy digest. A dirty working tree is valid as a *distinct candidate snapshot*; it is never represented as the commit alone.

Files are opened without following symlinks where the platform supports `O_NOFOLLOW`. Each regular file is checked for identity/metadata changes while hashing. Symlinks, special files, unsafe/noncanonical paths, Git identity changes, and scan races fail closed.

### Exclusion policy

Only fixed, versioned generated/local metadata directories are excluded: `.git`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.tox`, `.venv`, `venv`, and `node_modules`. Excluded paths that are present are recorded with reasons. Changes to exclusion rules change the policy digest and therefore candidate identity.

No secret file is silently normalized into evidence. Secret material must not be placed in source candidate trees. When a secret-bearing or otherwise consequential file cannot be safely included or excluded under a policy known in advance, candidate capture must stop instead of claiming complete provenance.

## 3. Canonicalization and hash binding

Canonical JSON uses UTF-8, Unicode-preserving text, lexicographically sorted keys, compact separators, `allow_nan=false`, and a final line-feed. Paths must be NFC-normalized POSIX-style relative paths with no empty, `.`, or `..` component.

There is no self-referential hash:
- `inventory_sha256` hashes the canonical inventory bytes.
- `candidate_id` hashes the candidate identity fields including `inventory_sha256`.
- `manifest_id` hashes the canonical manifest body with the `manifest_id` field omitted.
- The hash of the complete manifest file is recorded by the caller outside the manifest.

A self-hash mismatch, inventory digest mismatch, unknown schema, or observed candidate mismatch is a hard failure. Consumers must not silently strip extra fields, change exclusion rules, or rewrite a manifest to make a hash match.

## 4. Test-run identity and artifacts

The CLI command `tools/hg_provenance.py run`:

1. Verifies the exact manifest against a fresh snapshot before execution.
2. Requires a new evidence directory outside the repository, avoiding evidence-induced candidate mutation.
3. Runs the supplied argument vector without shell expansion.
4. Captures the spawned process PID, argument vector, UTC start/end times, exit code, runtime environment metadata, stdout/stderr byte counts and SHA-256.
5. Re-snapshots after the process exits. Candidate drift changes result status to `BLOCKED`, even when the command exits zero.
6. Writes `test-run.json` and a sidecar hash after collection. Reusing an existing output directory is rejected.

A nonzero command result is `FAIL`, not `PASS`. Missing/mismatched candidate linkage is `BLOCKED`. The local runner does not independently authenticate itself, so its trust status remains `LOCAL_UNATTESTED`. Replay protection across machines requires a trusted external run identifier or attestor; UUID generation alone is not a trust anchor.

## 5. Live module identity

`PhoneRuntime.health()` includes `runtime_identity` generated within the calling process. It captures PID, process start ticks where available, executable path, current working directory, Python version, module origins, current on-disk module hashes, and a deterministic fingerprint of loaded Python code objects (including bytecode, constants, names, variables, stack size and exception-table digest).

The following evidence fields are intentionally distinct:

- `disk_sha256`: digest of the file at its current path.
- `loaded_code_inventory_sha256`: fingerprint of Python code objects visible in this process.
- `module_identity_sha256`: digest of the process/module identity fields.

This is stronger than using disk hashes alone, but it is **not full memory attestation**. It does not completely capture mutable module globals, native extensions, interpreter internals, or malicious in-process tampering. The report is a process-local observation, not an authenticated remote report. Collection returns `OBSERVED_UNMATCHED`, never `PASS`, until an expected fingerprint bound to the approved candidate is supplied and compared. Missing required modules or unreadable file hashes result in `BLOCKED`.

## 6. Reason codes

The verifier must preserve the exact failure reason and never convert an unknown/missing condition into PASS.

| Code | Meaning | Effective result |
|---|---|---|
| `PROV_MISSING` | Required input/evidence absent | BLOCKED |
| `PROV_MISMATCH` | Bytes or identity values differ | BLOCKED |
| `PROV_UNVERIFIABLE` | Required fact cannot be reliably observed | BLOCKED |
| `PROV_UNTRUSTED_SOURCE` | Source identity/attestation is not trusted | BLOCKED |
| `PROV_BLOCKED` | Policy precondition or dependency unmet | BLOCKED |
| `PROV_CHAIN_BROKEN` | Candidate → run → artifact relationship is broken | BLOCKED |
| `PROV_CIRCULAR_EVIDENCE` | Evidence self-validates without an external anchor | BLOCKED |
| `PROV_ID_COLLISION` | Same identifier binds to inconsistent content | BLOCKED |
| `PROV_CANONICALIZATION_INVALID` | Ambiguous or noncanonical encoding/path | BLOCKED |
| `PROV_MANIFEST_BINDING_INVALID` | Manifest schema/binding is invalid | BLOCKED |
| `PROV_RUN_REPLAY` | Old evidence presented as a new execution | BLOCKED |
| `PROV_RUNTIME_IDENTITY_INCOMPLETE` | Loaded process/module identity is incomplete | BLOCKED |
| `PROV_ARTIFACT_HASH_MISMATCH` | Artifact bytes do not match the recorded digest | BLOCKED |
| `PROV_POLICY_INVALID` | Snapshot/evidence policy violated | BLOCKED |
| `PROV_TEST_COMMAND_FAILED` | Validly linked test command exits nonzero | FAIL |

If more than one reason applies, record all observed reasons. Do not use `FAIL` for a missing trust anchor; distinguish a demonstrated product/test failure from unavailable or untrusted evidence.

## 7. PASS invariant

A local candidate test result can be PASS only when the exact manifest verifies before and after the test, the same candidate ID is bound to the run, the process exit code is zero, and the log bytes hash correctly. This is still `LOCAL_UNATTESTED`.

A release/production conclusion additionally requires an authenticated external builder/run binding and applicable live-runtime, state-authority, credential, end-to-end, backup, recovery and rollback evidence. In particular:

- A passing local test does not prove remote or live behavior.
- A file hash does not prove a loaded module identity.
- A loaded-code fingerprint does not prove external attestation.
- A test double does not prove a production key provider or monotonic anchor.
- A hash manifest cannot authenticate itself.
- A skipped device-specific rollback test is not a passed rollback gate.

## 8. External design references

- [SLSA Build Provenance](https://slsa.dev/spec/v1.2/provenance): describes verifiable metadata about how an artifact was produced and the builder identity boundary.
- [in-toto Attestation Statement](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md): binds an attestation to immutable subjects using digests and a declared predicate type.
- [Python import system](https://docs.python.org/3/reference/import.html): documents module specs and import origins; module origin is useful metadata but not itself a memory attestation.
- [SQLite Atomic Commit](https://www.sqlite.org/atomiccommit.html): explains transactional atomicity and crash behavior under the documented operating mode; these guarantees do not substitute for HG2-specific end-to-end fault tests.
- [CircleCI Configuration Reference](https://circleci.com/docs/reference/configuration-reference/): documents external job status and artifact storage used to retain candidate/run evidence.

## 9. Current acceptance boundary

Implementation of deterministic candidate inventory, manifest binding, before/after test-run binding, artifact hashes, and process-local loaded-code fingerprints is candidate scope. It does not by itself close the technical acceptance gaps that require independently authenticated hosted provenance, a production-grade monotonic anchor/key provider, an actual second peer, or verified production recovery/rollback. Such gaps stay BLOCKED until their evidence exists.
