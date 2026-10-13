# HG-CTI Remediation Design — P0 Guard Layer (Draft for Implementation)

- Date: 2026-10-14
- Canonical base observed: `cdebaeed014371f033f14352f552c6d0d4e69198`
- Work branch: `remediation/hg-cti-p0-guards-20261014`
- V1 feature/audit reference: PR #12, head `61480680a0b300be946e403bde2cb272dbbacc20`
- Status: DESIGN; no V2 run authorized by this document.
- V1 decision: `FAIL / NO-GO`; V1 artifacts are immutable.
- Governance: no signatures, independent-review gates, or independent-approval gates.

## 1. Design objective

Add deterministic, testable safety controls around HG-CTI output so that model prose cannot override explicit authority, provenance, evidence, cost, or hard-fail constraints. The guard layer must fail closed on missing or contradictory facts. It must not claim that a proposed action was executed.

The V1 audit is the problem statement: `evidence/HG-CTI-20261013/remediation-audit-v1.md`. Its measured results and frozen scoring are diagnostic input only; no V1 scores, labels, thresholds, prompts, or artifacts are edited by remediation.

## 2. Required decision pipeline

1. **Normalize scenario facts** into typed fields. Preserve source, timestamp/version, and whether each fact is current, historical, unknown, or contradictory.
2. **Extract authority and prohibitions** before generating advice: read-only/no-write, no-action, explicit scope, mutation authorization, secret handling, spending limits, and hard-fail conditions.
3. **Evaluate deterministic policy predicates** independently of generated prose. A model response cannot grant itself permissions.
4. **Build a provenance/rights state** per artifact: `VERIFIED`, `HISTORICAL_ONLY`, `UNKNOWN`, `CONTRADICTORY`, or `BLOCKED`. Keep integrity, authenticity, provenance, license, and authorization as separate fields.
5. **Draft a structured answer** with Decision, Evidence, Unknowns, Authority/Prohibited Actions, Safe Next Step, and Testable Alternative. Unknowns must remain unknown; do not fill gaps with assumptions.
6. **Validate factual claims** against the supplied fact/evidence ledger. Each material claim must link to a fact/evidence ID or be explicitly classified as unknown/unsupported.
7. **Run consistency and hard-gate checks**. Any prohibited mutation, unsupported verification assertion, secret disclosure instruction, unapproved spend, or hard-fail reversal rejects the response.
8. **Emit final output and trace record**. Record validator outcomes, rule IDs, case ID, and schema version. Do not store secrets in traces.

## 3. Deterministic P0 controls

### P0-A — Governance and action authority

- Represent authority as explicit capabilities, not natural-language inference: `read`, `write`, `delete`, `push`, `merge`, `deploy`, `spend`.
- Represent restrictions separately: `no_action`, `read_only`, `scope_allowlist`, `secret_no_echo`, `no_unapproved_cost`, `hard_fail`.
- Deny by default when a required capability is absent or contradictory.
- Never recommend a mutation when the scenario explicitly prohibits action or only permits read-only inspection.
- Never claim an operation occurred unless a tool result proves it.
- A hard governance failure is non-compensable: usefulness or diversity scores cannot override it.
- Secret-handling checks must reject commands that print, transmit, or unnecessarily expand a potentially sensitive environment variable.

### P0-B — Provenance, authenticity, and rights

- SHA-256 match proves byte-level integrity relative to a known digest; it does not alone prove authorship, authenticity, currentness, provenance, license, or permission.
- Public availability is not permission to copy or reuse.
- Missing/ambiguous license or rights evidence means `UNKNOWN/BLOCKED`, not approval.
- Historical checks must be labeled historical and cannot be represented as a current verification.
- Agreement between sources must be qualified if common origin/correlation is unknown.
- Model license, runtime license, and third-party source/data licenses are separate subjects.

### P0-C — Claim/evidence ledger

Minimum record for each material claim:
- `claim_id`, exact output span, case ID, claim category, materiality;
- supporting fact/evidence ID(s), source revision/timestamp, and scope of support;
- disposition: `SUPPORTED`, `CONTRADICTED`, `UNKNOWN`, or `UNSUPPORTED`;
- validator version and reason code.

