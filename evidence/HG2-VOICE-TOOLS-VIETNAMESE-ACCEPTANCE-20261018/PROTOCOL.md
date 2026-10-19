# Vietnamese ASR acceptance protocol — prepared, not executed

## Status

`PROTOCOL_READY_DATASET_BLOCKED` — no approved Vietnamese audio/reference corpus was present in this task, so no WER/CER quality result is claimed. Do not use personal recordings, collect new recordings, download models, or upload audio. The scorer consumes transcript pairs only and has no audio/network capability.

## Dataset admission gate

Before scoring, require a documented source/license or explicit informed consent that permits local ASR evaluation; record corpus/version, provenance URL or approval reference, license/consent scope, permitted retention, and SHA-256 for each audio file and reference manifest. Exclude personal/identifiable recordings unless specific consent explicitly covers this purpose. Keep the dataset outside Git and do not commit audio, transcripts, personal metadata, or identifiers. Use opaque utterance IDs.

## Protocol

1. Freeze one approved Vietnamese test set and its gold references before inference. Split by speaker/source where applicable; do not tune using the test set. Document regional/dialect coverage, speaking conditions, duration, sampling rate, and corpus composition.
2. Run the already-installed, hash-pinned local engine only; do not download or substitute a model. Use explicit Vietnamese language setting and the same audio preprocessing for every item. Record engine commit, executable/model hashes, command/config, device/OS/Python versions, and run date.
3. Run inference locally/offline. Do not retain raw audio or full hypotheses in evidence by default; keep protected local outputs and publish only aggregate metrics and non-identifying run metadata. Never upload the corpus.
4. Normalize reference and hypothesis using Unicode NFC, Unicode casefold, and trim/collapse whitespace. Current scorer retains punctuation and Vietnamese diacritics. Freeze this policy before benchmark execution; if punctuation-insensitive scoring is needed, define a separate versioned policy rather than silently changing this one.
5. Compute corpus-level WER = total word edit distance / total reference words and CER = total Unicode-code-point edit distance / total reference code points. Do not average utterance percentages. Empty reference denominator yields `null` and is counted explicitly. Inspect a sample of errors only within the approved data access boundary.
6. Report overall WER/CER and, when the corpus license and sample size permit, stratify by region/accent, noise, duration, and speaker group without exposing identities. Include utterance count, word/character denominators, exclusions, failures, latency distribution, peak RAM, thermal/battery observations, and uncertainty intervals where practical.
7. Predeclare acceptance thresholds and test-set eligibility before the run. Do not invent thresholds or claim acceptance without an approved corpus and actual execution evidence. Compare to a documented baseline on the same split and normalization.

## Scorer smoke tests

`tools/voice/evaluate_wer_cer.py` scores a UTF-8 JSONL file whose records contain only `reference` and `hypothesis` strings. It performs no audio processing, model invocation, networking, or uploads. Example with synthetic text only:

```sh
printf '%s\n' '{"reference":"Xin chào thế giới","hypothesis":"Xin chào thế giới"}' > /tmp/hg-voice-metrics-smoke.jsonl
PYTHONPATH=tools/voice python tools/voice/evaluate_wer_cer.py /tmp/hg-voice-metrics-smoke.jsonl
```

This synthetic smoke test verifies metric calculation only; it is not Vietnamese ASR evidence and must not be counted as acceptance data.

## Current blocker

`APPROVED_VIETNAMESE_CORPUS_NOT_PROVIDED`. Stage C's public JFK sample is English and cannot support Vietnamese acceptance. No new model, recording, or dataset is fetched as part of this protocol preparation.
