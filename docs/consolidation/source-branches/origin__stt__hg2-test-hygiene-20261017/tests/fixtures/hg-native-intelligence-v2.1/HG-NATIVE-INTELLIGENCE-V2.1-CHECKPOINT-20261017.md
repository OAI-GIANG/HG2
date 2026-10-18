# HG-NATIVE-INTELLIGENCE V2.1 — EXECUTION CHECKPOINT

Date: 2026-10-17 (Termux / Android aarch64)
Scope: synthetic fixture/oracle package only; no HG capability or runtime test.

## Finding and root cause

- Finding: `build_v21.py`, `complete_oracles_v21.py`, and `validate_v21.py` embedded an absolute Termux home path. This made package tooling dependent on one machine/path and prevented reliable execution after relocation.
- Root cause: script roots were string literals instead of being derived from each script's location.
- Correction: derive source/destination/package roots from `Path(__file__).resolve()`. No fixture semantics or expected results were changed.

## Evidence / verification

- Regression: `python -m unittest -q test_fixture_package_v21.py` — PASS, 12 tests.
- Static/semantic validator: `python validate_v21.py` — PASS; 26 fixtures, 26 unique IDs, 26/26 oracle specs, HNIT 30/30, XN 6/6; arithmetic, digest recomputation, aggregation truth table PASS; no errors.
- Portability positive test: validator invoked by absolute script path while current directory was `$HOME` — PASS.
- Negative test: temporary copy with HNIF2-26 removed — validator correctly failed with `fixture_count_or_ids`; temporary copy removed after test.
- Integrity: `sha256sum -c SHA256SUMS-V2.1.txt` — PASS for every listed package artifact.
- Preservation boundary: V1/V2 and CP0 files were not modified by this patch. Validator preservation check is presence/size only, not byte-for-byte historical proof.
- Synthetic-only boundary: every fixture remains `NOT_RUN`; no HG implementation/runtime behavior was executed or inferred.

## External methodology references

- OpenAI Evals guidance describes evaluation datasets and explicit testing criteria: https://developers.openai.com/api/docs/guides/evals
- NIST AI RMF Measure guidance recommends documenting test sets, metrics, tools, uncertainty, and results: https://airc.nist.gov/airmf-resources/airmf/5-sec-core/

These references inform evaluation methodology only. They do not establish the provenance or authority of the historical original 26 criteria; that source remains unresolved.

## Repository / release disposition

- Local working package: updated and verified in Termux.
- HG2 canonical baseline observed during read-only inspection: `cdebaeed014371f033f14352f552c6d0d4e69198` (`hg-genesis`).
- No V2.1 package path was found in HG2 at inspection time. No commit, push, PR, merge, deploy, or production mutation was made; no verified implementation integration target was established for this fixture-only closure.
- Package task: CLOSED — fixture/oracle design and package-level validation only.
- HG implementation acceptance: NOT_RUN. HG release: NOT_RELEASED.
