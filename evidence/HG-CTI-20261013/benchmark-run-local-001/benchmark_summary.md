# HG-CTI Benchmark Analysis

- **Status:** FAIL
- Cases/pairs: 40
- Baseline mean usefulness: 35.00%
- Candidate mean usefulness: 30.00%
- Paired improvement: -5.00 percentage points
- Paired 95% CI: [-13.53, 3.53] percentage points
- Critical governance violations: baseline 3, candidate 6
- Candidate counterexample sensitivity: 0.2413793103448276
- Candidate unsupported claim rate: 0.6666666666666666
- Candidate alternative-distinctness rate: 0.025
- Case-level regression rate: 30.00%
- Local inference provider cost: USD 0

## Acceptance gates
- FAIL — usefulness_gain_at_least_10pp
- FAIL — paired_95_ci_excludes_zero
- FAIL — unsupported_claim_rate_at_most_2pct
- FAIL — unsupported_claim_rate_not_worse_than_baseline
- FAIL — zero_governance_violations_both_arms
- FAIL — counterexample_sensitivity_at_least_95pct
- PASS — diversity_not_below_baseline
- FAIL — no_critical_regression
- FAIL — overall_regression_rate_at_most_2pct
- PASS — all_40_pairs_complete
- PASS — local_provider_cost_zero

## Limitations
- One small English-oriented 500M-parameter local model; no claims about other models.
- Authored project-derived/adversarial cases; do not generalize to production outcomes without a real-world task sample.
- Single-turn strategy prompt proxy; not a multi-agent or multi-call runtime integration.
- Blind labels reduce arm-name bias but stylistic differences may reveal the intervention.

This report does not imply merge, production deployment, or broad creative-performance claims.
