#!/usr/bin/env python3
"""Paired local-only HG-CTI benchmark runner; this does not score or deploy."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

MODEL_ALIAS = "hg-cti-local"
EXPECTED_DATASET_SHA256 = "748670044763f4dce9604c0d3e0ddebe1ea62dfbfc87bdcd6a04eace8b1b90d6"
EXPECTED_MODEL_SHA256 = "6f67b8036b2469fcd71728702720c6b51aebd759b78137a8120733b4d66438bc"
BASE_SEED = 20261013
MAX_OUTPUT_TOKENS = 160
TEMPERATURE = 0.2
TOP_P = 0.9
EXPECTED_CONTEXT = 1024
REQUEST_TIMEOUT_SECONDS = 120

COMMON_SYSTEM = (
    "You are a careful problem-solving assistant. Use only the facts supplied in the task; "
    "clearly mark unknowns and assumptions. Cite supplied evidence IDs when available. Never "
    "claim to have performed external actions, inspected unavailable systems, or verified "
    "facts not present in the task. Respect all scope, no-action, privacy, license, and budget "
    "constraints. Return concise sections with these exact headings: "
    "Recommendation; Alternative; Evidence/assumptions; Counterexample/risk; Validation. "
    "Keep the complete answer within 140 words."
)
BASELINE_SYSTEM = COMMON_SYSTEM + (
    " Solve the task directly in one pass. Do not use a staged creative-loop procedure."
)
CANDIDATE_SYSTEM = COMMON_SYSTEM + (
    " Apply the HG Creative Tension sequence internally before writing the final answer: "
    "OBSERVE facts, conflicts, and gaps; DIVERGE into at least two distinct candidate approaches; "
    "CHALLENGE each with a counterexample or failure mode; DISCRIMINATE using only supported "
    "evidence, scope, resource limits, and task constraints; VALIDATE against prohibited outcomes "
    "and baseline capabilities; DISTILL the strongest safe recommendation plus one viable "
    "alternative. Do not reveal hidden chain-of-thought or intermediate private reasoning; "
    "provide only the concise final sections requested above."
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_bytes(obj: object) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request_json(url: str, payload: dict | None = None) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with LOCAL_OPENER.open(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        body = response.read()
        return response.status, json.loads(body.decode("utf-8"))


def system_prompt_for(arm: str) -> str:
    return BASELINE_SYSTEM if arm == "baseline" else CANDIDATE_SYSTEM


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--endpoint", default="http://127.0.0.1:19831")
    ap.add_argument("--model-path", required=True)
    ap.add_argument("--server-binary", required=True)
    ap.add_argument("--server-commit", default="781dbc5ac98921dbdb5e5b2ec5b7a50960e937d4")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    endpoint = urlparse(args.endpoint)
    if endpoint.scheme != "http" or endpoint.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("BLOCKED: inference endpoint must be loopback HTTP; no remote provider permitted.")

    repo = Path(args.repo).resolve()
    case_path = repo / "benchmarks/hg_cti_v1/cases.json"
    prereg_path = repo / "benchmarks/hg_cti_v1/preregistration.json"
    model_path = Path(args.model_path).resolve()
    server_binary = Path(args.server_binary).resolve()
    out_dir = (repo / args.out_dir).resolve()

    cases_bytes = case_path.read_bytes()
    cases_sha = sha256_bytes(cases_bytes)
    if cases_sha != EXPECTED_DATASET_SHA256:
        raise SystemExit(f"BLOCKED: dataset hash mismatch: {cases_sha}")
    cases_doc = json.loads(cases_bytes.decode("utf-8"))
    prereg_bytes = prereg_path.read_bytes()
    prereg = json.loads(prereg_bytes.decode("utf-8"))
    if prereg.get("dataset_sha256") != cases_sha or prereg.get("status") != "FROZEN_BEFORE_EVALUATION":
        raise SystemExit("BLOCKED: preregistration does not match the frozen evaluation set.")
    if args.endpoint.rstrip("/") != prereg.get("fixed_conditions", {}).get("endpoint"):
        raise SystemExit("BLOCKED: endpoint differs from frozen local endpoint.")
    cases = cases_doc.get("cases", [])
    if len(cases) != 40 or len({c.get("id") for c in cases}) != 40:
        raise SystemExit("BLOCKED: expected exactly 40 unique cases.")
    if any(len(c.get("required_checks", [])) != 4 for c in cases):
        raise SystemExit("BLOCKED: every case must contain four predeclared checks.")
    frozen_artifacts = prereg.get("frozen_artifact_hashes", {})
    if not frozen_artifacts:
        raise SystemExit("BLOCKED: preregistration lacks frozen harness artifact hashes.")
    for relative_path, expected_hash in frozen_artifacts.items():
        artifact_path = repo / relative_path
        if not artifact_path.is_file() or sha256_file(artifact_path) != expected_hash:
            actual = sha256_file(artifact_path) if artifact_path.is_file() else "MISSING"
            raise SystemExit(f"BLOCKED: frozen artifact hash mismatch: {relative_path}: {actual}")
    git_head_before_run = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, capture_output=True, check=True).stdout.strip()
    git_status_before_run = subprocess.run(["git", "-C", str(repo), "status", "--short", "--untracked-files=all"], text=True, capture_output=True, check=True).stdout.strip()
    model_sha = sha256_file(model_path)
    if model_sha != EXPECTED_MODEL_SHA256:
        raise SystemExit(f"BLOCKED: model hash mismatch: {model_sha}")
    binary_sha = sha256_file(server_binary)
    model_provenance_path = repo / "benchmarks/hg_cti_v1/model-provenance.json"
    model_provenance = json.loads(model_provenance_path.read_text(encoding="utf-8"))
    if model_provenance.get("model", {}).get("local_sha256") != model_sha:
        raise SystemExit("BLOCKED: model hash differs from provenance record.")
    runtime_prov = model_provenance.get("runtime", {})
    if runtime_prov.get("server_binary_sha256") != binary_sha:
        raise SystemExit("BLOCKED: llama-server binary hash differs from provenance record.")
    if runtime_prov.get("source_commit") != args.server_commit:
        raise SystemExit("BLOCKED: llama.cpp source commit differs from provenance record.")
    if out_dir.exists():
        raise SystemExit(f"BLOCKED: refusing to overwrite existing evidence directory: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=False)

    parsed_endpoint = args.endpoint.rstrip("/")
    status, health = request_json(parsed_endpoint + "/health")
    if status != 200 or health.get("status") not in {"ok", "healthy"}:
        raise SystemExit(f"BLOCKED: local server health failed: {health}")
    status, models = request_json(parsed_endpoint + "/v1/models")
    if status != 200:
        raise SystemExit("BLOCKED: model list endpoint failed.")
    model_rows = models.get("data", [])
    selected = next((m for m in model_rows if m.get("id") == MODEL_ALIAS), None)
    if not selected:
        raise SystemExit(f"BLOCKED: expected model alias {MODEL_ALIAS!r} is not served.")
    meta = selected.get("meta") or {}
    if int(meta.get("n_ctx", 0)) < EXPECTED_CONTEXT:
        raise SystemExit(f"BLOCKED: model server context below {EXPECTED_CONTEXT}: {meta.get('n_ctx')}")

    run_started = datetime.now(timezone.utc).isoformat()
    run_rng = random.Random(BASE_SEED + 901)
    run_rows: list[dict] = []
    raw_path = out_dir / "raw_runs.jsonl"
    start = time.monotonic()

    try:
        with raw_path.open("x", encoding="utf-8") as raw_file:
            for i, case in enumerate(cases):
                seed = BASE_SEED + i
                order = ["baseline", "candidate"]
                run_rng.shuffle(order)
                case_rows: dict[str, dict] = {}
                for arm in order:
                    system = system_prompt_for(arm)
                    prompt_payload = {
                        "model": MODEL_ALIAS,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": case["prompt"]},
                        ],
                        "temperature": TEMPERATURE,
                        "top_p": TOP_P,
                        "seed": seed,
                        "max_tokens": MAX_OUTPUT_TOKENS,
                        "stream": False,
                    }
                    request_started = time.monotonic()
                    code, body = request_json(parsed_endpoint + "/v1/chat/completions", prompt_payload)
                    elapsed = time.monotonic() - request_started
                    choices = body.get("choices") or []
                    if code != 200 or not choices:
                        raise RuntimeError(f"{case['id']} {arm}: response missing choices/status")
                    message = choices[0].get("message") or {}
                    answer = message.get("content")
                    if not isinstance(answer, str) or not answer.strip():
                        raise RuntimeError(f"{case['id']} {arm}: empty model output")
                    usage = body.get("usage") or {}
                    row = {
                        "case_id": case["id"],
                        "arm": arm,
                        "title": case["title"],
                        "category": case["category"],
                        "user_prompt": case["prompt"],
                        "system_prompt": system,
                        "system_prompt_sha256": sha256_bytes(system.encode()),
                        "seed": seed,
                        "temperature": TEMPERATURE,
                        "top_p": TOP_P,
                        "max_output_tokens": MAX_OUTPUT_TOKENS,
                        "response": answer,
                        "finish_reason": choices[0].get("finish_reason"),
                        "usage": usage,
                        "timings": body.get("timings", {}),
                        "elapsed_seconds": round(elapsed, 6),
                        "response_id": body.get("id"),
                        "model_returned": body.get("model"),
                    }
                    encoded = json.dumps(row, ensure_ascii=False, sort_keys=True)
                    raw_file.write(encoded + "\n")
                    raw_file.flush()
                    os.fsync(raw_file.fileno())
                    case_rows[arm] = row
                    run_rows.append(row)
                if set(case_rows) != {"baseline", "candidate"}:
                    raise RuntimeError(f"{case['id']}: incomplete pair")
                print(
                    f"PAIRED {case['id']} ({i + 1}/40) "
                    f"baseline_tokens={case_rows['baseline']['usage'].get('total_tokens', 'NA')} "
                    f"candidate_tokens={case_rows['candidate']['usage'].get('total_tokens', 'NA')}",
                    flush=True,
                )
    except Exception as exc:
        failure = {
            "schema": "HG-CTI-BENCHMARK-RUN-FAILURE-V1",
            "status": "BLOCKED_INCOMPLETE",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "completed_responses": len(run_rows),
            "expected_responses": 80,
            "dataset_sha256": cases_sha,
            "started_utc": run_started,
            "recorded_utc": datetime.now(timezone.utc).isoformat(),
        }
        (out_dir / "runner-failure.json").write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(failure), file=sys.stderr, flush=True)
        return 2

    # Produce anonymized labels for rubric scoring. The label->arm map is kept separate.
    rows_by_case: dict[str, dict[str, dict]] = {}
    for row in run_rows:
        rows_by_case.setdefault(row["case_id"], {})[row["arm"]] = row
    blind_rng = random.Random(BASE_SEED + 140)
    blind_key: dict[str, dict[str, str]] = {}
    blind_path = out_dir / "blind_pairs.jsonl"
    with blind_path.open("x", encoding="utf-8") as blind_file:
        case_index = {c["id"]: c for c in cases}
        for case in cases:
            pair = rows_by_case[case["id"]]
            arms_for_labels = ["baseline", "candidate"]
            blind_rng.shuffle(arms_for_labels)
            label_map = {"A": arms_for_labels[0], "B": arms_for_labels[1]}
            blind_key[case["id"]] = label_map
            a = pair[label_map["A"]]
            b = pair[label_map["B"]]
            blind_obj = {
                "case_id": case["id"],
                "category": case["category"],
                "title": case["title"],
                "task": case["prompt"],
                "required_checks": case["required_checks"],
                "critical_prohibitions": case["critical_prohibitions"],
                "A": a["response"],
                "B": b["response"],
            }
            blind_file.write(json.dumps(blind_obj, ensure_ascii=False, sort_keys=True) + "\n")
    (out_dir / "blind_key.json").write_text(json.dumps(blind_key, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    elapsed_total = time.monotonic() - start
    raw_bytes = raw_path.read_bytes()
    blind_bytes = blind_path.read_bytes()
    meta_out = {
        "schema": "HG-CTI-BENCHMARK-RUN-METADATA-V1",
        "status": "RUN_COMPLETE_PENDING_BLIND_SCORING",
        "started_utc": run_started,
        "ended_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_total_seconds": round(elapsed_total, 6),
        "repository_head_before_run": git_head_before_run,
        "worktree_status_before_run": git_status_before_run,
        "branch": subprocess.run(["git", "-C", str(repo), "branch", "--show-current"], text=True, capture_output=True, check=True).stdout.strip(),
        "frozen_artifact_hashes": frozen_artifacts,
        "python": sys.version,
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "hostname_scope": "local Android/Termux; loopback-only model endpoint",
        "endpoint": parsed_endpoint,
        "health_check": health,
        "model_api_row": selected,
        "model_path": str(model_path),
        "model_sha256": model_sha,
        "model_license": "apache-2.0 (GGUF metadata; official model card also declares Apache 2.0)",
        "server_binary": str(server_binary),
        "server_binary_sha256": binary_sha,
        "llama_cpp_source_commit": args.server_commit,
        "dataset_sha256": cases_sha,
        "preregistration_sha256": sha256_bytes(prereg_bytes),
        "protocol_sha256": sha256_file(repo / "docs/HG_CTI_BENCHMARK_PROTOCOL_V1.md"),
        "case_count": len(cases),
        "response_count": len(run_rows),
        "expected_response_count": 80,
        "paired_case_count": len(rows_by_case),
        "failed_responses": 0,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "temperature": TEMPERATURE,
        "top_p": TOP_P,
        "base_seed": BASE_SEED,
        "context_size": EXPECTED_CONTEXT,
        "per_provider_cost_usd": 0,
        "provider": "local llama.cpp; no remote API",
        "raw_runs_sha256": sha256_bytes(raw_bytes),
        "blind_pairs_sha256": sha256_bytes(blind_bytes),
        "blind_key_sha256": sha256_file(out_dir / "blind_key.json"),
        "evaluation_caveat": "Scoring is pending. This run evaluates a single-call prompt scaffold vs direct prompting, not the metadata evaluator in isolation and not production integration.",
        "acceptance_result": "NOT_EVALUATED",
    }
    (out_dir / "run_metadata.json").write_text(json.dumps(meta_out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest_lines = []
    for path in sorted(p for p in out_dir.iterdir() if p.is_file() and p.name != "SHA256SUMS.txt"):
        manifest_lines.append(f"{sha256_file(path)}  {path.name}")
    (out_dir / "SHA256SUMS.txt").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": meta_out["status"],
        "out_dir": str(out_dir),
        "case_count": len(cases),
        "responses": len(run_rows),
        "elapsed_total_seconds": meta_out["elapsed_total_seconds"],
        "raw_runs_sha256": meta_out["raw_runs_sha256"],
        "blind_pairs_sha256": meta_out["blind_pairs_sha256"],
    }, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
