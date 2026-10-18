# HG2 Voice Intelligence — Corpus Rights Gate

- Review date: 2026-10-18
- Repository: `OAI-GIANG/HG2`
- Branch: `stt/hg2-voice-tools-design-20261018`
- Status: `BLOCKED — NOT RELEASED`

## Decision

No existing corpus in the HG2 checkout is both present locally and approved for this benchmark. No real WER/CER run was performed, no dataset payload was downloaded, and no audio was played or sent through inference. The synthetic evaluator smoke test is not corpus acceptance evidence.

## Candidate findings

1. **Mozilla Common Voice Vietnamese, dataset card version 23.0** — the public dataset card declares CC-0 and says users must not attempt to identify speakers and must not re-host/re-share the dataset. The card reports audio clips, transcripts, speaker counts, and validated hours. This is a promising candidate, but the payload is not present in the HG2 checkout, no local asset hashes exist, and the specific dataset/asset terms plus speaker-consent/privacy fit for HG2's benchmark purpose have not been independently reviewed. Decision: `BLOCKED_NOT_ADMITTED`.
   Source: <https://dev.datacollective.mozillafoundation.org/datasets/cmflnn484oaiy1nwkq2dp76ig>

2. **VLSP ASR datasets** — the official VLSP resources page instructs users to complete, sign, and email a data-user agreement to obtain datasets. No signed agreement, approved-purpose record, or dataset payload is present in the checkout. Challenge pages describe task constraints and metrics, not a blanket license to use data outside their access terms. Decision: `BLOCKED_NOT_ADMITTED`.
   Sources: <https://vlsp.org.vn/resources>, <https://vlsp.org.vn/vlsp2021/eval/asr>, <https://vlsp.org.vn/vlsp2022/eval/asr>

3. **VieNeu-TTS-main.zip** — the existing archive audit records an Apache-2.0 license for repository code, while embedded audio, transcripts, speaker consent, and model-weight rights remain unverified. Decision: `BLOCKED_NOT_ADMITTED`.
   Prior evidence: `evidence/HG2-VOICE-INTELLIGENCE-RESEARCH-20261018/ARCHIVE_AUDIT.json`.

## Evidence and constraints

- Detailed machine-readable candidate-by-candidate matrix: `CORPUS_RIGHTS_GATE.json`.
- No corpus/audio payload or signed rights approval was found among tracked HG2 files.
- No download, model download, audio playback, inference, merge, or deploy occurred.
- No manifest or core-runtime file changed.
- Real Vietnamese ASR WER/CER: `NOT_RUN_BLOCKED_NO_APPROVED_LOCAL_CORPUS`.
- Dataset SHA-256 manifest: not created because no approved corpus payload was available.
- PR #26 must remain `OPEN · DRAFT`.
