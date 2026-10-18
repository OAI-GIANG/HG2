# HG-CTI V1 — Source License Resolution

Status: archive-level investigation complete; not legal advice. This separates root licenses from package/vendor component declarations.

| Archive | Observed license indicator | Status | HG-CTI decision |
|---|---|---|---|
| memXT-main.zip | MIT | VERIFIED_LICENSE_FILE | No code copied; future reuse needs scoped compatibility review. |
| friday-main.zip | Apache-2.0 | VERIFIED_LICENSE_FILE | No code copied; future reuse needs scoped compatibility review. |
| pp-finder-main.zip | MIT in package.json; no LICENSE file | DECLARED_METADATA_ONLY | Principles only; not a full permission review. |
| Dom-Explorer-main.zip | MIT | VERIFIED_LICENSE_FILE | No code copied; future reuse needs scoped compatibility review. |
| vulnerable-code-snippets-main.zip | UNKNOWN | NO_LICENSE_INDICATOR_FOUND | Principles only; no code reuse. |
| PwnFox-master.zip | UNKNOWN | NO_LICENSE_INDICATOR_FOUND | Principles only; no code reuse. |
| ywh2bugtracker-master.zip | UNKNOWN | NO_LICENSE_FILE_FOUND | Principles only; no code reuse. |
| YesWeBurp-master.zip | GPL-3.0 | VERIFIED_LICENSE_FILE | No code copied; future reuse needs scoped compatibility review. |
| yeswecaido-main.zip | MIT root; ISC nested package | VERIFIED_ROOT_WITH_NESTED_SCOPE | Root and nested package scopes remain distinct. |
| myopenvdp-master.zip | MIT | VERIFIED_LICENSE_FILE | No code copied; future reuse needs scoped compatibility review. |
| xsstools-master.zip | GPL-3.0 root vs MIT package.json; vendored Apache-2.0 | LICENSE_CONFLICT | HOLD code reuse; principles only. |
| burp-addon-tutorial-main.zip | UNKNOWN | NO_LICENSE_INDICATOR_FOUND | Principles only; no code reuse. |
| hoglet-main.zip | AGPL-3.0-only in Cargo.toml; no root LICENSE | DECLARED_METADATA_ONLY | Principles only; metadata declaration is not full permission review. |
| OpenGTM-main.zip | AGPLv3 root; mixed component licenses | VERIFIED_ROOT_LICENSE_WITH_COMPONENTS | Root LICENSE says AGPLv3; component metadata includes AGPL/MIT and vendored MIT. |
| VoiceStudio-main.zip | AGPL-3.0-only root; MIT fixture | VERIFIED_ROOT_LICENSE_WITH_FIXTURE | Treat fixture license separately. |
| Opal-main.zip | GPL-3.0 | VERIFIED_LICENSE_FILE | No code copied; future reuse needs scoped compatibility review. |
| bootable-main.zip | Apache-2.0 | VERIFIED_LICENSE_FILE | No code copied; future reuse needs scoped compatibility review. |
| homebrew-memxt-main.zip | UNKNOWN | NO_LICENSE_INDICATOR_FOUND | Principles only; no code reuse. |

## Findings

- 11 archives contain a root LICENSE file. GitHub API license detection at the exact tree-matched commit corroborates standard SPDX identifiers for most; OpenGTM and VoiceStudio return NOASSERTION from the API despite root LICENSE text saying AGPLv3.
- pp-finder declares MIT in package.json but has no LICENSE file detected. hoglet declares AGPL-3.0-only in Cargo.toml but no root LICENSE was detected.
- xsstools has a root-level conflict: GPL-3.0 LICENSE versus MIT in root package.json; the vendored documentation theme has a separate Apache-2.0 license. Do not copy code until scope and authority are resolved.
- yeswecaido has root MIT and ISC in packages/common. OpenGTM has AGPLv3 root terms plus package-level AGPL/MIT and a vendored MIT component. VoiceStudio has AGPLv3 root terms and an MIT fixture.
- Five sources have no license file or explicit declaration found by the scan: vulnerable-code-snippets, PwnFox, ywh2bugtracker, burp-addon-tutorial, homebrew-memxt. Do not copy their code.
- HG-CTI records abstract principles only; no third-party source code or dependency was copied.

## Evidence

- evidence/HG-CTI-20261013/license-api-audit-pinned.json — GitHub license endpoint at exact tree-matched commit and archive license paths.
- evidence/HG-CTI-20261013/license-content-audit.json — archive LICENSE headings and package metadata.
- evidence/HG-CTI-20261013/upstream-snapshot-comparison.json — commit/tree identity for all 18 ZIPs.
- SPDX identifiers: https://spdx.org/licenses/ . GitHub licensing guidance explains that without a license, default copyright restrictions apply: https://docs.github.com/en/enterprise-cloud@latest/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository .

## Verdict

PARTIALLY RESOLVED. xsstools remains conflicted; five archives lack an explicit license indicator; two have metadata-only declarations; nested component licenses need scope-aware handling. All sources remain principle-level references only; no code reuse is approved.
