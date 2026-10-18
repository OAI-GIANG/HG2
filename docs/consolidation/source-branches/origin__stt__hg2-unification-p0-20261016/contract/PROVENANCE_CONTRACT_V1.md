# HG2 Local Integrity Evidence Contract V1

Status: local candidate tooling; not an authorization or identity service.

## Purpose

Record deterministic source inventories, exact Git commit/tree identifiers, test commands, process exit status, log hashes, and process-local module observations. SHA-256 establishes byte consistency and reproducible linkage only. It does not establish author identity, authorization, or remote runtime identity.

## Candidate manifest

The manifest records repository label, commit/tree, working-tree state, sorted path inventory, file sizes, executable-bit state, SHA-256 digests, and the versioned exclusion policy. Unsafe paths, symlinks, special files, scan races, or changed Git identity fail closed. The manifest binds itself and its inventory to hashes; that self-binding is an integrity check, not an independent trust source.

## Test-run record

The runner verifies the candidate before and after execution and records the command, process ID, timestamps, exit code, environment, stdout/stderr sizes and hashes. A nonzero exit is FAIL; candidate drift or broken linkage is BLOCKED. Evidence is stored outside the repository and an existing output directory is never overwritten.

## Process-local module observations

The runtime diagnostic records process identity, module origins, current on-disk hashes, and fingerprints of visible Python code objects. It does not fully capture mutable globals, native extensions, interpreter internals, or malicious in-process changes, and it does not establish remote process state.

## Acceptance boundary

Local evidence supports the specific claims it directly records. Production claims must be evaluated using the actual product capability and its technical tests.
