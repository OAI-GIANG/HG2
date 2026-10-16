# Benchmark V1 reliability note — non-acceptance evidence

Date: 2026-10-14

Status: **EXPLORATORY ONLY / NOT VALID AS PREREGISTERED ACCEPTANCE EVIDENCE**.

The V1 scorer/registration was iterated while inspecting its first results. The fixture namespace/root and some expected edge/dependent records were corrected after observed failures; the final V1 iteration also lowered clean-case edge/dependent recall thresholds from 1.0 to 0.75. Therefore the final V1 result's `benchmark_pass` field is not an admissible preregistered acceptance conclusion. This note intentionally preserves that history instead of presenting the V1 output as a valid pass.

Preserved exploratory files:
- `HG2_CI_BENCHMARK_ITERATION_EXPLORATORY_V1_REGISTRATION.json` SHA-256: `c4e893cde1cbdbcc27bec9c165abeb9beed37b10c6df307c07ff0af89fc0dc6b`.
- `HG2_CI_BENCHMARK_ITERATION_EXPLORATORY_V1_RESULT.json` SHA-256: `1ea5d88ae70b8c40a15e3425a947896f7e0bb8e75aa19d0a66ab86561ab738a1`.
- Earlier V1 iterations had failing metrics (including edge and impact recall); they are development diagnostics only.

V2 is a separate registration and result. Its fixture hashes, literal expected static edges/dependents, expected incomplete-coverage states, scorer and thresholds were frozen in `HG2_CI_GROUND_TRUTH_REGISTRATION_V2.json` before its first V2 execution. V2 requires 1.0 precision and recall for the registered static graph and known dependents, exact coverage/impact status, and 100% fail-closed recall over the five incomplete cases. No V2 expected records or thresholds were changed after V2 was run.
