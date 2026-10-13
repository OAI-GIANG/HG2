# HG Creative Assimilation V1 — Source-to-Principle Matrix

All local archive SHA-256 values and ZIP CRC results are recorded in
evidence/HG-CTI-20261013/archive-manifest.json. The exact upstream commit for each archive remains
UNKNOWN because the archives contain no .git metadata. A URL shown below is an identity candidate
found in the archive README or package metadata; it does not prove that the ZIP is byte-equivalent
to that upstream revision. No source code is copied into HG.

| # | Archive / project | Principle candidate | Disposition | License / provenance gate |
|---:|---|---|---|---|
| 1 | memXT | Durable memory retrieval with evidence references and paraphrase-aware recall | KEEP AS PRINCIPLE | MIT license file found; exact source commit not mapped |
| 2 | Friday | Explicit approval, typed side effects, execution receipts, postcondition reconciliation | KEEP AS PRINCIPLE | Apache-2.0 file found; source URL candidate https://github.com/debpalash/friday; exact commit not mapped |
| 3 | PP-Finder | Candidate discovery/anomaly signals are hypotheses, not findings until tested | TRANSFORM | Package metadata says MIT; source URL candidate https://github.com/yeswehack/pp-finder; archive has no root license file |
| 4 | DOM-Explorer | Compare transformations side-by-side and retain intermediate observations | KEEP AS PRINCIPLE | MIT file found; source URL candidate https://github.com/yeswehack/Dom-Explorer |
| 5 | Vulnerable Code Snippets | Counterexamples and failure cases as negative-test material | KEEP AS PRINCIPLE | No license file found in archive; reference-only, no copied payloads |
| 6 | PwnFox | Explicit isolation of scope/context boundaries | TRANSFORM | No license file found in archive; source URL candidate https://github.com/B-i-t-K/PwnFox; reference-only |
| 7 | YWH2BugTracker | Finding lifecycle, controlled synchronization and conflict-aware updates | TRANSFORM | No license file found in archive; source URL candidate https://github.com/yeswehack/ywh2bugtracker; reference-only |
| 8 | YesWeBurp | External feedback/source adapter pattern | REFERENCE ONLY | GPL-3.0 license file found; source URL candidate https://github.com/yeswehack/YesWeBurp; no code copied |
| 9 | YesWeCaido | External feedback/source adapter pattern | REFERENCE ONLY | MIT license file found; source URL candidate https://github.com/yeswehack/yeswecaido |
| 10 | MyOpenVDP | Bounded, auditable intake and disclosure lifecycle | TRANSFORM | MIT file found; source URL candidate https://github.com/yeswehack/my-open-vdp |
| 11 | xsstools | Security payload research may inform threat modeling but is not a core creativity primitive | REFERENCE ONLY | License conflict: archive GPL-3.0 text versus package metadata MIT; source URL candidate https://github.com/yeswehack/xsstools; no payload implementation copied |
| 12 | Burp Addon Tutorial | Adapter/plugin boundary pattern | REFERENCE ONLY | No license file found in archive; no code copied |
| 13 | Hoglet | Contract-driven observability and explicit system boundaries | TRANSFORM | Cargo metadata declares AGPL-3.0-only; source URL/revision mapping unresolved |
| 14 | OpenGTM | Source selection and cost-aware provider waterfalls as a bounded sourcing strategy | TRANSFORM | License file found; source URL candidate https://github.com/debpalash/OpenGTM; exact revision and full dependency license review unresolved |
| 15 | VoiceStudio | Multimodal capability should sit behind a provider/adapter boundary | TRANSFORM | Cargo/package metadata indicates AGPL-3.0-only; source URL candidate https://github.com/debpalash/VoiceStudio; exact revision unresolved |
| 16 | Opal | Privacy-conscious media browser/player and optional local AI are product-boundary references only | REFERENCE ONLY | License file found; exact upstream identity/revision must be reconciled against the actual archive |
| 17 | Bootable | Separate source, target, review, execution and verification phases | TRANSFORM | Cargo metadata declares Apache-2.0; exact upstream URL/revision unresolved |
| 18 | Homebrew memXT | Packaging/distribution as a separate optional concern | REFERENCE ONLY | No license file found in archive; source README references https://github.com/Yupcha/memxt |

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
- Upstream source identity and exact revision must be independently mapped before source authenticity
  can pass.
- A license file or package metadata is evidence to review, not a legal conclusion.
- Missing/ambiguous license means reference-only; no code/dependency reuse.
- Source-level claims must be tied to inspected paths and limitations.
