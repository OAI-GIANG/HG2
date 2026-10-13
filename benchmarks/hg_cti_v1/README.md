# HG-CTI local benchmark V1

The runner uses the already-present local `llama.cpp` server/model on the authorized Android/Termux device. It does not install packages, download model weights, call a remote inference provider, touch production state, or alter the canonical branch.

## Frozen inputs

- Protocol: `docs/HG_CTI_BENCHMARK_PROTOCOL_V1.md`
- Dataset: `cases.json` (40 cases, 4 criteria each)
- Pre-registration: `preregistration.json`
- Dataset SHA-256: `748670044763f4dce9604c0d3e0ddebe1ea62dfbfc87bdcd6a04eace8b1b90d6`
- Model: local `SmolVLM2-500M-Video-Instruct-Q8_0.gguf`, SHA-256 `6f67b8036b2469fcd71728702720c6b51aebd759b78137a8120733b4d66438bc`, metadata license Apache-2.0.
- Inference server: existing `llama.cpp`, source commit `781dbc5ac98921dbdb5e5b2ec5b7a50960e937d4`, loopback-only `127.0.0.1:19831`.

## Experimental comparison

Both arms receive identical task facts and common answer-format/privacy/governance instructions, and use one call per case with the same model, endpoint, context limit (1024), seed per case, temperature (0.2), top-p (0.9), output cap (160 tokens), timeout, and local zero-provider-cost accounting. The intervention is the system prompt: baseline solves directly; candidate is given the HG-CTI stages (OBSERVE, DIVERGE, CHALLENGE, DISCRIMINATE, VALIDATE, DISTILL). Call order is randomized and A/B labels are randomized separately for blind rubric scoring.

This is an **operational prompt-scaffold benchmark**. It does not imply that the pure metadata evaluator `hg/creative_assimilation.py` generates content by itself, and it does not integrate a model into production HG runtime.

## Run

From the HG2 repository root, with the pre-existing local server already healthy:

```sh
python3 benchmarks/hg_cti_v1/run_benchmark.py \
  --repo . \
  --endpoint http://127.0.0.1:19831 \
  --model-path "$HOME/.cache/hg-local-vision-20261010/models/SmolVLM2-500M-Video-Instruct-Q8_0.gguf" \
  --server-binary "$HOME/.cache/hg-local-vision-20261010/build-termux-arm64/bin/llama-server" \
  --out-dir evidence/HG-CTI-20261013/benchmark-run-local-001
```

The runner refuses to use a non-loopback endpoint, a changed dataset, a different model digest, a missing model alias, or an existing output path. It stops and marks the run incomplete on any failed inference; it does not silently drop cases.

## Evidence sequence and current status

1. The inference run completed 40/40 pairs (80/80 responses) with no failed inference requests; provider cost was USD 0. Raw outputs and blind pairs are hashed.
2. Local-model auto-scoring failed to produce a valid complete score set. That failed attempt is preserved in `evidence/HG-CTI-20261013/benchmark-scoring-attempt.json` and was not used as the final scores.
3. STT then scored the 40 A/B pairs against the pre-registered case-specific rubric without opening `blind_key.json`. The 40-case score file passed schema/hash validation and was frozen before the analyzer read the A/B-to-arm key. The freeze records `approval_gate: false` and `signature: null`.
4. Analysis result: **FAIL**. Mean usefulness was 35.0% for baseline and 30.0% for candidate; paired difference was -5.0 percentage points, 95% CI [-13.53, +3.53] points. Unsupported-claim rates were 62.70% baseline and 66.67% candidate. Critical violations were 3 baseline and 6 candidate. Counterexample sensitivity was 48.28% baseline and 24.14% candidate. Twelve of 40 pairs regressed on usefulness.
5. Failed gates include usefulness gain >=10pp, paired 95% CI excluding zero, unsupported claims <=2% and no worse than baseline, zero governance violations, counterexample sensitivity >=95%, no critical regression, and overall regression <=2%. Diversity non-regression, pair completeness, and zero provider cost passed.
6. The comparison is limited to a single-call HG-CTI prompt scaffold versus direct prompting of one local 500M model on this project-derived adversarial case set. It does not establish production benefit or prove the standalone metadata evaluator generates content.
7. Keep PR in Draft/NO-GO. Do not change cases/rubric or selectively rerun an arm to improve the result. No signatures or independent-review gate are used; no merge or deployment is authorized by this benchmark.

No independent-review/signature gate is used. Scoring is a predeclared measurement procedure, not a separate authority that approves the work. Never claim production deployment from this benchmark.
