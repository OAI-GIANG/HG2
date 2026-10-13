#!/usr/bin/env python3
"""HG-CTI V2 paired local-only guarded benchmark runner.

The runner records raw model output and the deterministic final output separately.
It does not score, merge, deploy, or change canonical state.
"""
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
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

REPO_FROM_SCRIPT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_FROM_SCRIPT))

from hg.cti_guards import (  # noqa: E402
    AuthorityContext,
    EvidenceItem,
    MaterialClaim,
    ProposedAction,
    ProposedReuse,
    ProvenanceAssessment,
    validate_response_gate,
)

MODEL_ALIAS = "hg-cti-local"
EXPECTED_MODEL_SHA256 = "6f67b8036b2469fcd71728702720c6b51aebd759b78137a8120733b4d66438bc"
EXPECTED_SERVER_SHA256 = "6f9c5e7aba1cee5fb637c87db093040d86391d19cf35851a9a8f51cb2db71df3"
EXPECTED_SERVER_COMMIT = "781dbc5ac98921dbdb5e5b2ec5b7a50960e937d4"
EXPECTED_CONTEXT = 1024
MAX_OUTPUT_TOKENS = 320
TEMPERATURE = 0.2
TOP_P = 0.9
BASE_SEED = 20261014
TIMEOUT_SECONDS = 120

LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def write_manifest(out_dir: Path) -> None:
    manifest = []
    for path in sorted(item for item in out_dir.iterdir() if item.is_file() and item.name != "SHA256SUMS.txt"):
        manifest.append(f"{sha256_file(path)}  {path.name}")
    (out_dir / "SHA256SUMS.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")


def verify_sha256_manifest(manifest_path: Path, base_dir: Path) -> dict:
    if not manifest_path.is_file():
        raise SystemExit(f"BLOCKED: V1 integrity manifest missing: {manifest_path}")
    checked = 0
    failures = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            expected, relative = line.split("  ", 1)
        except ValueError:
            failures.append("MALFORMED_LINE:" + line)
            continue
        target = base_dir / relative
        if not target.is_file():
            failures.append("MISSING:" + relative)
        elif sha256_file(target) != expected:
            failures.append("HASH_MISMATCH:" + relative)
        else:
            checked += 1
    if failures:
        raise SystemExit("BLOCKED: V1 artifact integrity verification failed: " + ",".join(failures[:10]))
    return {"manifest_sha256": sha256_file(manifest_path), "entries_checked": checked, "failures": 0}


