# HNI-30 evaluator integration note — V1

**Status:** design-only; oracle not approved for runtime; no HNI-30 runtime tests executed.

## Scope separation

This evaluator is bound to the current 30-criterion source (HNI-01..HNI-30) and the separate hni30.evaluator-oracle.v1 oracle. It does not reuse or reinterpret the historical/native 16-criterion rubric in hg/native_criteria.py. The old historical 26-criterion source is outside this evaluator's scope; no equivalence claim is made.

## Evaluator contract

- Validates the 30 criterion IDs and names against the source document, oracle version, and source SHA-256.
- Requires per-case input/output/trace/environment artifact references and recomputes their SHA-256 values before accepting a runtime observation.
- Rejects path traversal and symlinks in evidence paths.
- Requires runtime build identity, full commit SHA, source-tree/runtime/config/environment digests, non-secret provider/model/endpoint identity, criterion oracle version, assertions, and a review record.
- Missing observations are NOT_RUN; missing prerequisites or invalid/missing evidence are BLOCKED; executed but undecidable cases are INCONCLUSIVE.
- Critical failures cannot be averaged away. A passing aggregate never authorizes release.
- Synthetic cases are always labeled SYNTHETIC_ONLY; they cannot become HG runtime verdicts.
- Runtime PASS/FAIL requires both an approved oracle and independently trusted callbacks for bundle/build provenance and review-record verification. The shipped CLI deliberately has no such callback and therefore fails closed for runtime acceptance.

## Test meaning and limits

The unit suite creates synthetic positive and negative contract records for each of the 30 criterion IDs. The resulting PASS/FAIL values are harness contract outcomes, not capability scores or HG results. This tests schema, evidence binding, digest checking, path safety, status aggregation and fail-closed behavior; it does not judge model semantics or establish HG capability. Human semantic scoring rules, reviewer agreement analysis, runtime provenance and an approved trust root remain separate gates.

## External methodology references

- Anthropic, Demystifying evals for AI agents (2026-01-09): https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- NIST, Accelerating the Adoption of Software and AI Agent Identity and Authorization (2026-02-05): https://csrc.nist.gov/pubs/other/2026/02/05/accelerating-the-adoption-of-software-and-ai-agent/ipd
- SLSA provenance v1.2 and verification: https://slsa.dev/spec/v1.2/provenance and https://slsa.dev/spec/v1.2/verifying-artifacts
- The Update Framework (TUF), rollback/freeze protections and root rotation: https://theupdateframework.github.io/specification/v1.0.36/

These sources inform the design; they do not attest HG or satisfy its production gates.
