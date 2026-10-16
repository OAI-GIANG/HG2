#!/usr/bin/env python3
"""HG2 provenance CLI; writes manifests and run evidence outside the candidate tree."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Make repository imports work when invoked as `python tools/hg_provenance.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hg.provenance import (
    ProvenanceError,
    canonical_json,
    loaded_module_identity,
    run_test_command,
    snapshot_candidate,
    verify_manifest,
    verify_test_run,
    sha256_bytes,
)


def _outside_repo(repo: Path, destination: Path) -> Path:
    dest = destination.resolve()
    try:
        dest.relative_to(repo.resolve())
    except ValueError:
        return dest
    raise ProvenanceError("PROV_POLICY_INVALID", "output must be outside repository")


def command_snapshot(args) -> int:
    root = Path(args.repo).resolve(strict=True)
    output = _outside_repo(root, Path(args.output))
    if output.exists():
        raise ProvenanceError("PROV_MISMATCH", "output path already exists; overwrite is forbidden")
    manifest = snapshot_candidate(root, repository_identity=args.repository_identity)
    raw = canonical_json(manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    receipt = {
        "status": "PASS",
        "candidate_id": manifest["candidate_id"],
        "manifest_id": manifest["manifest_id"],
        "manifest_file_sha256": sha256_bytes(raw),
        "inventory_entries": manifest["inventory_entry_count"],
        "working_tree_clean": manifest["working_tree_clean"],
        "evidence_scope": manifest["evidence_scope"],
        "output": str(output),
    }
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0


def command_verify(args) -> int:
    root = Path(args.repo).resolve(strict=True)
    raw_manifest_path = Path(args.manifest).expanduser()
    if raw_manifest_path.is_symlink():
        raise ProvenanceError("PROV_UNVERIFIABLE", "manifest path must not be a symlink")
    manifest_path = raw_manifest_path.resolve(strict=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = verify_manifest(root, manifest)
    result["manifest_file_sha256"] = sha256_bytes(manifest_path.read_bytes())
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


def command_run(args) -> int:
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    result = run_test_command(args.repo, args.manifest, args.out_dir, command)
    print(json.dumps(result, sort_keys=True, indent=2))
    if result["status"] == "PASS":
        return 0
    if result["status"] == "BLOCKED":
        return 2
    return 1


def command_verify_run(args) -> int:
    result = verify_test_run(args.run, manifest_path=args.manifest)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


def command_live(args) -> int:
    result = loaded_module_identity(args.modules or None)
    raw = canonical_json(result)
    if args.output:
        root = Path(args.repo).resolve(strict=True)
        output = _outside_repo(root, Path(args.output))
        if output.exists():
            raise ProvenanceError("PROV_MISMATCH", "output path already exists; overwrite is forbidden")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(raw)
    sys.stdout.buffer.write(raw)
    # Fingerprinting completed does not mean a source match was proven.
    return 0 if result["status"] == "OBSERVED_UNMATCHED" else 2


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="subcommand", required=True)
    snap = sub.add_parser("snapshot", help="bind Git metadata and stable file inventory")
    snap.add_argument("--repo", default=".")
    snap.add_argument("--repository-identity", default="OAI-GIANG/HG2")
    snap.add_argument("--output", required=True)
    snap.set_defaults(func=command_snapshot)
    ver = sub.add_parser("verify", help="re-hash and compare a candidate manifest")
    ver.add_argument("--repo", default=".")
    ver.add_argument("--manifest", required=True)
    ver.set_defaults(func=command_verify)
    run = sub.add_parser("run", help="run a command against a bound candidate and hash outputs")
    run.add_argument("--repo", default=".")
    run.add_argument("--manifest", required=True)
    run.add_argument("--out-dir", required=True)
    run.add_argument("command", nargs=argparse.REMAINDER)
    run.set_defaults(func=command_run)
    verify_run = sub.add_parser("verify-run", help="verify saved test-run and referenced artifact bytes")
    verify_run.add_argument("--run", required=True)
    verify_run.add_argument("--manifest")
    verify_run.set_defaults(func=command_verify_run)
    live = sub.add_parser("live", help="fingerprint modules loaded in the current process")
    live.add_argument("--repo", default=".")
    live.add_argument("--modules", nargs="*")
    live.add_argument("--output")
    live.set_defaults(func=command_live)
    return ap


def main() -> int:
    try:
        args = parser().parse_args()
        return args.func(args)
    except ProvenanceError as exc:
        print(json.dumps({"status": "BLOCKED", "reason_code": exc.code,
                          "message": exc.message}, sort_keys=True), file=sys.stderr)
        return 2
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason_code": "PROV_UNVERIFIABLE",
                          "message": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
