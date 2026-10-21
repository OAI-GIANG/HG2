# Model Gateway Output-Contract Normalizer — Revised Plan

Recorded: 2026-10-21T07:10:48.741262+00:00

## Why the first prompt-only change was insufficient

The original live `/api/ask` request returned an explanatory refusal. Under the clarified prompt, a direct `ModelGateway.ask()` call returned `{"answer":"HG2_RUNTIME_IDEMPOTENCY_CHECK"}`: the nested value was correct but wrapped in JSON. A separate CLI reproduction returned the raw token. These are distinct observed failure modes. Prompt changes alone are not a reliable exact-output guarantee, so the revised fix only normalizes a single-key JSON envelope when its nested value matches a clearly extracted exact-output contract; explanatory refusals remain unchanged and fail the contract.

## Revised bounded implementation

Add a deterministic postcondition in the existing `hg/model_gateway.py` only for a narrowly recognized explicit exact-output instruction:

1. Recognize a bounded set of explicit English/Vietnamese exact-output forms ending in “and nothing else” / “không thêm gì khác”.
2. Extract the requested literal conservatively; if the pattern is ambiguous or too long, do nothing.
3. If the provider answer already equals the expected literal, leave it unchanged.
4. Otherwise, parse JSON only if the entire provider answer is valid JSON. Unwrap only an object with exactly one key `answer`, whose string value exactly equals the expected literal.
5. If the nested answer differs, the object has extra keys, or the user requested a different format, leave the provider output untouched.
6. Record raw provider response hash, raw provider-answer hash, normalized-answer hash, and normalization status in the result manifest. This keeps provenance honest.

No tool execution, state writes, model switching, new dependency, endpoint change, or deployment is included.

## Ten-angle critique

1. Architecture: no new module; normalization belongs at the provider response boundary.
2. Implementation: pure helper, bounded regexes, stdlib `re`/`json` only.
3. Testing: unit tests for exact match, envelope unwrap, mismatch, extra keys, no explicit contract, and Vietnamese phrasing; direct local-model smoke.
4. Security: cannot execute anything; only removes an envelope when the exact user-requested literal is matched byte-for-byte after JSON decoding.
5. Reliability: ambiguous requests fail closed to the original provider answer; no fuzzy matching.
6. Performance: negligible parsing overhead only for explicit exact-output requests.
7. Maintainability: small pure helper and transparent manifest status.
8. Adversarial: an attacker cannot cause arbitrary output replacement unless the model returns the exact requested literal inside the expected one-key envelope.
9. UX: fixes the observed formatting defect without claiming the model independently complied.
10. Long-term: response normalization remains separate from `RESPONSE_ONLY`/execution evidence semantics.

## Acceptance

- Unit tests pass.
- The same real local ModelGateway request returns the exact token.
- Negative tests prove mismatched content and unrelated JSON are not rewritten.
- Live state hashes remain unchanged; active runtime is not restarted.
- Only `hg/model_gateway.py` and `tests/test_model_gateway.py` are tracked-source changes.

## Decision boundary

If the exact-output parser needs broad natural-language heuristics or breaks non-exact-output requests, revert it. Do not change `brain.status` or claim `SUCCESS` based on output normalization.


## Execution result

- `test_model_gateway.py`: 11/11 PASS.
- Real `ModelGateway.ask()` call to the existing local Qwen2.5-1.5B server returned the exact requested token after `UNWRAPPED_EXACT_ANSWER_JSON_ENVELOPE` normalization. The raw provider answer hash and normalized answer hash differ and are recorded in the manifest.
- Four live state file hashes were unchanged; the call bypassed `/api/ask` and `PhoneRuntime`.
- Full isolated candidate HTTP-server E2E was not run. No live restart, deployment, commit or push was performed.
- Disposition: `TESTED_NOT_DEPLOYED`; do not call the production runtime fixed until candidate HTTP integration and release provenance gates pass.


## HTTP route integration alternative

- The direct candidate-server POST attempt was blocked before the request was sent, so it is not counted as executed. The temporary candidate server was stopped and its temporary state removed.
- To avoid stopping at that block, a new isolated HTTP route test was added to `tests/test_server.py` and run alone: `test_server.ServerTests.test_ask_normalizes_exact_output_envelope_and_replays` — 1/1 PASS. It uses a deterministic local fake OpenAI-compatible provider, calls the real `HGHTTPServer` `/api/ask` route, verifies exact answer normalization, raw/normalized hash separation, `PARTIAL`/`RESPONSE_ONLY` honesty, same-key replay, one provider call, no state changes on replay, and state integrity.
- Together with 11/11 `ModelGateway` tests and the real local-model smoke, this verifies the response normalizer and API route path in isolation. It does not prove a production rollout; live runtime remains on `fcc561`.
