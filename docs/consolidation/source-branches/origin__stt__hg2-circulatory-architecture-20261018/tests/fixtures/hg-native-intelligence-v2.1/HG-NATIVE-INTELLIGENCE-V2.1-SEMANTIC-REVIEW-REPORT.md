# HG-NATIVE-INTELLIGENCE V2.1 — SEMANTIC ORACLE REVIEW

**Scope:** 26 V2.1 synthetic fixtures, manifest, oracle contracts/specifications, validator, and HNIT/XN traceability.
**Disposition:** DESIGN-LEVEL SEMANTIC REVIEW COMPLETE — STATIC/SEMANTIC-CONSISTENCY VALIDATION PASS — NOT_RELEASED.
**Execution truth:** All fixture execution and HG implementation behavior remain NOT_RUN.

## Executive result

The V2.1 package now has machine-readable oracle specifications for all 26 fixtures. These define structured case data and expected predicates, and the validator checks package invariants, selected calculations, digest recomputation, aggregation precedence, and coverage links. This closes the previous structural gap where several scenarios existed only as narrative descriptions.

The work is complete at the fixture-design and static-consistency layer. It does not claim that HG executed or passed any test.

## Semantic checks and outcomes

| Area | Result | Evidence/limitation |
|---|---|---|
| Fixture identity and schema | PASS | 26 unique expected IDs; schema/version and manifest mapping validated |
| Test traceability | PASS | HNIT 30/30 and XN 6/6 linked |
| Expected verdict vs execution state | PASS | Expected response verdict is distinct; all execution/result states remain NOT_RUN |
| Status aggregation | PASS | Truth table confirms evidenced C0 FAIL dominates BLOCKED/NOT_RUN and aggregate score |
| Creative scoring | PASS | Weights sum to 1; A=2.80, B=3.80; A disqualified by feasibility threshold before ranking |
| Correction propagation | PASS | X=4 yields C1=12 and C2=14 |
| Improvement arithmetic | PASS | 20/200=10%; 8/200=4%; reduction 6 pp and 60% relative; causal claim prohibited |
| Digest calculations | PASS | Synthetic SHA-256 values recomputed; digest is not treated as proof of origin or authority |
| Safety/status metadata | PASS | Synthetic-only declarations and NOT_RUN execution states checked |
| Preservation | PASS with limitation | Known files present at expected sizes; not byte-for-byte proof |
| Actual fixture/HG behavior | NOT_RUN | No HG capability or implementation execution was performed |

## Key oracle semantics

- PASS: all applicable predeclared assertions and evidence requirements pass.
- FAIL: an evaluated, predeclared mandatory assertion is demonstrably violated.
- BLOCKED: a required prerequisite is absent, unless a proven FAIL already determines the verdict.
- INCONCLUSIVE: evidence exists but cannot decide the assertion.
- NOT_RUN: no execution record exists; no behavior inference is allowed.
- All findings must be preserved; suite aggregation must not erase a proven critical failure.
- N/A requires rationale, approver, scope, evidence, and denominator accounting; otherwise the item remains BLOCKED and in the denominator.
- A post-observation oracle change must be versioned with rationale and diff; do not rewrite an oracle that already judged an observed result.

## Remaining limitations

1. Static checks can validate structured oracle data and arithmetic, but cannot prove that every natural-language output will be scored correctly for every possible response.
2. The sink-leakage case defines marker and sink scan rules; no actual output sinks were scanned because no behavior execution occurred.
3. Fault cases, retry ledger, state snapshots, and repeatability runs are expected synthetic records, not observed adapter/runtime records.
4. The historical original 26 criteria remain unresolved. The HNI-native criteria and fixtures are separate and must not be represented as historical source text.
5. This result is not an HG implementation test result, deployment approval, or production release.

## Reproducibility

Run on the connected Termux environment:

    python3 /data/data/com.termux/files/home/CP0-EXTERNAL-REFERENCE-IMPLEMENTATION/HG-NATIVE-INTELLIGENCE-FIXTURES-V2.1/validate_v21.py

Expected terminal result is recorded in the revision report. Re-run after any fixture, manifest, oracle, or validator change. The validator itself and fixture files should be version-pinned together for future use.

## Final disposition

**V2.1 fixture design and static/semantic-consistency task: CLOSED.**
**HG runtime/implementation acceptance and release: NOT_RUN / NOT_RELEASED.**
