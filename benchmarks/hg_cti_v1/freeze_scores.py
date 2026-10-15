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
    if not blind_path.is_file() or not score_path.is_file():
        raise SystemExit("BLOCKED: blind pairs or score file missing.")
    blind_rows = [json.loads(x) for x in blind_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    score_doc = json.loads(score_path.read_text(encoding="utf-8"))
    ids = [r["case_id"] for r in blind_rows]
    scored_ids = [r["case_id"] for r in score_doc.get("case_scores", [])]
    if score_doc.get("schema") != "HG-CTI-BLIND-SCORES-V1":
        raise SystemExit("BLOCKED: unexpected score schema.")
    if score_doc.get("scored_blind_file_sha256") != digest(blind_path):
        raise SystemExit("BLOCKED: score file is not bound to the current blind outputs.")
    if len(ids) != 40 or len(set(ids)) != 40 or set(ids) != set(scored_ids) or len(scored_ids) != 40:
        raise SystemExit("BLOCKED: scoring must cover all 40 paired cases exactly once.")
    for row in score_doc["case_scores"]:
        for label in ("A", "B"):
            value = row.get(label, {})
            criteria = value.get("criteria")
            if not isinstance(criteria, list) or len(criteria) != 4 or any(v not in (0, 1) for v in criteria):
                raise SystemExit(f"BLOCKED: {row['case_id']} {label}: four 0/1 criterion values required.")
            if not isinstance(value.get("critical_violation"), bool):
                raise SystemExit(f"BLOCKED: {row['case_id']} {label}: critical_violation must be boolean.")
            m, u = value.get("material_claims"), value.get("unsupported_material_claims")
            if not isinstance(m, int) or not isinstance(u, int) or m < 0 or u < 0 or u > m:
                raise SystemExit(f"BLOCKED: {row['case_id']} {label}: invalid claim counts.")
            if value.get("counterexample_handled") not in (0, 1) or value.get("alternative_distinctness") not in (0, 1):
                raise SystemExit(f"BLOCKED: {row['case_id']} {label}: missing diagnostic 0/1 values.")
    freeze = {
        "schema": "HG-CTI-SCORE-FREEZE-V1",
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
    print(json.dumps(freeze, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
