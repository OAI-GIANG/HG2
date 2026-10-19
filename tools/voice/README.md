# HG2 Voice Tools — on-demand local speech utilities

Standalone, on-demand CLI. It is not imported by HG runtime modules. Core orchestration uses Python standard library only; optional speech engines are invoked explicitly.

From repository root:

```sh
PYTHONPATH=tools/voice python -m hg_voice doctor
PYTHONPATH=tools/voice python -m hg_voice engines
PYTHONPATH=tools/voice python -m hg_voice verify PATH --sha256 HEX_DIGEST
PYTHONPATH=tools/voice python -m hg_voice tts --text-file NOTICE.txt --output NOTICE.wav --voice vi --play
PYTHONPATH=tools/voice python -m hg_voice play NOTICE.wav
PYTHONPATH=tools/voice python -m unittest discover -s tools/voice/tests -v
```

`doctor` and `engines` are read-only: no network, model download, microphone, or package installation. The example manifest is metadata only; no model is included. Verify only hashes a user-specified local file. TTS reads UTF-8 text from a file, passes it to the local engine through stdin (not process arguments), creates and validates a PCM WAV, calculates SHA-256, and never writes spoken text to audit logs.

Engine readiness is per-engine: eSpeak NG is an available-if-installed local fallback for Vietnamese announcement audio; its quality is not accepted merely because synthesis and playback work. Whisper.cpp requires a separately installed, hash-pinned executable/model. VieNeu Nano remains blocked until Termux inference and Vietnamese quality are verified. Android system TTS remains optional and unverified; the Termux:API CLI by itself is insufficient without its companion Android app. Do not describe that path as guaranteed offline.

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


## Local Vietnamese TTS — eSpeak NG fallback

The Stage E fallback supports Vietnamese synthesis without a neural model download or a remote provider. It uses the espeak-ng executable and its installed voice data, with vi (Northern), vi-vn-x-central, and vi-vn-x-south selectable. The generated output is a local PCM WAV; default rate is 135 and supported rate values are 90–220.

Example:

~~~sh
PYTHONPATH=tools/voice python -m hg_voice tts \
  --text-file /path/to/notice.txt \
  --output /path/to/notice.wav \
  --voice vi --rate 135 --play
PYTHONPATH=tools/voice python -m hg_voice play /path/to/notice.wav
~~~

The text-file argument is required so spoken content does not appear in the command's argument list. The default refuses to overwrite an existing WAV; --overwrite is a separate explicit opt-in. Input is limited to 10,000 characters; WAV output is bounded and validated for PCM format, channels, sample rate, frame count and duration. Temporary output files use owner-only permissions and are removed on failure. The optional play flag invokes the local play-audio utility without a shell; it does not use termux-tts-speak or an online fallback.

**Acceptance boundary:** a zero process exit, valid WAV, SHA-256, and successful local-player exit prove that the local pipeline ran and the player accepted the file. They do not establish naturalness, pronunciation accuracy, accessibility suitability, or that a person actually heard/approved the audio. Human listening and a predefined Vietnamese quality review are still required before any production quality claim. VieNeu Nano remains a separate blocked research candidate; this adapter does not mark it ready.


## Upstream references and distribution boundary

- eSpeak NG upstream overview and license statement: https://github.com/espeak-ng/espeak-ng
- eSpeak NG Vietnamese voice/dialect identifiers: https://github.com/espeak-ng/espeak-ng/blob/master/docs/languages.md
- Termux eSpeak package build recipe, source version/hash, and package license metadata: https://github.com/termux/termux-packages/blob/master/packages/espeak/build.sh
- Termux local audio playback utility (OpenSL ES; upstream repository states Apache-2.0): https://github.com/termux/play-audio

**Supply-chain note:** the current Termux package recipe lists GPL-2.0 package metadata, while the eSpeak NG upstream README describes its project as GPL-3.0-or-later. Treat this as a license-metadata discrepancy requiring exact source/package verification before redistributing or bundling the executable or voice data. HG2 does not commit, vendor, or redistribute either executable or voice files; it invokes the locally installed Termux package. A production bundle requires a separate license review.
