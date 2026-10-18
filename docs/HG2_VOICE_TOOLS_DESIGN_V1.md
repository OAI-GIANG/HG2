# HG2 Voice Tools — Design V1 (GitHub-first)

**Disposition:** DESIGN BASELINE CANDIDATE — DOCUMENTATION ONLY — NOT RELEASED
**Canonical base:** `hg-genesis` at `9d83a113ccdf1aeda656e494593fa55b9078c803`
**Working branch:** `stt/hg2-voice-tools-design-20261018`
**Runtime integration:** none
**Installation / model download in this task:** none

## 1. Decision

Build a small, independently callable **Voice Tools** suite in repository `OAI-GIANG/HG2`, rather than reinstalling or depending on the deleted HG application. A user invokes one specific operation when needed; no daemon, wake-word listener, or background microphone process is enabled.

The tool is a utility, not an authority. Its output is untrusted user content and must never automatically become an HG command, approval, identity proof, or tool invocation. This design does not add voice to HG's canonical runtime, alter the existing runtime contract, or add speech-model dependencies to the base `hg` package.

## 2. Proposed command contract

Future interface (names are illustrative until the implementation PR):

- `hg-voice doctor` — report available commands, model manifests, disk/RAM estimate, privacy boundary, and engine compatibility. Read-only; no download.
- `hg-voice stt <audio-file>` — transcribe a user-selected local file. Output goes to stdout or an explicitly named output file. No automatic provider fallback.
- `hg-voice record --seconds N` — record only after an explicit per-call consent prompt/flag; hard bounded duration; then call STT. No always-on recording.
- `hg-voice tts <text-file>` — synthesize/read selected text using an explicitly selected engine.
- `hg-voice install-engine <engine-id>` — future, opt-in install operation after displaying exact model size, hash source, license and destination; never implicit from `doctor`, `stt` or `tts`.
- `hg-voice engines` — list registered adapters and processing boundaries.

Commands should be invokable through a short natural-language request to STT, e.g. “dùng Voice Tools đọc văn bản X”, without requiring the whole HG runtime to be installed. STT can translate the request into the precise CLI operation, report its result and preserve the operation's evidence. The repository cannot by itself guarantee that a future assistant session has terminal access; the invocation contract remains explicit.

## 3. Separation and repository scope

Target layout after an implementation is approved:

```
tools/voice/
  README.md
  pyproject.toml or stdlib-only launcher (choice after packaging tests)
  hg_voice/
    __main__.py
    cli.py
    policy.py
    audio.py
    manifest.py
    adapters/
      whisper_cpp.py
      termux_tts.py
      vieneu_nano.py        # only after compatibility gate passes
  tests/
    test_voice_*.py
  models.example.json       # no model weights or user paths
  evidence/
```

This is a proposed layout, not a statement that these files already exist. Keep `manifest.json`'s core `hg` dependencies empty. Do not import the voice package from `hg/__init__.py`, `hg/phone_runtime.py`, or `hg/edge.py`. No VPS, relay, model gateway, API key, or live HG state is needed for the local tool.

The tool should be isolated as a command/package and only later, if specifically approved, be called from another HG component. It must not write canonical history, approvals, or agent state.

## 4. Engine choices from evidence

### STT: whisper.cpp (preferred local candidate)

- Upstream describes whisper.cpp as a C/C++ inference implementation and provides an Android sample app; its Android guidance suggests starting with tiny or base models. The current upstream memory table lists tiny at approximately 75 MiB on disk and ~273 MB memory, base approximately 142 MiB and ~388 MB; these are upstream reference values, not a measurement on this phone.
- Actual device evidence already exists outside the canonical repository: whisper.cpp was compiled in a private Termux cache on Android/aarch64, and the HG adapter candidate invoked it successfully with the upstream public English `jfk.wav` sample (11 seconds; one observation approximately 2.13 seconds). This is only an end-to-end smoke test, not a Vietnamese quality benchmark.
- Upstream reference: https://github.com/ggml-org/whisper.cpp and https://github.com/ggml-org/whisper.cpp/tree/master/examples/whisper.android
- Code license: upstream repository declares MIT. A specific model file and any redistributed binary still require its own pinned digest and license/source review.
- Selection rule: begin benchmark comparison with tiny and base; choose based on Vietnamese WER/CER, real-device latency, memory and thermal/battery tests. Do not infer tiny will be sufficiently accurate from the English smoke test.

### TTS: VieNeu-TTS v3 Nano (preferred research candidate, NOT yet compatible/accepted)