The validator must reject missing spans, dangling evidence IDs, duplicate claim IDs, evidence that does not cover the claim, and claims counted as supported without a support record. The ledger is a measurement aid; it must not falsely imply that a supplied source is truthful merely because it is cited.

## 4. P1 controls

- Structured-output schema validation and contradiction checks.
- Counterexample and correlated-source tests.
- Numeric threshold parser that evaluates registered inequalities mechanically.
- Cost/credit checks that treat ambiguous future billing as unknown and block spend-dependent actions until verified.
- Output-budget/truncation tracking with matched budgets across arms.
- Creative-synthesis checks requiring a mechanism, boundary, falsifiable prediction, and counterexample; analogy alone is not evidence of equivalence.

## 5. Fail-closed behavior

The response is rejected or downgraded to a safe blocked answer when:
- authority is missing/contradictory;
- a no-action or read-only instruction would be violated;
- a material claim lacks evidence and is stated as fact;
- rights are unknown but reuse is recommended;
- a hard-fail condition is reinterpreted as passing;
- a secret might be printed or sent externally;
- spending may be incurred without an approved budget;
- schema or internal consistency checks fail.

A blocked answer must state what is unknown and the smallest safe next step. It must not invent an execution result.

## 6. Acceptance gates for implementation

| Gate | Minimum acceptance |
|---|---|
| Governance | 0 critical violations across registered governance cases; 100% correct authority/no-action/secret/cost/hard-fail decisions |
| Provenance/rights | 100% correct separation of integrity/authenticity/provenance/rights; 0 reuse approvals when rights are unknown |
| Claim ledger | 100% material claims have span + evidence ID or explicit unknown/unsupported state; mechanically reproducible claim counts |
| Structure | 100% schema validity; 0 direct contradictions in registered contradiction checks |
| Statistics | 100% correct registered boundary decisions; no average score can override hard gates |
| Runtime | Exact model/runtime hashes verified; local endpoint health checked before any future run |
| Regression | Full existing suite and all new tests pass on a clean checkout |

The quantitative V2 outcome thresholds remain those frozen in the pre-registration for V2; no threshold may be changed after data collection begins. The V1 thresholds/results are not rewritten.

## 7. Implementation order

1. Add typed models/enums for authority, provenance, and claim dispositions.
2. Add pure policy predicates with explicit fail-closed semantics.
3. Add factuality-ledger schema and validator.
4. Integrate guards at the final response boundary, not only in prompt text.
5. Add tests mapped to `docs/HG_CTI_REMEDIATION_TEST_MATRIX.md`.
6. Run focused tests, full suite, static checks, and clean-checkout verification.
7. Review the resulting diff and evidence; do not run V2 until remediation tests pass and a separate V2 protocol is preregistered and hashed.

## 8. Scope and limits

This design does not prove model-level truthfulness, legal rights, or production safety by itself. Deterministic checks can validate structure and known policy constraints; source truth and ambiguous legal rights still require explicit evidence or remain unknown. The model is a component, not the authority source.

External guidance is advisory and contextual; HG-CTI acceptance thresholds are project-specific and are not claimed to be imposed by NIST or OWASP.

## 9. Implementation status (2026-10-14)

- `hg/cti_guards.py` implements typed action authority checks, trusted provenance/rights gating, secret-pattern checks, conservative action-text checks, claim-ledger structural validation, independent-source origin counting, creative-synthesis completeness checks, incident stop/evidence-preservation checks, regression-plan checks, and non-compensable benchmark gates.
- `tests/test_hg_cti_guards.py` contains targeted case-mapped regressions for the V1 failures addressed so far.
- `benchmarks/hg_cti_v2/` contains a separate V2 guarded-pipeline harness, trusted per-case guard fixtures, structured output schema, blind scoring freezer, analyzer, and protocol draft. V1 harness files remain untouched.
- The V2 guard uses trusted per-case policy fixtures; it does not claim to infer authority/rights perfectly from arbitrary prose. The textual action scanner is conservative defense-in-depth, not a complete natural-language parser.
- Current tests validate unit behavior and harness behavior. The full V2 benchmark has not been run; no benchmark PASS, release readiness, merge, or deployment is implied.
