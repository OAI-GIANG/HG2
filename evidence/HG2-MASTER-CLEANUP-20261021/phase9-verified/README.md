# HG2 Model Gateway Exact-Output Normalization — Evidence

- Implementation commit: `71c7aa95700817f5fba32544d6fe0e0ba2463171`
- HTTP route test commit: `07aa9492a95514324e01a12a5f3ee3d717c82ae6`
- Candidate source manifest SHA-256: `70ad9b4f5e614584e71875d312f62523d9d62690e28304c7aa3528a97a8f5b3b`
- Unit tests: 11/11 pass (`model-gateway-unit-tests.log`)
- Real local provider smoke: exact token returned after a narrow one-key JSON-envelope normalization (`real-local-model-smoke.json`)
- HTTP route integration: 1/1 pass with a deterministic local fake provider; validates exact answer, hash provenance, `PARTIAL`/`RESPONSE_ONLY`, same-key replay, one provider call, and state integrity (`http-route-integration-test.log`)
- Candidate startup health/provenance: PASS (`candidate-startup-health.json`)
- Active production runtime: still commit `fcc561ae919b64572c5a9b549d5664b7fbfd4676`; no restart or deployment.
- Status: `TESTED_NOT_DEPLOYED`. The direct candidate-server POST was not executed; no request was sent. The in-process HTTP route test is the alternative integration evidence.

The normalizer only unwraps a provider JSON object with exactly one `answer` key when the query contains a recognized explicit English/Vietnamese exact-output contract and the nested string equals the expected literal. Mismatches and objects with extra keys remain unchanged. The manifest records raw provider-answer and normalized-answer hashes separately.