def request_json(url: str, payload: dict | None = None) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with LOCAL_OPENER.open(req, timeout=TIMEOUT_SECONDS) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def validate_endpoint(endpoint: str) -> None:
    parsed = urlparse(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("BLOCKED: V2 permits loopback HTTP only; no remote inference endpoint.")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_response_shape(payload: object) -> tuple[str, ...]:
    if not isinstance(payload, dict):
        return ("RESPONSE_NOT_OBJECT",)
    required = {"decision", "answer", "alternative", "next_step", "unknowns", "actions", "reuse_requests", "claims"}
    if set(payload) != required:
        return ("RESPONSE_KEYS_MISMATCH",)
    errors: list[str] = []
    if not isinstance(payload["decision"], str) or payload["decision"] not in {"RECOMMEND", "BLOCKED", "NEEDS_EVIDENCE"}:
        errors.append("DECISION_INVALID")
    for name in ("answer", "alternative", "next_step"):
        if not isinstance(payload[name], str):
            errors.append(name.upper() + "_NOT_STRING")
    if not isinstance(payload["answer"], str) or not payload["answer"].strip():
        errors.append("ANSWER_EMPTY")
    if not isinstance(payload["next_step"], str) or not payload["next_step"].strip():
        errors.append("NEXT_STEP_EMPTY")
    if not isinstance(payload["unknowns"], list) or any(not isinstance(x, str) for x in payload["unknowns"]):
        errors.append("UNKNOWNS_INVALID")
    if not isinstance(payload["actions"], list):
        errors.append("ACTIONS_INVALID")
    else:
        for item in payload["actions"]:
            if not isinstance(item, dict) or set(item) != {"action", "scope", "cost_usd"}:
                errors.append("ACTION_SCHEMA_INVALID")
                continue
            if not isinstance(item["action"], str) or item["action"] not in {"none", "read", "write", "delete", "push", "merge", "deploy", "rollback", "spend"}:
                errors.append("ACTION_VALUE_INVALID")
            if not isinstance(item["scope"], str):
                errors.append("ACTION_SCOPE_INVALID")
            if item["cost_usd"] is not None and (
                not isinstance(item["cost_usd"], (int, float)) or isinstance(item["cost_usd"], bool) or item["cost_usd"] < 0
            ):
                errors.append("ACTION_COST_INVALID")
    if not isinstance(payload["reuse_requests"], list):
        errors.append("REUSE_REQUESTS_INVALID")
    else:
        for item in payload["reuse_requests"]:
            if not isinstance(item, dict) or set(item) != {"artifact_id", "reuse_requested"}:
                errors.append("REUSE_REQUEST_SCHEMA_INVALID")
                continue
            if not isinstance(item["artifact_id"], str) or not item["artifact_id"].strip():
                errors.append("REUSE_ARTIFACT_ID_INVALID")
            if not isinstance(item["reuse_requested"], bool):
                errors.append("REUSE_FLAG_INVALID")
    if not isinstance(payload["claims"], list):
        errors.append("CLAIMS_INVALID")
    else:
        for item in payload["claims"]:
            if not isinstance(item, dict) or set(item) != {"claim_id", "span", "disposition", "evidence_ids"}:
                errors.append("CLAIM_SCHEMA_INVALID")
                continue
            if not isinstance(item["claim_id"], str) or not item["claim_id"].strip():
                errors.append("CLAIM_ID_INVALID")
            if not isinstance(item["span"], str) or not item["span"].strip():
                errors.append("CLAIM_SPAN_INVALID")
            if not isinstance(item["disposition"], str) or item["disposition"] not in {"SUPPORTED", "CONTRADICTED", "UNKNOWN", "UNSUPPORTED"}:
                errors.append("CLAIM_DISPOSITION_INVALID")
            if not isinstance(item["evidence_ids"], list) or any(not isinstance(x, str) for x in item["evidence_ids"]):
                errors.append("CLAIM_EVIDENCE_IDS_INVALID")
    return tuple(dict.fromkeys(errors))


def parse_json_output(raw: str) -> tuple[dict | None, tuple[str, ...]]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None, ("RESPONSE_JSON_INVALID",)
    errors = validate_response_shape(payload)
    return (payload if not errors else None), errors


def blocked_response(blockers: tuple[str, ...]) -> str:
    reasons = ", ".join(blockers) if blockers else "RESPONSE_GUARD_REJECTED"
    return (
        "Decision: BLOCKED\n"
        "Answer: The raw model response failed the deterministic HG-CTI response gate; do not act on it.\n"
        f"Guard blockers: {reasons}\n"
        "Safe next step: verify the missing evidence or authority and produce a schema-valid response."
    )


def guarded_output(raw: str, case: dict, policy: dict) -> tuple[str, dict]:
    payload, shape_errors = parse_json_output(raw)
    if payload is None:
        return blocked_response(shape_errors), {
            "schema_valid": False, "accepted": False, "blockers": list(shape_errors),
            "guard_intervention": True,
        }

    authority_doc = policy["authority"]
    authority = AuthorityContext(
        allowed_actions=frozenset(authority_doc["allowed_actions"]),
        no_action=bool(authority_doc["no_action"]),
        read_only=bool(authority_doc["read_only"]),
        scope_allowlist=frozenset(authority_doc["scope_allowlist"]),
        approved_cost_limit_usd=authority_doc["approved_cost_limit_usd"],
    )
    actions = tuple(ProposedAction(
        action=item["action"], scope=item["scope"], cost_usd=item["cost_usd"]
    ) for item in payload["actions"])
    trusted_doc = policy["trusted_reuse_assessment"]
    trusted_assessment = ProvenanceAssessment(
        integrity=trusted_doc["integrity"],
        authenticity=trusted_doc["authenticity"],
        provenance=trusted_doc["provenance"],
        rights=trusted_doc["rights"],
        source_revision=trusted_doc["source_revision"],
        evidence_ids=tuple(trusted_doc["evidence_ids"]),
    )
    reuse_requests = tuple(ProposedReuse(
        trusted_assessment=trusted_assessment,
        reuse_requested=item["reuse_requested"],
    ) for item in payload["reuse_requests"] if item["reuse_requested"])
    output_text = (
        f"Decision: {payload['decision']}\n"
        f"Answer: {payload['answer']}\n"
        f"Alternative: {payload['alternative']}\n"
        f"Next step: {payload['next_step']}\n"
        "Unknowns: " + ("; ".join(payload["unknowns"]) if payload["unknowns"] else "None stated.")
    )
    claims = tuple(MaterialClaim(
        claim_id=item["claim_id"],
        span=item["span"],
        disposition=item["disposition"],
        evidence_ids=tuple(item["evidence_ids"]),
    ) for item in payload["claims"])
    evidence = {
        "CASE_PROMPT": EvidenceItem(
            evidence_id="CASE_PROMPT",
            text=case["prompt"],
            source_ref="case:" + case["id"],
        )
    }
    gate = validate_response_gate(
        output_text=output_text,
        authority=authority,
        actions=actions,
        reuse_requests=reuse_requests,
        claims=claims,
        evidence=evidence,
    )
    result = {
        "schema_valid": True,
        "accepted": gate.accepted,
        "blockers": list(gate.blockers),
        "guard_intervention": not gate.accepted,
        "decision": payload["decision"],
        "claim_ledger_structure_valid": not any(
            blocker.startswith(("CLAIM_", "EVIDENCE_")) for blocker in gate.blockers
        ),
    }
    return (output_text if gate.accepted else blocked_response(gate.blockers)), result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--endpoint", default="http://127.0.0.1:19831")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--server-binary", required=True)
    parser.add_argument("--server-commit", default=EXPECTED_SERVER_COMMIT)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    validate_endpoint(args.endpoint)
    endpoint = args.endpoint.rstrip("/")
    case_path = repo / "benchmarks/hg_cti_v2/cases.json"
    policy_path = repo / "benchmarks/hg_cti_v2/guard_policy.json"
    prompt_path = repo / "benchmarks/hg_cti_v2/prompts.json"
    prereg_path = repo / "benchmarks/hg_cti_v2/preregistration.json"
    freeze_path = repo / "benchmarks/hg_cti_v2/preregistration-freeze.json"
    schema_path = repo / "benchmarks/hg_cti_v2/response-schema.json"
    model_path = Path(args.model_path).resolve()
    server_binary = Path(args.server_binary).resolve()
    out_dir = (repo / args.out_dir).resolve()

    for required in (case_path, policy_path, prompt_path, prereg_path, freeze_path, schema_path, model_path, server_binary):
        if not required.is_file():
            raise SystemExit(f"BLOCKED: required file missing: {required}")
    prereg = load_json(prereg_path)
    freeze = load_json(freeze_path)
    if prereg.get("status") != "FROZEN_BEFORE_EVALUATION":
        raise SystemExit("BLOCKED: V2 preregistration is not frozen.")
    if freeze.get("status") != "FROZEN_BEFORE_EVALUATION":
        raise SystemExit("BLOCKED: V2 freeze record is not frozen.")
    if freeze.get("preregistration_sha256") != sha256_file(prereg_path):
        raise SystemExit("BLOCKED: preregistration hash does not match freeze record.")
    if freeze.get("protocol_sha256") != sha256_file(repo / prereg["protocol"]):
        raise SystemExit("BLOCKED: protocol hash does not match freeze record.")
    if prereg.get("dataset_sha256") != sha256_file(case_path):
        raise SystemExit("BLOCKED: V2 dataset hash mismatch.")
    for relpath, expected in prereg.get("frozen_artifact_hashes", {}).items():
        artifact = repo / relpath
        if not artifact.is_file() or sha256_file(artifact) != expected:
            actual = sha256_file(artifact) if artifact.is_file() else "MISSING"
            raise SystemExit(f"BLOCKED: frozen artifact hash mismatch: {relpath}: {actual}")
    if sha256_file(model_path) != EXPECTED_MODEL_SHA256:
        raise SystemExit("BLOCKED: model SHA-256 mismatch.")
    if sha256_file(server_binary) != EXPECTED_SERVER_SHA256:
        raise SystemExit("BLOCKED: llama-server SHA-256 mismatch.")
    if args.server_commit != EXPECTED_SERVER_COMMIT:
        raise SystemExit("BLOCKED: llama.cpp source commit mismatch.")
    provenance = load_json(repo / "benchmarks/hg_cti_v2/model-provenance.json")
    if provenance.get("model", {}).get("local_sha256") != sha256_file(model_path):
        raise SystemExit("BLOCKED: model provenance digest mismatch.")
    if provenance.get("runtime", {}).get("server_binary_sha256") != sha256_file(server_binary):
        raise SystemExit("BLOCKED: runtime provenance digest mismatch.")
    if endpoint != prereg["fixed_conditions"]["endpoint"]:
        raise SystemExit("BLOCKED: endpoint differs from frozen protocol.")
    if out_dir.exists():
        raise SystemExit(f"BLOCKED: refusing to overwrite evidence directory: {out_dir}")

    v1_root_manifest = repo / "evidence/HG-CTI-20261013/SHA256SUMS.txt"
    v1_run_dir = repo / "evidence/HG-CTI-20261013/benchmark-run-local-001"
    v1_root_verification = verify_sha256_manifest(v1_root_manifest, repo)
    v1_run_verification = verify_sha256_manifest(v1_run_dir / "SHA256SUMS.txt", v1_run_dir)

    case_doc = load_json(case_path)
    policy_doc = load_json(policy_path)
    prompt_doc = load_json(prompt_path)
    cases = case_doc.get("cases", [])
    if len(cases) != 40 or len({case.get("id") for case in cases}) != 40:
        raise SystemExit("BLOCKED: expected exactly 40 unique V2 cases.")
    if set(policy_doc.get("cases", {})) != {case["id"] for case in cases}:
        raise SystemExit("BLOCKED: trusted guard policy does not exactly match the case set.")
    for case in cases:
        if case.get("guard_context") != policy_doc["cases"][case["id"]]:
            raise SystemExit(f"BLOCKED: case/policy context mismatch: {case['id']}")
        if sha256_bytes(case["prompt"].encode("utf-8")) != case.get("prompt_sha256"):
            raise SystemExit(f"BLOCKED: case prompt hash mismatch: {case['id']}")
    if len({case.get("prompt_sha256") for case in cases}) != 40:
        raise SystemExit("BLOCKED: missing/duplicate prompt hashes.")

    head_before = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, capture_output=True, check=True
    ).stdout.strip()
    status_before = subprocess.run(
        ["git", "-C", str(repo), "status", "--short", "--untracked-files=all"],
        text=True, capture_output=True, check=True,
    ).stdout.strip()
    status, health = request_json(endpoint + "/health")
    if status != 200 or health.get("status") not in {"ok", "healthy"}:
        raise SystemExit(f"BLOCKED: local model health failed: {health}")
    status, models = request_json(endpoint + "/v1/models")
    if status != 200:
        raise SystemExit("BLOCKED: model-list endpoint failed.")
    model_rows = models.get("data", [])
    selected = next((row for row in model_rows if row.get("id") == MODEL_ALIAS), None)
    if not selected:
        raise SystemExit(f"BLOCKED: expected model alias {MODEL_ALIAS!r} not served.")
    if int((selected.get("meta") or {}).get("n_ctx", 0)) < EXPECTED_CONTEXT:
        raise SystemExit("BLOCKED: server context smaller than preregistered context.")
    out_dir.mkdir(parents=True, exist_ok=False)

    raw_path = out_dir / "raw_runs.jsonl"
    blind_path = out_dir / "blind_pairs.jsonl"
    started_utc = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    rng = random.Random(BASE_SEED + 77)
    raw_rows: list[dict] = []
    by_case: dict[str, dict[str, dict]] = {}
    try:
        with raw_path.open("x", encoding="utf-8") as raw_file:
            for index, case in enumerate(cases):
                seed = BASE_SEED + index
                order = ["baseline", "candidate"]
                rng.shuffle(order)
                for arm in order:
                    system = prompt_doc["common_system"] + " " + prompt_doc[f"{arm}_suffix"]
                    payload = {
                        "model": MODEL_ALIAS,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": (
                                f"Case ID: {case['id']}\n"
                                f"Evidence ID CASE_PROMPT contains the complete scenario text below. "
                                f"Do not infer that any grounding reference was opened.\n"
                                f"Scenario: {case['prompt']}"
                            )},
                        ],
                        "temperature": TEMPERATURE,
                        "top_p": TOP_P,
                        "seed": seed,
                        "max_tokens": MAX_OUTPUT_TOKENS,
                        "stream": False,
                    }
                    request_start = time.monotonic()
                    status, body = request_json(endpoint + "/v1/chat/completions", payload)
                    elapsed = time.monotonic() - request_start
                    choices = body.get("choices") or []
                    if status != 200 or not choices:
                        raise RuntimeError(f"{case['id']} {arm}: missing model choice")
                    message = choices[0].get("message") or {}
                    raw = message.get("content")
                    if not isinstance(raw, str) or not raw.strip():
                        raise RuntimeError(f"{case['id']} {arm}: empty raw response")
                    final_text, gate = guarded_output(raw, case, policy_doc["cases"][case["id"]])
                    row = {
                        "case_id": case["id"],
                        "arm": arm,
                        "title": case["title"],
                        "category": case["category"],
                        "user_prompt": case["prompt"],
                        "system_prompt": system,
                        "system_prompt_sha256": sha256_bytes(system.encode("utf-8")),
                        "seed": seed,
                        "temperature": TEMPERATURE,
                        "top_p": TOP_P,
                        "max_output_tokens": MAX_OUTPUT_TOKENS,
                        "raw_response": raw,
                        "guarded_response": final_text,
                        "guard": gate,
                        "finish_reason": choices[0].get("finish_reason"),
                        "usage": body.get("usage") or {},
                        "elapsed_seconds": round(elapsed, 6),
                        "response_id": body.get("id"),
                        "model_returned": body.get("model"),
                    }
                    raw_file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                    raw_file.flush()
                    os.fsync(raw_file.fileno())
                    by_case.setdefault(case["id"], {})[arm] = row
                    raw_rows.append(row)
                if set(by_case[case["id"]]) != {"baseline", "candidate"}:
                    raise RuntimeError(f"{case['id']}: incomplete pair")
                print(
                    f"PAIRED {case['id']} ({index + 1}/40) "
                    f"baseline_guard={by_case[case['id']]['baseline']['guard']['accepted']} "
                    f"candidate_guard={by_case[case['id']]['candidate']['guard']['accepted']}",
                    flush=True,
                )
    except Exception as exc:
        failure = {
            "schema": "HG-CTI-V2-RUN-FAILURE",
            "status": "BLOCKED_INCOMPLETE",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "completed_responses": len(raw_rows),
            "expected_responses": 80,
            "dataset_sha256": sha256_file(case_path),
            "started_utc": started_utc,
            "recorded_utc": datetime.now(timezone.utc).isoformat(),
        }
        write_json(out_dir / "runner-failure.json", failure)
        write_manifest(out_dir)
        print(json.dumps(failure), file=sys.stderr, flush=True)
        return 2

    blind_rng = random.Random(BASE_SEED + 140)
    blind_key: dict[str, dict[str, str]] = {}
    blind_rows = []
    with blind_path.open("x", encoding="utf-8") as blind_file:
        for case in cases:
            arms = ["baseline", "candidate"]
            blind_rng.shuffle(arms)
            label_map = {"A": arms[0], "B": arms[1]}
            blind_key[case["id"]] = label_map
            row_a = by_case[case["id"]][label_map["A"]]
            row_b = by_case[case["id"]][label_map["B"]]
            blind = {
                "case_id": case["id"],
                "category": case["category"],
                "title": case["title"],
                "task": case["prompt"],
                "required_checks": case["required_checks"],
                "critical_prohibitions": case["critical_prohibitions"],
                "A": row_a["guarded_response"],
                "B": row_b["guarded_response"],
                "raw_A": row_a["raw_response"],
                "raw_B": row_b["raw_response"],
                "guard_A": row_a["guard"],
                "guard_B": row_b["guard"],
            }
            blind_file.write(json.dumps(blind, ensure_ascii=False, sort_keys=True) + "\n")
            blind_rows.append(blind)
    write_json(out_dir / "blind_key.json", blind_key)

    elapsed_total = time.monotonic() - start
    metadata = {
        "schema": "HG-CTI-V2-RUN-METADATA",
        "status": "RUN_COMPLETE_PENDING_BLIND_SCORING",
        "started_utc": started_utc,
        "ended_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_total_seconds": round(elapsed_total, 6),
        "repository_head_before_run": head_before,
        "worktree_status_before_run": status_before,
        "branch": subprocess.run(
            ["git", "-C", str(repo), "branch", "--show-current"],
            text=True, capture_output=True, check=True,
        ).stdout.strip(),
        "dataset_sha256": sha256_file(case_path),
        "guard_policy_sha256": sha256_file(policy_path),
        "prompts_sha256": sha256_file(prompt_path),
        "response_schema_sha256": sha256_file(schema_path),
        "preregistration_sha256": sha256_file(prereg_path),
        "protocol_sha256": sha256_file(repo / prereg["protocol"]),
        "preregistration_freeze_sha256": sha256_file(freeze_path),
        "model_sha256": sha256_file(model_path),
        "server_binary_sha256": sha256_file(server_binary),
        "server_commit": args.server_commit,
        "endpoint": endpoint,
        "health": health,
        "model_row": selected,
        "python": sys.version,
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "case_count": len(cases),
        "paired_case_count": len(by_case),
        "response_count": len(raw_rows),
        "expected_response_count": 80,
        "failed_responses": 0,
        "guard_interventions_baseline": sum(1 for row in raw_rows if row["arm"] == "baseline" and row["guard"]["guard_intervention"]),
        "guard_interventions_candidate": sum(1 for row in raw_rows if row["arm"] == "candidate" and row["guard"]["guard_intervention"]),
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "temperature": TEMPERATURE,
        "top_p": TOP_P,
        "base_seed": BASE_SEED,
        "per_provider_cost_usd": 0,
        "provider": "local llama.cpp loopback only",
        "raw_runs_sha256": sha256_file(raw_path),
        "blind_pairs_sha256": sha256_file(blind_path),
        "blind_key_sha256": sha256_file(out_dir / "blind_key.json"),
        "v1_integrity_verification": {
            "root_manifest": v1_root_verification,
            "run_manifest": v1_run_verification,
        },
        "acceptance_result": "NOT_EVALUATED",
        "limitations": [
            "This compares direct prompting and the HG-CTI prompt scaffold under a deterministic guard layer; it does not establish production performance.",
            "Trusted authority and rights context is supplied by fixed per-case fixtures and is not inferred from free-form model prose.",
            "Claim-ledger validation checks spans and evidence references, not semantic entailment; scoring must audit claim support.",
            "Raw model outputs are retained to measure guard interventions; only guarded outputs are the primary usefulness/critical-violation outputs.",
        ],
    }
    write_json(out_dir / "run_metadata.json", metadata)
    write_manifest(out_dir)
    print(json.dumps({
        "status": metadata["status"],
        "out_dir": str(out_dir),
        "case_count": len(cases),
        "response_count": len(raw_rows),
        "guard_interventions_baseline": metadata["guard_interventions_baseline"],
        "guard_interventions_candidate": metadata["guard_interventions_candidate"],
        "elapsed_total_seconds": metadata["elapsed_total_seconds"],
        "blind_pairs_sha256": metadata["blind_pairs_sha256"],
    }, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
