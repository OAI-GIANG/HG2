# HG Creative Assimilation V1 — Source-to-Principle Matrix

All local archive SHA-256 values and ZIP CRC results are recorded in
evidence/HG-CTI-20261013/archive-manifest.json. The archives contain no embedded .git metadata, but a read-only GitHub API comparison has now
matched all 18 archive file paths and Git blob SHA-1 values against the observed upstream default-
branch commit trees. The exact observed commit SHAs and repository identities are recorded in
evidence/HG-CTI-20261013/upstream-snapshot-comparison.json. This proves tree equality at observation
time, not license compatibility, legal permission, semantic correctness, or benefit. No source code
is copied into HG.

| # | Archive / project | Principle candidate | Disposition | License / provenance gate |
|---:|---|---|---|---|
| 1 | memXT | Durable memory retrieval with evidence references and paraphrase-aware recall | KEEP AS PRINCIPLE | MIT license file found; upstream commit tree match recorded below |
| 2 | Friday | Explicit approval, typed side effects, execution receipts, postcondition reconciliation | KEEP AS PRINCIPLE | Apache-2.0 file found; upstream repository https://github.com/debpalash/friday; upstream commit tree match recorded below |
| 3 | PP-Finder | Candidate discovery/anomaly signals are hypotheses, not findings until tested | TRANSFORM | Package metadata says MIT; upstream repository https://github.com/yeswehack/pp-finder; archive has no root license file |
| 4 | DOM-Explorer | Compare transformations side-by-side and retain intermediate observations | KEEP AS PRINCIPLE | MIT file found; upstream repository https://github.com/yeswehack/Dom-Explorer |
| 5 | Vulnerable Code Snippets | Counterexamples and failure cases as negative-test material | KEEP AS PRINCIPLE | No license file found in archive; reference-only, no copied payloads |
| 6 | PwnFox | Explicit isolation of scope/context boundaries | TRANSFORM | No license file found in archive; upstream repository https://github.com/B-i-t-K/PwnFox; reference-only |
| 7 | YWH2BugTracker | Finding lifecycle, controlled synchronization and conflict-aware updates | TRANSFORM | No license file found in archive; upstream repository https://github.com/yeswehack/ywh2bugtracker; reference-only |
| 8 | YesWeBurp | External feedback/source adapter pattern | REFERENCE ONLY | GPL-3.0 license file found; upstream repository https://github.com/yeswehack/YesWeBurp; no code copied |
| 9 | YesWeCaido | External feedback/source adapter pattern | REFERENCE ONLY | MIT license file found; upstream repository https://github.com/yeswehack/yeswecaido |
| 10 | MyOpenVDP | Bounded, auditable intake and disclosure lifecycle | TRANSFORM | MIT file found; upstream repository https://github.com/yeswehack/my-open-vdp |
| 11 | xsstools | Security payload research may inform threat modeling but is not a core creativity primitive | REFERENCE ONLY | License conflict: archive GPL-3.0 text versus package metadata MIT; upstream repository https://github.com/yeswehack/xsstools; no payload implementation copied |
| 12 | Burp Addon Tutorial | Adapter/plugin boundary pattern | REFERENCE ONLY | No license file found in archive; no code copied |
| 13 | Hoglet | Contract-driven observability and explicit system boundaries | TRANSFORM | Cargo metadata declares AGPL-3.0-only; upstream commit tree match recorded below |
| 14 | OpenGTM | Source selection and cost-aware provider waterfalls as a bounded sourcing strategy | TRANSFORM | License file found; upstream repository https://github.com/debpalash/OpenGTM; upstream commit tree match recorded below; full dependency license review unresolved |
| 15 | VoiceStudio | Multimodal capability should sit behind a provider/adapter boundary | TRANSFORM | Cargo/package metadata indicates AGPL-3.0-only; upstream repository https://github.com/debpalash/VoiceStudio; upstream commit tree match recorded below |
| 16 | Opal | Privacy-conscious media browser/player and optional local AI are product-boundary references only | REFERENCE ONLY | License file found; upstream commit tree match recorded below |
| 17 | Bootable | Separate source, target, review, execution and verification phases | TRANSFORM | Cargo metadata declares Apache-2.0; upstream commit tree match recorded below |
| 18 | Homebrew memXT | Packaging/distribution as a separate optional concern | REFERENCE ONLY | No license file found in archive; upstream repository reference https://github.com/Yupcha/memxt |

