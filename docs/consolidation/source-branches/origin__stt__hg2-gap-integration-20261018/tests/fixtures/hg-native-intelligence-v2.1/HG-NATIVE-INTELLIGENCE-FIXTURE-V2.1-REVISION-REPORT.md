# HG-NATIVE-INTELLIGENCE-FIXTURE-V2.1 — REVISION AND VALIDATION REPORT

**Package:** HG-NATIVE-INTELLIGENCE-FIXTURES-V2.1
**Version:** 2.1.0 with oracle-spec schema v2.1.1
**Disposition:** FIXTURE DESIGN PACKAGE COMPLETE — STATIC/SEMANTIC-CONSISTENCY VALIDATION PASS — NOT_RELEASED
**Execution:** All fixture behavior and HG implementation tests remain NOT_RUN
**Scope:** Synthetic fixture package only; no production data, secrets, network calls, or live mutations.

## Summary

The package contains 26 synthetic fixtures and a manifest. Every fixture remains explicitly execution_status=NOT_RUN and result_record.observed_status=NOT_RUN. Added a machine-readable oracle_spec to all 26 fixtures so key input cases and expected predicates are concrete rather than relying only on prose.

## Changes completed

1. Added oracle_spec_version=hni.oracle-spec.v2.1.1 and per-fixture oracle_spec.case_data plus explicit predicates.
2. Added structured constraints/dependency records, conflicting requirements, claim/source mapping, provenance metadata, feedback delta, experiment baseline, transfer boundary, counterexample, uncertainty inputs, correction dependencies, partial tool sequence, authorization trace, sink policy, fault records, repeatability identity, critical-gate case, status/source states, improvement metrics, digest/authority separation, retry ledger, missing/mismatched artifact cases, malformed-manifest cases, post-hoc oracle-change case, N/A exclusion case, and evidence-status cases.
3. Corrected HNIF2-05 score semantics and recorded weighted scores: A=2.80, B=3.80. Option A is disqualified before ranking because feasibility=1 is below threshold 2; B remains eligible.
4. Made HNIF2-19 explicitly descriptive only: baseline 20/200=10%; candidate 8/200=4%; absolute reduction 6 percentage points; relative reduction 60%; causal claim prohibited without controlled-design evidence.
5. Added deterministic checks for arithmetic, dependency recomputation, synthetic digest values, fixture IDs/schema, manifest mapping, HNIT/XN coverage, and status aggregation precedence.
6. Retained the fail-closed suite rule: any evidenced applicable C0 FAIL forces suite FAIL regardless of aggregate score or other missing results. The validator includes an aggregation truth table.
7. Kept the package synthetic-only and all execution records NOT_RUN.

## Validation evidence

Command:

    python3 /data/data/com.termux/files/home/CP0-EXTERNAL-REFERENCE-IMPLEMENTATION/HG-NATIVE-INTELLIGENCE-FIXTURES-V2.1/validate_v21.py

Observed output:

    STATIC_SEMANTIC_VALIDATION PASS
    fixtures=26 unique_ids=26 oracle_specs=26/26
    HNIT=30/30 XN=6/6
    semantic_arithmetic=PASS
    digest_recompute=PASS
    aggregation_truth_table=PASS
    preservation_size_presence_checks=PASS (not byte-for-byte proof)
    errors=[]

This validates static package consistency and selected deterministic oracle calculations. It does not execute the fixtures against HG, prove the semantic quality of every possible response, or establish production behavior.

## Preserved boundaries

- V1, V2, the frozen CP0 documents, and source/canonical/runtime state were not intentionally modified.
- No Git commit, push, merge, deployment, migration, or release was performed; this fixture package is outside a verified Git release workflow.
- Preservation validation checks presence and previously recorded file sizes only; it is not a cryptographic byte-for-byte proof.
- The historical 26 criteria remain unresolved and are not replaced by the HG-native fixtures.
- No HG implementation behavior is claimed as tested or verified.

## Final status

**CLOSED for the scoped V2.1 fixture-design and static/semantic-consistency work. NOT_RELEASED for HG itself.** Any later implementation evaluation must use a pinned implementation/build/configuration and produce actual raw execution records. The fixture package is ready as a test-specification input, not as evidence that HG passed the tests.
