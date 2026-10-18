# HG2 Vietnamese Speech Intelligence — Research & Design V1

**Status:** DESIGN / NOT RELEASED
**Scope:** standalone HG2 Voice Tools; no core runtime or manifest integration.
**Reference material:** user-provided `VieNeu-TTS-main.zip`; research only, not a code or dataset dependency.

## 1. Design intent

HG should learn useful engineering principles from Vietnamese speech tooling without copying its architecture or treating a TTS project as an ASR benchmark. HG's differentiator is an evidence-first, Vietnamese-aware evaluation loop: data admission, deterministic text normalization, task-specific scoring, error diagnosis, provenance, and fail-closed acceptance.

## 2. Transferable principles observed in the reference archive

The archive's README and code describe explicit audio/text pairing, single-speaker constraints for one fine-tuning path, clip-duration checks, phonemization aligned with inference normalization, audio encoding and speaker embeddings, and a guard against a repeated terminal code artifact. These are useful examples of validating assumptions at data boundaries and checking known failure signatures before training.

The archive also separates inference modes, configuration and examples. HG can learn from explicit interfaces and bounded pipelines, but must not inherit provider assumptions, hidden network/model acquisition, or the reference project's training pipeline as a runtime dependency.

## 3. HG-native architecture

### A. Evidence-gated corpus admission

Each corpus is represented by a metadata-only admission record with: corpus ID/version, source URL or supplied-file digest, acquisition date, declared license, audio/transcript rights status, speaker consent status where applicable, permitted purpose, split policy, language/locale labels, and reviewer decision. Missing or ambiguous rights are `BLOCKED`, never silently accepted. The admission record must not include raw speech or personal identifiers.

### B. Deterministic Vietnamese text contract

Keep the current scorer's NFC + casefold + whitespace normalization as a versioned baseline. Preserve Vietnamese diacritics and punctuation by default; do not strip tone marks or punctuation to improve scores. Any alternate normalization is a separately named diagnostic view and must never replace the primary score. Record normalizer version and corpus digest with every result.

### C. Task-separated evaluation

- **ASR:** audio input and trusted reference transcript; report corpus-level WER and CER, sample count, skipped/error count, and null scores when denominators are empty. Break down errors by word/character, diacritic-sensitive substitutions, punctuation, and locale only when labels are valid.
- **TTS:** text input and generated audio; WER/CER are not direct audio-quality metrics. Evaluate text fidelity only after an independently qualified ASR pass, and report it as a proxy. Audio quality, intelligibility, speaker similarity, latency, and resource cost require distinct methods and explicit limitations.
- **Text-only scorer tests:** validate metric implementation with synthetic examples. Never present these as model accuracy or corpus acceptance.

### D. Failure diagnosis loop

For each accepted run: freeze input manifest and hashes; execute locally/offline; preserve model/runtime identity and command/config; score with the pinned normalizer; group errors by deterministic categories; produce a report that recommends the next test, not an automatic production mutation. Re-run the same inputs and compare exact artifacts before accepting a change.

### E. Device feasibility gate

Before considering on-device execution, measure existing installed engine only (no model download): executable/model hashes, startup, wall time, peak memory if reliably measurable, thermal/battery observations only if safely exposed, and failure codes. Missing observability remains `UNKNOWN`; never fabricate measurements. Resource feasibility is independent of language accuracy.

## 4. Novel HG contribution

The proposed **Vietnamese Error Atlas (VEA)** is a deterministic diagnostic layer over accepted ASR results. It groups mismatches into auditable buckets without altering the primary WER/CER: diacritic/tone-mark difference, punctuation-only difference, whitespace/tokenization difference, lexical substitution, insertion, deletion, and locale-tagged slice (only when source labels are trustworthy). Each bucket includes count, denominator, and examples only when the corpus license and privacy policy permit excerpts. Otherwise emit aggregate counts only.

VEA does not claim phonetic causality from text differences alone. It labels observable differences and keeps causal hypotheses separate from measured evidence. No model fine-tuning or self-learning is automatic.

## 5. Data and licensing findings — preliminary

The supplied archive contains an Apache-2.0 `LICENSE` for the repository code. The archive also contains WAV/TXT example pairs and an SRT example. The repository code license alone does not establish that each embedded voice recording, transcript, pretrained checkpoint, speaker identity, or third-party asset is cleared for HG benchmark use. Individual data/model rights and consent remain unverified; therefore the supplied samples are not admitted as acceptance data in this revision.

## 6. Acceptance gates

1. `G0_SOURCE`: source/digest and repository snapshot recorded.
2. `G1_RIGHTS`: code, audio, transcript, model-weight and speaker-consent terms assessed separately.
3. `G2_CORPUS`: approved purpose, manifest, splits, labels and transcript quality documented.
4. `G3_ENGINE`: exact existing local engine/model identity verified; no implicit network fallback.
5. `G4_REPRODUCIBILITY`: command/config/input digest and output evidence captured.
6. `G5_METRICS`: primary WER/CER computed on valid ASR reference pairs; no synthetic smoke test presented as acceptance.
7. `G6_REVIEW`: limitations and failures disclosed; PR remains Draft until explicitly authorized otherwise.

Any missing required gate yields `BLOCKED`; it does not block independent design/test work that does not use unapproved data.

## 7. Non-goals and constraints

- No raw audio or transcripts from this archive are copied into HG2.
- No personal recording, microphone capture, or new model/data download.
- No changes to `manifest.json`, core runtime, or provider authority.
- No inference/benchmark on these sample recordings in this research task.
- No merge, deploy, or release claim.

## 8. Next implementation increments

1. Add unit tests for VEA categories using synthetic text fixtures only.
2. Add a metadata-only corpus admission schema and fail-closed validator.
3. Add report serialization with run IDs and SHA-256 references.
4. Later, if a properly licensed and approved Vietnamese ASR corpus becomes available, run a real benchmark and publish measured WER/CER with all gates and limitations.

## 9. Evidence classification

- **Observed in archive:** repository Apache-2.0 license file; documentation/code describe audio-text metadata, single-speaker fine-tuning path, clip-duration validation and a terminal-code anomaly guard; sample WAV/TXT/SRT assets exist.
- **Design proposal:** HG-native corpus admission, Vietnamese Error Atlas, task-separated metrics and evidence gates described above.
- **Not verified:** rights for embedded speech assets/transcripts and model weights; real Vietnamese ASR accuracy; on-device performance; TTS quality; production readiness.