- Current model card labels v3 Nano PREVIEW, identifies Vietnamese on-device/edge use, ONNX CPU runtime, 24 kHz output, approximately 280 MB runtime artifacts and lower quality than Turbo. Those are upstream claims that can change by model revision.
- References: https://huggingface.co/pnnbao-ump/VieNeu-TTS-v3-Nano and https://github.com/pnnbao97/VieNeu-TTS
- Published model card license is Apache-2.0. Before implementing downloads or redistribution, pin exact model revision/file hashes and check licenses for every bundled model, preset voice asset, dictionary, and code dependency separately.
- The actual Termux compatibility attempt has NOT completed inference. ONNX Runtime imports, but the VieNeu SDK environment lacks PyYAML; a PyYAML source build attempt failed at PEP-517 backend setup. A prior `soxr` pip build attempt failed during stub generation with a missing Android Python symbol. The upstream `sea-g2p` native library was separately built through its C ABI, but the adapter shim is experimental and is not part of HG2.
- Therefore no TTS model should be marked installed/ready, and no voice quality or offline claim is allowed yet. Do not clone a real person's voice in V1.

### Optional system TTS: Termux:API

- A future adapter may call `termux-tts-speak`, but it requires the Termux:API companion app and compatible device engine.
- The Android/system TTS engine may use external services. Classify its processing boundary as `DEVICE_SYSTEM_OR_UNKNOWN`; disable by default unless the user explicitly allows that boundary for this call and the selected engine's behavior has been explained. Never represent it as guaranteed-offline.
- Upstream script reference: https://github.com/termux/termux-api-package/blob/master/scripts/termux-tts-speak.in

### Explicitly not selected yet

Do not pull Fish Speech, GPT-SoVITS, IndexTTS, Chatterbox, VibeVoice, PyTorch/torchaudio, or multiple overlapping TTS engines into the first version. They add model/license/dependency/resource uncertainty before the minimum use case is proven. Re-evaluate only against a measured acceptance need.

## 5. Dependency and installation policy

- Core CLI: prefer Python standard library only. Engine adapters are optional extras or explicit executables.
- STT runtime: a pinned whisper.cpp executable plus a pinned local model file. Do not build or download these during ordinary STT calls. Build/download only through an explicit installer command in a separate cache/model directory.
- TTS runtime: model provider is unresolved. VieNeu requires ONNX Runtime, NumPy, audio I/O/resampling packages, a Hugging Face downloader, PyYAML in the observed SDK path, and a working Vietnamese phonemizer/native interface. Exact minimum versions and an Android-compatible packaging route must be proven before declaring the adapter ready.
- No PyTorch GPU stack in the phone-first baseline. No binary, model, SDK, voice asset, cache, or generated audio is committed to Git.
- Dependencies and model weights are separate supply-chain items. Each release must contain a dependency inventory, upstream commit/revision, license identifier, artifact SHA-256, download origin, and reproducible setup notes.
- Downloads must use a verified HTTPS origin, fixed artifact path/revision, size limit and SHA-256. Do not run arbitrary model-repository scripts. Model downloads are explicit, never automatic fallback.

## 6. Privacy and security contract

1. No always-on microphone, wake-word listener, background recorder, or automatic launch at Termux startup.
2. Every recording call requires explicit consent, uses a short configurable duration cap (initial default 15 seconds; maximum 30 seconds), size cap, and a visible indication of start/stop.
3. Never upload audio or transcript automatically. Default processing is local-only. If an optional provider crosses the device boundary, block unless a policy opt-in and per-call consent both exist.
4. Raw audio is ephemeral in an owner-only private scratch directory. Delete it on normal exit and failure. Do not store audio/transcripts in HG history by default.
5. Do not place audio/text in command-line arguments, URLs, telemetry, logs or exception strings. Pass spoken text through stdin or protected pipes. Logs contain operation ID, engine ID, phase, duration, byte/character counts and stable error codes only.
6. Treat recognized text as untrusted input. Display/edit/confirm it before passing it to any agent. Voice is not authentication, authorization or approval proof. No direct call from STT adapter to HG ToolPlane.
7. Fail closed for missing permission, unknown processing boundary, digest mismatch, malformed audio, size limit, timeout, audit failure or unavailable model. Do not fall back to a remote service silently.
8. Never collect voice samples for training or cloning without explicit informed permission and a documented lawful right to use them.
9. `doctor` is read-only and must never install packages, download a model, request the microphone, or print credentials.

## 7. Performance and capacity gates

No universal RAM or latency promise can be made from a single sample. Before selecting defaults, capture the phone's memory availability and free disk at benchmark time, then test a fixed permissioned Vietnamese set under controlled conditions.

