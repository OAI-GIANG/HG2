# HG2 External Branch Archive — 2026-10-19

This folder preserves branch-specific deltas before the non-canonical refs are retired. The five intended remote branch refs are `hg-genesis` (Brain), `stt/hg2-single-system-20261017` (Memory), `stt/hg2-voice-tools-design-20261018` (Creative), `stt/hg2-gap-integration-20261018` (Tools), and `stt/hg2-circulatory-architecture-20261018` (Security).

Each patch is a binary-capable Git diff from the recorded common ancestor to the exact source HEAD; the manifest records the source HEAD SHA, merge base, changed paths, full commit chain, tree IDs, commit subjects, patch IDs, patch SHA-256, and the exact ref in the recovery bundle. Exact duplicate patches share a single stored patch. `main` had no common ancestor and only carried `.bootstrap`, a plain-text anchor explicitly superseded by the clean-slate genesis commit; the exact file is stored under `standalone/`.

**Archive is not activation.** Historical T-018 implementation/design branches are preserved but remain explicitly deferred; this archive does not claim T-018 is completed or integrated into the live sync runtime. Alternate history/security, product-scope, CI, and unification variants are preserved for reproducibility; do not overlay their code onto the active implementation without an API/security compatibility review and tests. The active code stays in the five canonical branches.

The full branch preservation bundle is local at the path and SHA-256 recorded in `manifest.json`; `git bundle verify` succeeded before archive creation. The archive's source snapshots were scanned for common GitHub/OpenAI/cloud private-key patterns with zero matches. This scan is a heuristic, not a general secret guarantee.
