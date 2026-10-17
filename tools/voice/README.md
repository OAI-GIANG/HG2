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