| Measurement | Required protocol | Pass condition (initial proposal) |
|---|---|---|
| STT accuracy | At least 50 permissioned Vietnamese utterances spanning Northern/Central/Southern accents, quiet and moderate noise; human-checked reference transcripts | Report WER and CER per slice; threshold set before selecting model |
| STT speed | At least 10 repeat runs per model/duration, cold and warm | Median and p95 latency; target initially ≤ real-time factor 1.0 for short clips |
| Peak memory | Sample process RSS while loading and transcribing | Must leave agreed Android/HG headroom; exact MB threshold chosen after phone baseline |
| Thermal/battery | Repeated workload with device temperature/power observations | No sustained thermal throttling or runtime interruption in accepted workload |
| TTS quality | Human listening review of ≥30 Vietnamese phrases including numbers, dates, names, punctuation and long text | Intelligibility/pronunciation score and defects recorded; no quality claim without review |
| TTS speed | ≥10 fixed phrases, cold model load and warm synthesis separately | Report RTF/TTFA median and p95; agree threshold before acceptance |
| Offline behavior | Disable network after artifacts are pinned; run repeated requests | Must complete fully offline for an adapter described as LOCAL |
| Cleanup/privacy | Success, timeout, malformed input and process termination cases | No raw recording remains; no transcript/audio in logs |
| Repeatability | Pin source/model/hash/config and rerun | Same artifact identities; expected output text/audio quality variation documented |

Upstream figures such as whisper.cpp tiny's disk/RAM estimates and VieNeu Nano's ~280 MB artifacts/desktop real-time factor are planning references, not these acceptance results.

## 8. Failure behavior and interface guarantees

Stable error families: `MICROPHONE_CONSENT_REQUIRED`, `MICROPHONE_API_UNAVAILABLE`, `MODEL_NOT_INSTALLED`, `ARTIFACT_DIGEST_MISMATCH`, `INVALID_AUDIO`, `AUDIO_SIZE_LIMIT`, `TRANSCRIPTION_TIMEOUT`, `TRANSCRIPTION_FAILED`, `TTS_BACKEND_UNAVAILABLE`, `NONLOCAL_PROCESSING_DISABLED`, `OUTPUT_WRITE_FAILED`.

Exit-code outline:
- `0`: operation completed and output was made available.
- `2`: invalid argument or incompatible option.
- `3`: required adapter/model/API not configured.
- `4`: consent or privacy policy denied.
- `5`: engine failure/timeout.
- `6`: artifact/provenance verification failed.

A failed STT call must not create transcript output or invoke another provider. A failed TTS call must preserve the input text and return an actionable stable code. Do not expose engine stderr in an ordinary user-facing error.

## 9. Staged implementation plan

1. **Stage A — design (this document):** freeze boundaries, initial engines, commands, risks and acceptance gates.
2. **Stage B — stdlib CLI foundation:** implement parser, `doctor`, manifest/hash verification, engine registry, redacted audit records and fake-adapter tests; no model downloads.
3. **Stage C — STT adapter:** add whisper.cpp execution with pinned binary/model digests and strict bounded WAV handling; test on public fixtures and then permissioned Vietnamese evaluation clips.
4. **Stage D — microphone adapter:** integrate Termux:API only after the companion-app permission and capture/cleanup test is available.
5. **Stage E — TTS adapter:** fix/replace the VieNeu native phonemizer packaging route in isolated experiments, then test a pinned Nano model; add optional system TTS only as a clearly nonlocal/unknown path.
6. **Stage F — packaging and evidence:** pinned installs, checksum manifest, negative tests, performance report, on-demand invocation guide and Draft PR.
7. **Stage G — separate approval:** only after acceptance is complete may any calling path into the live HG runtime be proposed. It requires a separate scope review.

No stage may silently advance if its evidence is missing. Do not merge, deploy, install to the phone's active runtime, modify canonical runtime architecture, or claim release from a documentation-only PR.

## 10. Current readiness snapshot

