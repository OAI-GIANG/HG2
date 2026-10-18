# HG2 Voice Tools — Stage B foundation

Standalone, on-demand CLI. It is not imported by HG runtime modules. Core code uses Python standard library only.

From repository root:

```sh
PYTHONPATH=tools/voice python -m hg_voice doctor
PYTHONPATH=tools/voice python -m hg_voice engines
PYTHONPATH=tools/voice python -m hg_voice verify PATH --sha256 HEX_DIGEST
PYTHONPATH=tools/voice python -m unittest discover -s tools/voice/tests -v
```

`doctor` and `engines` are read-only: no network, model download, microphone, or package installation. `models.example.json` is metadata only; no model is included. `verify` only hashes a user-specified local file. No audio/transcript content is accepted or logged by this Stage B foundation.

The engines listed are candidates, not ready-to-use capabilities. Whisper.cpp requires a separately installed, hash-pinned executable/model; VieNeu Nano is blocked until Termux inference and Vietnamese quality are verified; Android system TTS has an unknown processing boundary and must not be described as guaranteed offline.

## Local whisper.cpp adapter (Stage C)

`hg_voice.adapters.whispercpp.WhisperCppAdapter` accepts an explicit local executable and model path with expected SHA-256 values. It only accepts bounded, uncompressed PCM WAV inputs (maximum 30 seconds / 32 MiB), launches the local process without a shell and enforces a timeout. It does not download artifacts or use a network fallback. A model is considered installed only when the configured path exists and its digest matches. No executable or model is bundled in this repository.

The adapter smoke test in `evidence/HG2-VOICE-TOOLS-STAGE-C-20261018/` used the upstream public English JFK sample. It does not establish Vietnamese quality or authorize redistribution of model weights.

## HG-native Vietnamese text stress suite (synthetic, non-acoustic)

`hg_voice.text_stress` provides a deterministic, hand-authored synthetic suite for exercising the text scoring and error-atlas path. It covers diacritics, Unicode normalization, punctuation, whitespace/token boundaries, numbers and units, names/place spellings, code-switching, context-sensitive homophones, insertions/deletions and empty hypotheses/references.

From repository root:

```sh
PYTHONPATH=tools/voice python -m hg_voice.text_stress
PYTHONPATH=tools/voice python -m hg_voice.text_stress --output /tmp/hg-voice-text-stress.json --jsonl /tmp/hg-voice-synthetic-pairs.jsonl
```

The suite uses seed `20261018`; the fixture and report are reproduced under `evidence/HG2-VOICE-TEXT-STRESS-20261018/`. Case IDs and per-case SHA-256 values make fixture changes visible. Scoring uses the same NFC + casefold + collapsed-whitespace policy as the existing metrics implementation.

**Boundary:** these strings are synthetic and hand-authored, not a representative language benchmark. This tool does not generate/process audio or invoke an ASR model. Its WER/CER only exercise the text evaluation path and are explicitly marked `DIAGNOSTIC_ONLY_NOT_ACCEPTANCE`; they must not be quoted as acoustic recognition performance or release acceptance evidence.