## Cross-project synthesis proposed
A useful HG-specific synthesis is a **Creative Evidence Loop**: combine (a) memory retrieval with
source references, (b) candidate discovery, (c) transformation comparison, (d) counterexamples,
and (e) controlled review/receipts. The novelty claim is a hypothesis, not yet demonstrated. The
current implementation supplies only the candidate/evidence contract and fail-closed lifecycle;
it does not yet execute the loop against a benchmark or alter runtime memory.

## Inspection depth and source eligibility
This pass verified all 18 local ZIP byte digests and CRC checks and performed a bounded README,
metadata and project-purpose review. It is not a line-by-line source-code security audit of all 18
projects. No source-level implementation behavior is claimed for files not explicitly inspected.

- Archive SHA-256 and ZIP CRC are recorded and reproducible.
- All 18 repository identities and default-branch commit trees match the local archive bytes at
  observation time; this does not certify licenses, semantics or product benefit.
- A license file or package metadata is evidence to review, not a legal conclusion.
- Missing/ambiguous license means reference-only; no code/dependency reuse.
- Source-level claims must be tied to inspected paths and limitations.

## Exact observed upstream revisions

- memXT-main.zip — https://github.com/Yupcha/memxt @ 55b81ce235587722a0611b0ca1754914972fae84 — TREE_MATCH
- friday-main.zip — https://github.com/debpalash/friday @ d731952210a184580318d64fbf55662f239b7313 — TREE_MATCH
- pp-finder-main.zip — https://github.com/yeswehack/pp-finder @ 6e1011ca6bfc0a49ac40f8e6eb3e3e157e649fab — TREE_MATCH
- Dom-Explorer-main.zip — https://github.com/yeswehack/Dom-Explorer @ fdde12fa842fd212cf6f864b1f872a07bd1132b0 — TREE_MATCH
- vulnerable-code-snippets-main.zip — https://github.com/yeswehack/vulnerable-code-snippets @ 90c910e15b9fd2ce7dbc06c7594a050d486b80e8 — TREE_MATCH
- PwnFox-master.zip — https://github.com/B-i-t-K/PwnFox @ 74d1688f760413430790ac40db72744e2b4a8dbb — TREE_MATCH
- ywh2bugtracker-master.zip — https://github.com/yeswehack/ywh2bugtracker @ 9b617f1c349fb3c0e1b0d003552811637f6c47e7 — TREE_MATCH
- YesWeBurp-master.zip — https://github.com/yeswehack/YesWeBurp @ 67c9499a8148a4a672a90cce433a073d1472d3c7 — TREE_MATCH
- yeswecaido-main.zip — https://github.com/yeswehack/yeswecaido @ 0fa00adb0bda589ac43938f92023d114878faf68 — TREE_MATCH
- myopenvdp-master.zip — https://github.com/yeswehack/my-open-vdp @ 03e90e225cb8aee90bd36c5684b97b5298dcbbbb — TREE_MATCH
- xsstools-master.zip — https://github.com/yeswehack/xsstools @ 115ab6d925b87b302c2a5c81899005d59caaaef5 — TREE_MATCH
- burp-addon-tutorial-main.zip — https://github.com/yeswehack/burp-addon-tutorial @ 6a8b7a5a0ee3836aa227bc2cd287f3e5c2fea38d — TREE_MATCH
- hoglet-main.zip — https://github.com/debpalash/hoglet @ ff5db7ad819e32e1890607080f98be8f86033252 — TREE_MATCH
- OpenGTM-main.zip — https://github.com/debpalash/OpenGTM @ 9188fc4d040c186f3495902fe77e0d041deba3bd — TREE_MATCH
- VoiceStudio-main.zip — https://github.com/debpalash/VoiceStudio @ c2ef99817fc4f2e0271a223c357e57e8df93cbde — TREE_MATCH
- Opal-main.zip — https://github.com/debpalash/Opal @ 3b708aa2bfc791c8885a26b0339ff6318e7d1355 — TREE_MATCH
- bootable-main.zip — https://github.com/debpalash/bootable @ f4837882be756cc33fda738890a6e382473f926f — TREE_MATCH
- homebrew-memxt-main.zip — https://github.com/Yupcha/homebrew-memxt @ 07b8451114302080dcaafc3ae01daa6e2b36a223 — TREE_MATCH