| Item | Status | Evidence |
|---|---|---|
| Canonical branch and SHA | VERIFIED by GitHub ref/tree read | `hg-genesis` = `9d83a113ccdf1aeda656e494593fa55b9078c803` |
| Canonical source has existing voice module | NO voice/audio/STT/TTS paths in its 63-file tree | Recursive Git tree query at canonical SHA |
| Local Termux checkout safe to edit | NO — detached `4d97c34d...`, many modified/deleted/untracked files | Read-only `git status`; preserved untouched |
| Prior candidate branch | PR #25 Draft, base canonical, no review; its head is not canonical | GitHub PR metadata |
| whisper.cpp ARM64 smoke test | PASS, public English sample only | Private cache evidence; not committed/canonical |
| Vietnamese STT accuracy | NOT RUN | Requires permissioned Vietnamese evaluation set |
| Real microphone | NOT RUN; Termux microphone command was absent in last check | Device command inventory |
| VieNeu Nano inference | BLOCKED/NOT RUN | YAML/PyYAML packaging errors; no Nano model downloaded |
| System TTS Vietnamese quality/offline | NOT RUN | Requires companion app/engine check |
| RAM/thermal/battery benchmark | NOT RUN | No sustained device benchmark |
| Runtime integration or release | NOT APPROVED / NOT RELEASED | Outside current design-only scope |

## 11. Research references reviewed

- whisper.cpp Android example and model guidance: https://github.com/ggml-org/whisper.cpp/tree/master/examples/whisper.android
- whisper.cpp upstream memory table and quantization notes: https://github.com/ggml-org/whisper.cpp
- VieNeu-TTS v3 Nano model card, status, quality caveats, and reported size: https://huggingface.co/pnnbao-ump/VieNeu-TTS-v3-Nano
- VieNeu-TTS SDK/dependency and Nano documentation: https://github.com/pnnbao97/VieNeu-TTS
- Termux:API TTS command interface: https://github.com/termux/termux-api-package/blob/master/scripts/termux-tts-speak.in

## 12. Review outcome

**Recommended:** proceed with Stage B on an isolated branch after this design document is reviewed. Keep TTS engine selection provisional until real Termux TTS inference works and Vietnamese quality/resource evidence exists. The most valuable immediate deliverable is a stable on-demand tool surface with local-first STT and an honest, fail-closed TTS capability report—not a large combined stack.

**Status: DESIGN ONLY — IMPLEMENTATION NOT STARTED IN THIS BRANCH — NOT RELEASED.**


## 13. Stage E result — local Vietnamese announcement fallback (2026-10-18)

**Implemented on the working branch:** tools/voice/hg_voice/adapters/espeakng.py adds an explicit eSpeak NG adapter for Vietnamese WAV synthesis and local playback. It is independent of the core HG runtime and does not modify manifest.json, hg/, approvals, or runtime services.

- Voice choices are explicitly allowlisted: vi, vi-vn-x-central, vi-vn-x-south; text is supplied via stdin rather than as a child-process argument.
- The adapter uses shell=False, timeout and text/audio size bounds; validates PCM WAV properties; hashes the final file; writes owner-only output; refuses overwrite unless explicitly requested; cleans failed temporary outputs.
- The optional playback step requires local play-audio. It never falls back to Android system TTS or a network service.
- Termux package runtime was exercised on Android/aarch64 with eSpeak NG and play-audio; one generic non-personal Vietnamese announcement synthesized to valid WAV and the local player returned exit code 0. The artifact and digest are recorded in the dated execution evidence. A separate Termux:API system-engine query timed out because the Termux:API companion app was not installed; that optional route remains unavailable and is not used.
- Automated Voice Tools suite: 63 tests pass on the device after adding adapter, CLI and safety tests.

**Limitations:** this is a functional local announcement path, not a neural/naturalness acceptance. No trained Vietnamese quality set or independent human listening review was performed. Do not infer pronunciation quality from process success. VieNeu Nano stays blocked-unverified; no model was downloaded. No microphone was accessed, no personal audio used, no runtime integration/deploy performed, and canonical hg-genesis was not changed. The work remains on this PR's draft branch pending acceptance review.


## 14. External references and eSpeak NG license gate

The implementation uses the installed Termux package and the installed eSpeak NG voice data, not a copied engine binary or downloaded speech model.

- eSpeak NG upstream and its stated license: https://github.com/espeak-ng/espeak-ng
- Upstream language/dialect identifiers: https://github.com/espeak-ng/espeak-ng/blob/master/docs/languages.md
- Termux package recipe, source version and SHA-256 metadata: https://github.com/termux/termux-packages/blob/master/packages/espeak/build.sh
- Termux play-audio implementation and license: https://github.com/termux/play-audio

**License gate:** the Termux package recipe currently labels the package GPL-2.0, whereas the upstream eSpeak NG README states GPL-3.0-or-later. This discrepancy is not resolved here. No engine binary or voice data is committed to HG2; redistribution/bundling remains blocked until the exact package/source licensing is verified. The local tested command path does not itself establish legal clearance for a future bundled release.
