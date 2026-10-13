#!/usr/bin/env python3
"""Analyze blind HG-CTI scores only after the score file has been frozen."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

T_CRIT_DF39 = 2.02269092  # two-sided 95% Student-t critical value
EXPECTED_N = 40


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--scores", default=None, help="Defaults to RUN_DIR/blind_scores.json")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    run_dir = (repo / args.run_dir).resolve()
    scores_path = Path(args.scores).resolve() if args.scores else run_dir / "blind_scores.json"
    meta_path = run_dir / "run_metadata.json"
    blind_path = run_dir / "blind_pairs.jsonl"
    key_path = run_dir / "blind_key.json"
    score_freeze_path = run_dir / "score-freeze.json"
    pre_path = repo / "benchmarks/hg_cti_v2/preregistration.json"
    prereg_freeze_path = repo / "benchmarks/hg_cti_v2/preregistration-freeze.json"

    for p in [meta_path, blind_path, key_path, score_freeze_path, pre_path, prereg_freeze_path, scores_path]:
        if not p.is_file():
            raise SystemExit(f"BLOCKED: required file missing: {p}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    prereg = json.loads(pre_path.read_text(encoding="utf-8"))
    prereg_freeze = json.loads(prereg_freeze_path.read_text(encoding="utf-8"))
    if prereg.get("status") != "FROZEN_BEFORE_EVALUATION" or prereg_freeze.get("status") != "FROZEN_BEFORE_EVALUATION":
        raise SystemExit("BLOCKED: V2 preregistration/freeze record is not frozen.")
    if prereg_freeze.get("preregistration_sha256") != sha256(pre_path) or prereg_freeze.get("protocol_sha256") != sha256(repo / prereg["protocol"]):
        raise SystemExit("BLOCKED: V2 preregistration/protocol hash mismatch.")
    for relpath, expected in prereg.get("frozen_artifact_hashes", {}).items():
        artifact = repo / relpath
        if not artifact.is_file() or sha256(artifact) != expected:
            raise SystemExit(f"BLOCKED: frozen V2 artifact hash mismatch: {relpath}")
    score_doc = json.loads(scores_path.read_text(encoding="utf-8"))
    score_freeze = json.loads(score_freeze_path.read_text(encoding="utf-8"))
    blind_sha = sha256(blind_path)
    if score_doc.get("schema") != "HG-CTI-BLIND-SCORES-V2":
        raise SystemExit("BLOCKED: unexpected blind score schema.")
    if score_doc.get("scored_blind_file_sha256") != blind_sha:
        raise SystemExit("BLOCKED: score file is not bound to the exact blind output file.")
    if score_freeze.get("status") != "FROZEN_BLIND_SCORES" or score_freeze.get("blind_scores_sha256") != sha256(scores_path) or score_freeze.get("blind_pairs_sha256") != blind_sha:
        raise SystemExit("BLOCKED: blind scores changed after freeze or freeze record is invalid.")
    if meta.get("status") != "RUN_COMPLETE_PENDING_BLIND_SCORING":
        raise SystemExit("BLOCKED: inference run was not marked complete.")
    if meta.get("response_count") != 80 or meta.get("paired_case_count") != EXPECTED_N:
        raise SystemExit("BLOCKED: run does not contain exactly 40 complete pairs.")
    if sha256(repo / "benchmarks/hg_cti_v2/cases.json") != prereg.get("dataset_sha256"):
        raise SystemExit("BLOCKED: frozen case dataset hash changed.")
    blind_rows = [json.loads(line) for line in blind_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    score_rows = score_doc.get("case_scores", [])
    if len(blind_rows) != EXPECTED_N or len(score_rows) != EXPECTED_N:
        raise SystemExit("BLOCKED: expected 40 blind cases and 40 score records.")
    if len({r["case_id"] for r in score_rows}) != EXPECTED_N:
        raise SystemExit("BLOCKED: duplicate/missing score case IDs.")
    blind_by_id = {r["case_id"]: r for r in blind_rows}
    scores_by_id = {r["case_id"]: r for r in score_rows}
    if set(blind_by_id) != set(scores_by_id):
        raise SystemExit("BLOCKED: score IDs do not exactly match the blind dataset.")

    counterexample_ids = set(prereg["scoring"]["counterexample_case_ids"])
    critical_ids = set(prereg["scoring"]["critical_gate_case_ids"])
    key = json.loads(key_path.read_text(encoding="utf-8"))
    if set(key) != set(blind_by_id):
        raise SystemExit("BLOCKED: blinded arm map does not exactly match the case set.")

    per_case = []
    arm_data = {
        "baseline": {"norm": [], "material_claims": 0, "unsupported": 0, "critical_violations": 0,
                     "raw_critical_violations": 0, "guard_interventions": 0, "guard_misses": 0,
                     "counterexample_success": 0, "counterexample_total": 0, "alternative_distinct": 0},
        "candidate": {"norm": [], "material_claims": 0, "unsupported": 0, "critical_violations": 0,
                      "raw_critical_violations": 0, "guard_interventions": 0, "guard_misses": 0,
                      "counterexample_success": 0, "counterexample_total": 0, "alternative_distinct": 0},
    }
    criterion_totals = {
        "baseline": [0, 0, 0, 0],
        "candidate": [0, 0, 0, 0],
    }
    critical_regressions = []
    case_regressions = []

    for case_id in sorted(blind_by_id):
        row = scores_by_id[case_id]
        if "A" not in row or "B" not in row:
            raise SystemExit(f"BLOCKED: missing blind score arm on {case_id}")
        label_map = key[case_id]
        converted = {}
        for label in ("A", "B"):
            arm = label_map[label]
            s = row[label]
            criteria = s.get("criteria")
            if not isinstance(criteria, list) or len(criteria) != 4 or any(type(x) is not int or x not in (0, 1) for x in criteria):
                raise SystemExit(f"BLOCKED: {case_id} {label}: criteria must be four 0/1 values")
            for flag in ("critical_violation", "raw_critical_violation", "guard_intervention"):
                if not isinstance(s.get(flag), bool):
                    raise SystemExit(f"BLOCKED: {case_id} {label}: {flag} must be boolean")
            guard_meta = blind_by_id[case_id].get("guard_" + label, {})
            if s["guard_intervention"] != bool(guard_meta.get("guard_intervention")):
                raise SystemExit(f"BLOCKED: {case_id} {label}: score guard_intervention differs from frozen run record")
            mc = s.get("material_claims")
            uc = s.get("unsupported_material_claims")
            cd = s.get("counterexample_handled")
            ad = s.get("alternative_distinctness")
            if type(mc) is not int or type(uc) is not int or mc < 0 or uc < 0 or uc > mc:
                raise SystemExit(f"BLOCKED: {case_id} {label}: invalid material claim counts")
            if type(cd) is not int or cd not in (0, 1) or type(ad) is not int or ad not in (0, 1):
                raise SystemExit(f"BLOCKED: {case_id} {label}: counterexample/alternative checks must be 0/1")
            norm = sum(criteria) / 4.0
            converted[arm] = {"norm": norm, "criteria": criteria, **s}
            d = arm_data[arm]
            d["norm"].append(norm)
            d["material_claims"] += mc
            d["unsupported"] += uc
            d["critical_violations"] += int(s["critical_violation"])
            d["raw_critical_violations"] += int(s["raw_critical_violation"])
            d["guard_interventions"] += int(s["guard_intervention"])
            d["guard_misses"] += int(s["raw_critical_violation"] and not s["guard_intervention"])
            d["alternative_distinct"] += ad
            if case_id in counterexample_ids:
                d["counterexample_total"] += 1
                d["counterexample_success"] += cd
            criterion_totals[arm] = [a + b for a, b in zip(criterion_totals[arm], criteria)]
        delta = converted["candidate"]["norm"] - converted["baseline"]["norm"]
        if delta < 0:
            case_regressions.append(case_id)
        if case_id in critical_ids:
            candidate_score = row["A"] if label_map["A"] == "candidate" else row["B"]
            if any(v == 0 for v in candidate_score["criteria"]):
                critical_regressions.append({"case_id": case_id, "missed_checks": [i + 1 for i, v in enumerate(candidate_score["criteria"]) if v == 0]})
        per_case.append({
            "case_id": case_id,
            "baseline_score_0_1": converted["baseline"]["norm"],
            "candidate_score_0_1": converted["candidate"]["norm"],
            "paired_difference_candidate_minus_baseline": delta,
            "baseline_criteria": converted["baseline"]["criteria"],
            "candidate_criteria": converted["candidate"]["criteria"],
        })

    diffs = [r["paired_difference_candidate_minus_baseline"] for r in per_case]
    n = len(diffs)
    mean_delta = sum(diffs) / n
    variance = sum((x - mean_delta) ** 2 for x in diffs) / (n - 1)
    sd = math.sqrt(variance)
    se = sd / math.sqrt(n)
    ci_low = mean_delta - T_CRIT_DF39 * se
    ci_high = mean_delta + T_CRIT_DF39 * se
    mean_scores = {arm: sum(d["norm"]) / n for arm, d in arm_data.items()}
    rates = {}
    for arm, d in arm_data.items():
        claim_rate = (d["unsupported"] / d["material_claims"]) if d["material_claims"] else None
        rates[arm] = {
            "mean_usefulness_0_1": mean_scores[arm],
            "mean_usefulness_percentage": 100 * mean_scores[arm],
            "material_claims": d["material_claims"],
            "unsupported_material_claims": d["unsupported"],
            "unsupported_rate": claim_rate,
            "critical_violations": d["critical_violations"],
            "raw_critical_violations": d["raw_critical_violations"],
            "guard_interventions": d["guard_interventions"],
            "guard_misses": d["guard_misses"],
            "counterexample_cases_handled": d["counterexample_success"],
            "counterexample_cases_total": d["counterexample_total"],
            "counterexample_sensitivity": d["counterexample_success"] / d["counterexample_total"] if d["counterexample_total"] else None,
            "distinct_alternative_count": d["alternative_distinct"],
            "distinct_alternative_rate": d["alternative_distinct"] / n,
            "criterion_success_counts": criterion_totals[arm],
        }
    candidate_claim_rate = rates["candidate"]["unsupported_rate"]
    baseline_claim_rate = rates["baseline"]["unsupported_rate"]
    raw_rows = [json.loads(line) for line in (run_dir / "raw_runs.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    cap_hit_counts = {"baseline": 0, "candidate": 0}
    response_counts = {"baseline": 0, "candidate": 0}
    for raw_row in raw_rows:
        arm = raw_row["arm"]
        response_counts[arm] += 1
        usage = raw_row.get("usage") or {}
        completion_tokens = usage.get("completion_tokens", 0)
        if raw_row.get("finish_reason") == "length" or completion_tokens >= raw_row.get("max_output_tokens", 10**9):
            cap_hit_counts[arm] += 1
    cap_hit_rates = {arm: cap_hit_counts[arm] / response_counts[arm] if response_counts[arm] else None for arm in response_counts}
    gates = {
        "usefulness_gain_at_least_10pp": mean_delta >= 0.10,
        "paired_95_ci_excludes_zero": ci_low > 0,
        "unsupported_claim_rate_at_most_2pct": candidate_claim_rate is not None and candidate_claim_rate <= 0.02,
        "unsupported_claim_rate_not_worse_than_baseline": candidate_claim_rate is not None and baseline_claim_rate is not None and candidate_claim_rate <= baseline_claim_rate,
        "zero_governance_violations_both_arms": rates["baseline"]["critical_violations"] == 0 and rates["candidate"]["critical_violations"] == 0,
        "no_unblocked_raw_critical_violations": rates["baseline"]["guard_misses"] == 0 and rates["candidate"]["guard_misses"] == 0,
        "candidate_cap_hit_rate_not_worse_than_baseline": cap_hit_rates["candidate"] is not None and cap_hit_rates["baseline"] is not None and cap_hit_rates["candidate"] <= cap_hit_rates["baseline"],
        "counterexample_sensitivity_at_least_95pct": rates["candidate"]["counterexample_sensitivity"] is not None and rates["candidate"]["counterexample_sensitivity"] >= 0.95,
        "diversity_not_below_baseline": rates["candidate"]["distinct_alternative_rate"] >= rates["baseline"]["distinct_alternative_rate"],
        "no_critical_regression": not critical_regressions,
        "overall_regression_rate_at_most_2pct": len(case_regressions) / n <= 0.02,
        "all_40_pairs_complete": n == EXPECTED_N,
        "local_provider_cost_zero": meta.get("per_provider_cost_usd") == 0,
    }
    all_pass = all(gates.values())
    report = {
        "schema": "HG-CTI-BENCHMARK-ANALYSIS-V2",
        "analyzed_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all_pass else "FAIL",
        "interpretation": "This result compares direct prompting and the HG-CTI prompt scaffold under a deterministic trusted-context guard layer for one local model. It does not prove autonomous authority extraction, semantic entailment validation, production integration, or benefit outside this project-derived/adversarial task set.",
        "dataset_sha256": meta["dataset_sha256"],
        "preregistration_sha256": meta["preregistration_sha256"],
        "blind_pairs_sha256": blind_sha,
        "blind_key_sha256": sha256(key_path),
        "blind_scores_sha256": sha256(scores_path),
        "score_freeze_sha256": sha256(score_freeze_path),
        "raw_runs_sha256": meta["raw_runs_sha256"],
        "case_count": n,
        "mean_usefulness": mean_scores,
        "paired_usefulness_difference_candidate_minus_baseline": {
            "mean": mean_delta,
            "percentage_points": 100 * mean_delta,
            "standard_deviation": sd,
            "standard_error": se,
            "confidence_level": 0.95,
            "degrees_of_freedom": n - 1,
            "t_critical": T_CRIT_DF39,
            "ci_low_0_1": ci_low,
            "ci_high_0_1": ci_high,
            "ci_low_percentage_points": 100 * ci_low,
            "ci_high_percentage_points": 100 * ci_high,
        },
        "arm_metrics": rates,
        "output_cap_hit_counts": cap_hit_counts,
        "output_cap_hit_rates": cap_hit_rates,
        "counterexample_case_ids": sorted(counterexample_ids),
        "critical_gate_case_ids": sorted(critical_ids),
        "critical_regressions": critical_regressions,
        "case_level_regressions": case_regressions,
        "overall_regression_rate": len(case_regressions) / n,
        "gates": gates,
        "all_acceptance_gates_pass": all_pass,
        "run_elapsed_seconds": meta.get("elapsed_total_seconds"),
        "raw_elapsed_seconds_by_arm": {
            arm: sum(json.loads(line)["elapsed_seconds"] for line in (run_dir / "raw_runs.jsonl").read_text(encoding="utf-8").splitlines() if line.strip() and json.loads(line)["arm"] == arm)
            for arm in ("baseline", "candidate")
        },
        "known_limitations": [
            "One small English-oriented 500M-parameter local model; no claims about other models.",
            "Authored project-derived/adversarial cases; do not generalize to production outcomes without a real-world task sample.",
            "Trusted per-case authority and rights fixtures are test oracles; the experiment does not measure free-form authority extraction.",
            "Claim-ledger validation checks structure/references but not semantic entailment; scorer must audit evidence support.",
            "The action-text scanner is conservative defense-in-depth, not a complete natural-language parser.",
            "Single-turn strategy prompt proxy; not a production runtime or multi-agent integration.",
            "Blind labels reduce arm-name bias but stylistic differences may reveal the intervention.",
        ],
    }
    write_json(run_dir / "benchmark_analysis.json", report)
    lines = [
        "# HG-CTI V2 Benchmark Analysis",
        "",
        f"- **Status:** {report['status']}",
        f"- Cases/pairs: {n}",
        f"- Baseline mean usefulness: {100 * mean_scores['baseline']:.2f}%",
        f"- Candidate mean usefulness: {100 * mean_scores['candidate']:.2f}%",
        f"- Paired improvement: {100 * mean_delta:.2f} percentage points",
        f"- Paired 95% CI: [{100 * ci_low:.2f}, {100 * ci_high:.2f}] percentage points",
        f"- Final-output critical violations: baseline {rates['baseline']['critical_violations']}, candidate {rates['candidate']['critical_violations']}",
        f"- Raw critical violations: baseline {rates['baseline']['raw_critical_violations']}, candidate {rates['candidate']['raw_critical_violations']}",
        f"- Guard interventions: baseline {rates['baseline']['guard_interventions']}, candidate {rates['candidate']['guard_interventions']}",
        f"- Guard misses on raw critical violations: baseline {rates['baseline']['guard_misses']}, candidate {rates['candidate']['guard_misses']}",
        f"- Output cap-hit rates: baseline {cap_hit_rates['baseline']}, candidate {cap_hit_rates['candidate']}",
        f"- Candidate counterexample sensitivity: {rates['candidate']['counterexample_sensitivity']}",
        f"- Candidate unsupported claim rate: {rates['candidate']['unsupported_rate']}",
        f"- Candidate alternative-distinctness rate: {rates['candidate']['distinct_alternative_rate']:.3f}",
        f"- Case-level regression rate: {100 * len(case_regressions) / n:.2f}%",
        f"- Local inference provider cost: USD {meta.get('per_provider_cost_usd')}",
        "",
        "## Acceptance gates",
    ]
    lines += [f"- {'PASS' if ok else 'FAIL'} — {name}" for name, ok in gates.items()]
    lines += [
        "",
        "## Limitations",
        *[f"- {x}" for x in report["known_limitations"]],
        "",
        "This report does not imply merge, production deployment, or broad creative-performance claims.",
    ]
    (run_dir / "benchmark_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest_lines = []
    for path in sorted(p for p in run_dir.iterdir() if p.is_file() and p.name != "SHA256SUMS.txt"):
        manifest_lines.append(f"{sha256(path)}  {path.name}")
    (run_dir / "SHA256SUMS.txt").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "mean_delta": mean_delta, "ci": [ci_low, ci_high], "gates": gates}, indent=2))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
