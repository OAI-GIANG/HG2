# HG2 — Voice Announcement Result

**Date:** 2026-10-18
**Disposition:** LOCAL FUNCTIONAL PATH VERIFIED · QUALITY ACCEPTANCE PENDING
**Repository:** OAI-GIANG/HG2
**Branch:** stt/hg2-voice-tools-design-20261018
**Canonical base:** hg-genesis at 9d83a113ccdf1aeda656e494593fa55b9078c803

## Outcome

An on-demand Vietnamese announcement can now be synthesized and played locally on the connected Android/Termux device through the hg-voice command. The implementation uses the installed eSpeak NG engine, with no model download, microphone capture, audio upload, remote fallback, or HG core-runtime integration.

The optional Android system-TTS adapter was not used: com.termux.api was not installed and its CLI probe timed out. The unused Termux:API CLI package was removed. The working fallback is eSpeak NG plus Termux play-audio.

## Device acceptance evidence

- CLI synthesis exit code: 0
- Playback command exit code: 0
- PCM WAV parser: PASS
- FFmpeg decode/validation exit code: 0
- SHA-256 verification: PASS
- Voice: vi-vn-x-central
- Sample rate: 22050 Hz; channels: mono; sample width: 16-bit
- Duration: 8.053 seconds; size: 355168 bytes
- Audio SHA-256: f0fb4aecab152b1da1d763705c3b4f57cf44fce18cd1699d33d4c32a558f8cd6
- Shared device file: ~/storage/shared/Download/HG2-Voice-Announcement-Test.wav
- Shared copy SHA-256 matches the private source.
- Automated Voice Tools tests: 63 passed, 0 failed with -W error::ResourceWarning.
- Python compileall: PASS; git diff --check: PASS.

Machine-readable run details and exact artifact metadata are in EXECUTION.json.

## Scope and limits

- The local path is functional for generating and handing a WAV to the device's player.
- No person independently confirmed audibility or approved Vietnamese pronunciation/naturalness. An exit code cannot establish that a person heard or liked the output.
- Therefore Vietnamese TTS quality remains NOT_ASSESSED; this is not a production-quality acceptance.
- VieNeu Nano remains blocked/unverified. This task did not download a model or attempt to mark that model ready.
- The original PR remains Draft pending quality review. No merge, deployment, or change to canonical hg-genesis was performed.


## External research and licensing gate

References reviewed:
- eSpeak NG upstream (feature overview and stated license): https://github.com/espeak-ng/espeak-ng
- eSpeak NG language/dialect list: https://github.com/espeak-ng/espeak-ng/blob/master/docs/languages.md
- Termux eSpeak package source/build metadata: https://github.com/termux/termux-packages/blob/master/packages/espeak/build.sh
- Termux play-audio (local OpenSL ES player): https://github.com/termux/play-audio

The Termux package recipe labels its eSpeak package GPL-2.0, whereas the eSpeak NG upstream README states GPL-3.0-or-later. This discrepancy is unresolved and blocks bundling/redistribution until the exact source and package licensing is verified. HG2 does not vendor the engine or voice data.
