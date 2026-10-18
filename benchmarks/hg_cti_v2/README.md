# HG-CTI V2 Benchmark Harness

V2 is a new guarded-pipeline evaluation. It does not modify V1 case files, prompts, scores, manifests, or run output.

## Files

- `cases.json`: V1 scenario prompts and four case checks preserved byte-for-content, plus V2 prompt hashes and trusted guard-context fixtures.
- `guard_policy.json`: authoritative per-case authority and provenance context used by the post-generation guard. It is never sent to the model and cannot be overridden by model-generated fields.
- `prompts.json`: exact common system prompt and the baseline/candidate suffixes.
- `response-schema.json`: required structured response contract.
- `model-provenance.json`: model/runtime identity record; revalidate hashes and local health immediately before any run.
- `run_benchmark.py`: local-only paired inference, structured-output validation, P0 guard integration, raw/final output capture, blind-pair generation, and run manifest.
- `scoring-rubric.md`: frozen blind scoring method with four rationales per output and claim-span/evidence ledger.
- `freeze_scores.py`: validates completeness and freezes blind scores without reading the arm key.
- `analyze_scores.py`: computes paired results and all preregistered gates.
- `preregistration.json` and `preregistration-freeze.json`: created only after implementation and tests are final; runner refuses to start if hashes differ.

## Guard contract

The runner passes only each case's natural-language prompt to the model. Authority and rights states come from the trusted per-case fixture, not from the model output. The model emits structured action/reuse/claim fields. The runner validates the response schema, action authority, trusted rights, secret/action text patterns, and claim span/evidence references. If the response is malformed or the gate rejects it, the user-visible benchmark output becomes a standardized blocked response; the raw output remains recorded for diagnostics.

This is a benchmark guard contract, not a claim that arbitrary natural-language authority can be inferred perfectly. The trusted per-case fixtures are test oracles. Claim-ledger validation checks structure and references, not semantic entailment; the blind scorer must audit claim support.

## Execution gate

Do not run this harness until `preregistration.json`, `preregistration-freeze.json`, the protocol, all frozen artifact hashes, and the test suite are finalized and verified. A run requires exactly 40 paired cases / 80 responses, local loopback inference, the recorded model/runtime hashes, and a new non-existing output directory. No selective reruns are allowed. Preserve incomplete run evidence and, if a full paired rerun is justified by infrastructure failure, run the complete frozen case set in a separate directory and record the incident.

V2 is not a release approval. No merge or deploy follows from inference completion alone.
