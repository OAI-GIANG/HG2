# HG2 Branch 2 — Memory, Knowledge, History Import

## Scope
This branch is a new integration workspace for Branch 2 only: memory, knowledge, history, durable state, replica/state continuity, and provenance memory. `origin/hg-genesis` is the immutable source baseline and was not modified. No source branch was merged wholesale.

## Imported sources (file-level, not whole-branch merges)
- `origin/fix/history-integrity-v2` (`b28fff890f2d879a77e1fda3ce26c87f3bec7a45`): `hg/history.py`, `tests/test_integrity_v2.py`.
- `origin/stt/cleanroom-gap-closure-20261015` (`dadf599b25005b787d5a9665ce8d8727b7784bef`): `tests/test_history_malformed_shapes.py`.
- `origin/stt/hg2-single-system-20261017` (`4229892a2569eca68fcbcf32bae0c7d34dc07fa5`): `hg/memory.py`, `hg/durable.py`, `hg/replica.py` and their focused tests plus `tests/test_provenance.py`.
- `origin/stt/hg-agentic-intelligence-g1-20261017` (`78f1149c9aa4d3f7920c33c19a8954db0927ddb4`): `hg/provenance_memory.py`.

## Import policy
Files are intentionally accepted even if source-branch quality is unresolved. They are not represented as verified or release-ready. Dependencies, API compatibility, duplicated concepts, failure modes, and test results must be reviewed on this branch. Genesis, source refs, and pre-existing review artifacts are preserved.

## Validation status
NOT RUN at import time. No claim of tests passing, compatibility, or release readiness is made by this record.
