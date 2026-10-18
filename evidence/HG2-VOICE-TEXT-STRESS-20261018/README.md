# HG2 Vietnamese synthetic text stress suite

- Fixture source: `tools/voice/hg_voice/text_stress.py`
- Test coverage: `tools/voice/tests/test_text_stress.py`
- Cases: 30 deterministic, hand-authored synthetic text pairs.
- Generator seed: `20261018`.
- Scope: text normalization, WER/CER aggregation, and observable difference categories only.
- Explicit status: `DIAGNOSTIC_ONLY_NOT_ACCEPTANCE`.

No audio, microphone, model, network, or external corpus was used. Values in `report.json` describe only the chosen synthetic text pairs and scoring policy; they are not evidence of acoustic ASR quality, general Vietnamese performance, corpus admission, or release readiness.
