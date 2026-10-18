# HG2 Tools Distribution Integration — 2026-10-19

- Target: `stt/hg2-gap-integration-20261018`.
- Functional port from `stt/hg2-unification-p0-20261016`: `tools/build_distribution.py`. Added target-specific `tests/test_distribution.py`; adapted acceptance assertions to the existing target `manifest.json` instead of importing unrelated CTI-only modules from the source branch.
- Builder uses the manifest module allowlist, includes only root manifest/README/runtime modules, fixes ZIP timestamps/permissions for deterministic output, rejects output inside the checkout, rejects existing output, validates archive inventory, and removes a failed partial artifact.
- Focused suite: **5 tests, OK**. Full target suite: **92 tests, OK**.
- No source ref deleted and no branch created.
