# HG AGENTIC INTELLIGENCE EVOLUTION — NATIVE-FIRST

**Status:** Native rubric implemented and pushed to candidate PR; production technical acceptance remains **BLOCKED**; **NOT_RELEASED**.

## Candidate / preservation

- Repository: `OAI-GIANG/HG2`
- PR: https://github.com/OAI-GIANG/HG2/pull/21
- Candidate branch: `stt/hg-agentic-intelligence-g1-20261017`
- Candidate commit at authoring time: `0a1a5e97d57cdee68b696866e29dc0fb07562ec6`
- Canonical base: `9d83a113ccdf1aeda656e494593fa55b9078c803`
- PR state last verified: OPEN / DRAFT / NOT MERGED.
- Canonical branch unchanged. No deploy/release performed.

## Delivered

- `hg/native_criteria.py`: authored HG-native rubric v1.0.0, 16 criteria, total weight 100, 7 C0 critical gates.
- `scripts/hg-native-evaluate`: emit rubric or evaluate explicitly supplied observations.
- `docs/HG_NATIVE_INTELLIGENCE_CRITERIA_V1.md`: specification, methodology, loop, validation and remaining gates.
- `tests/test_native_criteria.py`: negative tests for schema, score weights, CP0 separation, missing evidence, critical failure precedence, duplicate/unknown status, and release never authorized.
- `tests/test_native_improvement_plan.py` and `tests/testdata/hg-native-improvement-plan.v1.json`: eight controlled experiment hypotheses with baselines/candidates explicitly NOT_RUN.
- `evidence/HG-NATIVE-FIRST-20261017/`: rubric JSON, strict suite log, manifest, this status report.

## Validation

On connected Termux / Android ARM64, Python 3.14.6, SQLite 3.53.4:

`PYTHONDONTWRITEBYTECODE=1 python -W error::ResourceWarning -m unittest discover -s tests -v`

Result: **169 tests passed, 0 failed, exit code 0**. Strict full-suite log SHA-256: `67fe7c74b21d374ffe92a6b183e22ceb43636fd1c790b47f095a9b5cbbffe07c`.

Rubric schema validation: 16 criteria, weights=100, C0 gates=7. Empty observations evaluate to BLOCKED. A C0 failure dominates missing tests. Even complete input observations do not authorize release. Digests are not authenticated evidence.

## Boundaries and unresolved gates

- Historical CP0 original criteria: `BLOCKED_INPUT`; new rubric explicitly says `NOT_CLAIMED` and does not wait for CP0 to progress.
- Existing 26 V2.1 fixtures are unchanged and remain synthetic / `NOT_RUN`.
- Production trust roots for actor, approval, capability and evidence: BLOCKED.
- Live natural-language model E2E: NOT_ACCEPTED.
- Criterion oracles need independent calibration/held-out semantic review; current tests verify evaluator wiring and fail-closed rules, not intelligence quality.
- Target-device abrupt power-loss test: NOT_RUN.
- Runtime provenance, backup/restore, rollback, side-effect and full production acceptance: BLOCKED.
- After push, GitHub API confirmed PR head `0a1a5e97d57cdee68b696866e29dc0fb07562ec6` and canonical base unchanged; no hosted CI run appeared yet (`gh run list` empty and PR checks temporarily reported none). Recheck hosted CI at exact final HEAD before considering CI accepted.

## Disposition

Native-first implementation step is committed/pushed for review. Overall mission is not closed because mandatory production gates remain unresolved. Do not merge, deploy or release while blocked.
