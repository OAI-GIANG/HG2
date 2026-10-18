# HG-CTI External Research Register

- Research date: 2026-10-14
- Scope: governance and safe-action controls, GenAI risk management, secure development, provenance/claim traceability, output validation, and benchmark integrity.
- Status: sources identified and reviewed at the publication/project pages; this is an engineering reference register, not legal advice or a certification.
- Rule: project-specific HG-CTI acceptance thresholds remain project decisions. No cited publication is represented as requiring a signature or independent-review gate.

## Source register

| ID | Source / version / status | Canonical URL | Relevant guidance and application to HG-CTI | Limitations |
|---|---|---|---|---|
| EXT-001 | NIST AI RMF 1.0, NIST AI 100-1; published 2023-01-26; voluntary framework | https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-ai-rmf-10 | Use Govern/Map/Measure/Manage as a risk lifecycle: inventory risks, define intended use and limits, measure known failures, and manage residual risks. Supports explicit risk register, measurable gates, and release-blocking governance failures. | Voluntary and context-dependent; it does not prescribe HG-CTI's numeric benchmark thresholds. |
| EXT-002 | NIST AI 600-1, AI RMF Generative AI Profile; published 2024-07-26; current official publication page reviewed 2026-10-14 | https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence | Apply GenAI-specific risk consideration across lifecycle, including measurement, human/operational context, output reliability, and monitoring. Supports recording model/runtime scope and not generalizing one small model's results to all models. | A risk-management profile, not proof that a particular guard or model is safe. |
| EXT-003 | NIST SP 800-218 SSDF v1.1; final 2022-02-03 | https://csrc.nist.gov/pubs/sp/800/218/final | Use secure-development practices: versioned changes, reviewable diffs, tests, vulnerability/root-cause remediation, and release evidence. Supports branch isolation, test evidence, clean-checkout validation, and not releasing on a failing gate. | NIST's publications page also lists SP 800-218 Rev. 1 / v1.2 as a draft dated 2025-12-17; do not label the draft final. The v1.1 source above is final. |
| EXT-004 | NIST SP 800-218A, Secure Software Development Practices for Generative AI and Dual-Use Foundation Models: SSDF Community Profile; final 2024-07-26 | https://csrc.nist.gov/Projects/SSDF/publications | Supplement the general SSDF with GenAI-specific lifecycle and development considerations. Use when checking model/runtime supply chain, data, and AI-specific development controls. | Profile is supplementary guidance; adapt practices to HG-CTI scope and available evidence. |
| EXT-005 | OWASP GenAI Security Project — GenAI LLM Top 10 2026, current release referenced by the official project page; canonical project source | https://github.com/GenAI-Security-Project/GenAI-LLM-Top10/tree/main/2026/final | Map prompt injection, sensitive information disclosure, improper output handling, supply-chain and excessive-agency risks to P0 authority enforcement, secret-safe behavior, output validation, dependency provenance, and explicit tool/action permissions. | Community risk taxonomy, not a complete threat model or a pass/fail certification. Confirm exact release content at the linked canonical release before a future security review. |
| EXT-006 | OWASP GenAI Security Project official landing page; current project information reviewed 2026-10-14 | https://genai.owasp.org/llm-top-10/ | Confirms the active OWASP project and current LLM risk taxonomy. Prefer this active project over the historical OWASP GitHub Pages archive. | The 2025 page remains useful historical context but should not be mislabeled as the latest release when 2026 is the current release. |

## Technical decisions traced to sources

| HG-CTI decision | Supporting source(s) | Applied artifact/test |
|---|---|---|
| Treat risk management as lifecycle work, not one prompt edit | EXT-001, EXT-002 | `docs/HG_CTI_REMEDIATION_DESIGN.md`; risk and residual-risk reporting |
| Separate model capability claims from observed evidence; record model/runtime scope | EXT-001, EXT-002, EXT-004 | Runtime/provenance tests CTI-010, CTI-012–016 |
| Require branch-isolated changes, regression tests, clean-checkout evidence, and reproducible release artifacts | EXT-003, EXT-004 | Test matrix and patch acceptance workflow |
| Use deterministic enforcement for authority and hard-fail semantics rather than trusting generated prose | EXT-001, EXT-002, EXT-005 | GOV-P0; CTI-017–021, CTI-027, CTI-035 |
| Reject unsafe handling of potential secrets and unauthorized tool/action behavior | EXT-002, EXT-005, EXT-006 | CTI-019, secret-safe and authority guard tests |
| Validate generated output structure and trace material claims to evidence | EXT-002, EXT-005 | LEDGER-P0, SCHEMA-P1, claim ledger validator tests |
| Track model/runtime/source licenses separately and do not infer reuse rights from public access or a hash | EXT-003, EXT-004 (secure supply-chain context); HG-CTI source-specific license evidence | RIGHTS-P0; CTI-001–008 and CTI-040 |
| Freeze protocol, dataset, prompts, model/runtime identity, scoring and analysis rules before data collection | EXT-001, EXT-002, EXT-003 | V2 pre-registration requirements; no V2 run before freeze |

## Research method and integrity

- URLs above point to official NIST or OWASP project pages/canonical release locations.
- Publication/version/status is recorded separately from engineering interpretation.
- NIST AI RMF and OWASP guidance are advisory references; HG-CTI's own preregistered thresholds remain the acceptance authority for this project.
- No claim is made that the cited sources require independent reviewer signatures or approval gates; HG-CTI explicitly does not introduce such gates.
- Before V2, pin the exact OWASP 2026 release commit or archive digest used by the implementation review, and retain the exact NIST publication/version references.
- This register does not assert that the code has already implemented these recommendations or that tests have passed.
