# Branch 2 source expansion — 2026-10-18

Additional feature-bearing sources imported after the initial four-source pass:
- T-018 cross-context synchronization: `hg/sync.py`, `tests/test_t018_sync.py`, and the T-018 contract.
- Circulatory architecture: SQLite state backend, sync dispatcher/tests, and its source reports/logs.
- Agentic intelligence branch: durable transaction implementation and tests.
- Unification P0 branch: authenticated sync transaction, sync authorization/bootstrap, phone-runtime sync integration tests and contracts.
- The alternate `hg/sync.py` from unification P0 is preserved as a source variant because it conflicts with the T-018 implementation; it is not silently discarded and is not automatically selected as active runtime code.

All imports are file-level. Known test failures and unresolved compatibility are intentionally retained as defects to repair, not used as exclusion criteria. Genesis remains unchanged.
