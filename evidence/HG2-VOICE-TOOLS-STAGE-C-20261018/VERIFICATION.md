# Stage C — whisper.cpp adapter verification

- Base: canonical `hg-genesis` `9d83a113ccdf1aeda656e494593fa55b9078c803`; work is isolated to `tools/voice` plus this evidence directory on `stt/hg2-voice-tools-design-20261018`.
- Existing local artifact inventory was restricted to the prior voice-engine cache. No artifacts were downloaded in Stage C.
- Upstream source: `https://github.com/ggml-org/whisper.cpp.git`, commit `0c7be696371069e0baa2515ed7aa08d5a5473aa6`. Repository LICENSE identifies MIT; license SHA-256 recorded in `whispercpp-smoke.json`.
- Local executable SHA-256: `6ee09f5f5ac8767bb96e2def475af2d73f6e53b19f4653665035c7fec1587422`.
- Local tiny model SHA-256: `be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21`, 77,691,713 bytes. Model-weight licensing must be reviewed separately before redistribution.
- Upstream public JFK WAV, 352,078 bytes, processed locally in 3.574 seconds; output matched the expected English sentence. No personal recording or microphone used.
- Adapter validates PCM WAV, bounded size/duration, executable/model SHA-256, uses `subprocess.run(..., shell=False)` with timeout, and emits stable errors. It contains no HTTP client, download code, or remote fallback.
- Tests: 18 Voice Tools tests passed; the full repository suite passed 26 tests, both under `-W error::ResourceWarning`. Coverage includes fake adapter success, invalid WAV, timeout, missing model, digest mismatch, max duration and no-network/no-shell behavior.
- Stage C did not modify `manifest.json` or `hg/`; no model download, microphone access, runtime integration, merge, or deployment.
- Limits: smoke test is English only. Vietnamese accuracy, RAM/thermal/battery performance and model-weight redistribution terms remain unverified. Release remains blocked.
