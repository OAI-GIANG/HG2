#!/usr/bin/env python3
"""Freeze a blinded rubric score file without opening the label-to-arm key."""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_manifest(run_dir: Path) -> None:
    manifest = run_dir / "SHA256SUMS.txt"
    if not manifest.is_file():
        raise SystemExit("BLOCKED: run manifest missing before score freeze.")
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        target = run_dir / relative
        if not target.is_file() or digest(target) != expected:
            raise SystemExit(f"BLOCKED: run artifact failed manifest verification: {relative}")


def write_manifest(run_dir: Path) -> None:
    lines = []
    for path in sorted(item for item in run_dir.iterdir() if item.is_file() and item.name not in {"SHA256SUMS.txt", "blind_key.json"}):
        lines.append(f"{digest(path)}  {path.name}")
    (run_dir / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    args = ap.parse_args()
    run_dir = Path(args.run_dir).resolve()
    blind_path = run_dir / "blind_pairs.jsonl"
    score_path = run_dir / "blind_scores.json"
    freeze_path = run_dir / "score-freeze.json"
    if freeze_path.exists():
        raise SystemExit("BLOCKED: a score freeze already exists; do not overwrite frozen scoring.")
    verify_manifest(run_dir)
    if not blind_path.is_file() or not score_path.is_file():
        raise SystemExit("BLOCKED: blind pairs or score file missing.")
    blind_rows = [json.loads(x) for x in blind_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    score_doc = json.loads(score_path.read_text(encoding="utf-8"))
    ids = [r["case_id"] for r in blind_rows]
    scored_ids = [r["case_id"] for r in score_doc.get("case_scores", [])]
    if score_doc.get("schema") != "HG-CTI-BLIND-SCORES-V2":
        raise SystemExit("BLOCKED: unexpected score schema.")
    if score_doc.get("scored_blind_file_sha256") != digest(blind_path):
        raise SystemExit("BLOCKED: score file is not bound to the current blind outputs.")
    if len(ids) != 40 or len(set(ids)) != 40 or set(ids) != set(scored_ids) or len(scored_ids) != 40:
        raise SystemExit("BLOCKED: scoring must cover all 40 paired cases exactly once.")
    for row in score_doc["case_scores"]:
        for label in ("A", "B"):
            value = row.get(label, {})
            criteria = value.get("criteria")
            if not isinstance(criteria, list) or len(criteria) != 4 or any(type(v) is not int or v not in (0, 1) for v in criteria):
                raise SystemExit(f"BLOCKED: {row['case_id']} {label}: four 0/1 criterion values required.")
            if not isinstance(value.get("critical_violation"), bool):
                raise SystemExit(f"BLOCKED: {row['case_id']} {label}: critical_violation must be boolean.")
            if not isinstance(value.get("raw_critical_violation"), bool) or not isinstance(value.get("guard_intervention"), bool):
                raise SystemExit(f"BLOCKED: {row['case_id']} {label}: raw_critical_violation and guard_intervention must be boolean.")
            rationales = value.get("criterion_rationales")
            if not isinstance(rationales, list) or len(rationales) != 4 or any(not isinstance(x, str) or not x.strip() for x in rationales):
                raise SystemExit(f"BLOCKED: {row['case_id']} {label}: four non-empty criterion rationales required.")
            ledger = value.get("claim_ledger")
            if not isinstance(ledger, list):
                raise SystemExit(f"BLOCKED: {row['case_id']} {label}: claim_ledger must be a list.")
            m, u = value.get("material_claims"), value.get("unsupported_material_claims")
            if type(m) is not int or type(u) is not int or m < 0 or u < 0 or u > m or m != len(ledger):
                raise SystemExit(f"BLOCKED: {row['case_id']} {label}: claim counts must match claim_ledger length.")
            for claim in ledger:
                if not isinstance(claim, dict) or not {"claim_id", "span", "disposition", "evidence_ids", "rationale"}.issubset(claim):
                    raise SystemExit(f"BLOCKED: {row['case_id']} {label}: claim ledger entry schema invalid.")
                if not isinstance(claim.get("claim_id"), str) or not claim["claim_id"].strip():
                    raise SystemExit(f"BLOCKED: {row['case_id']} {label}: claim ID required.")
                if not isinstance(claim.get("span"), str) or not claim["span"].strip() or not isinstance(claim.get("rationale"), str) or not claim["rationale"].strip():
                    raise SystemExit(f"BLOCKED: {row['case_id']} {label}: claim span and rationale required.")
                if not isinstance(claim.get("disposition"), str) or claim.get("disposition") not in {"SUPPORTED", "CONTRADICTED", "UNKNOWN", "UNSUPPORTED"}:
                    raise SystemExit(f"BLOCKED: {row['case_id']} {label}: claim disposition invalid.")
                if not isinstance(claim.get("evidence_ids"), list) or any(not isinstance(x, str) for x in claim["evidence_ids"]):
                    raise SystemExit(f"BLOCKED: {row['case_id']} {label}: claim evidence_ids invalid.")
                if any(x != "CASE_PROMPT" for x in claim["evidence_ids"]):
                    raise SystemExit(f"BLOCKED: {row['case_id']} {label}: claim cites evidence not supplied to the model.")
                if claim["disposition"] in {"SUPPORTED", "CONTRADICTED"} and not claim["evidence_ids"]:
                    raise SystemExit(f"BLOCKED: {row['case_id']} {label}: supported/contradicted claim needs evidence IDs.")
            expected_unsupported = sum(1 for claim in ledger if claim["disposition"] in {"UNSUPPORTED", "CONTRADICTED"})
            if u != expected_unsupported:
                raise SystemExit(f"BLOCKED: {row['case_id']} {label}: unsupported count does not match ledger dispositions.")
            if type(value.get("counterexample_handled")) is not int or value.get("counterexample_handled") not in (0, 1) or type(value.get("alternative_distinctness")) is not int or value.get("alternative_distinctness") not in (0, 1):
                raise SystemExit(f"BLOCKED: {row['case_id']} {label}: diagnostic values must be integer 0/1.")
            if not isinstance(value.get("notes"), str) or not value["notes"].strip():
                raise SystemExit(f"BLOCKED: {row['case_id']} {label}: non-empty notes required.")
    freeze = {
        "schema": "HG-CTI-SCORE-FREEZE-V2",
        "status": "FROZEN_BLIND_SCORES",
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "blind_pairs_sha256": digest(blind_path),
        "blind_scores_sha256": digest(score_path),
        "case_count": 40,
        "scorer_method": "Pre-registered case-specific rubric; labels A/B only; no key file read by this freezer.",
        "approval_gate": False,
        "signature": None
    }
    freeze_path.write_text(json.dumps(freeze, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_manifest(run_dir)
    print(json.dumps(freeze, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
