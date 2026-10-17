"""Deterministic runtime-source manifest used by the phone API's provenance gate."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import platform
import re
import sys
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def runtime_manifest(root: str | Path | None = None) -> dict:
    repo_root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    module_dir = repo_root / "hg"
    ui_file = repo_root / "ui" / "index.html"
    paths = sorted(module_dir.glob("*.py")) + [ui_file]
    if not paths or not ui_file.is_file():
        raise RuntimeError("runtime source set is incomplete")
    files = []
    for path in paths:
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(repo_root):
            raise RuntimeError("runtime source contains a missing or escaped file")
        files.append({
            "path": path.relative_to(repo_root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        })
    body = {"schema": "HG_RUNTIME_SOURCE_MANIFEST_V1", "files": files}
    return {**body, "manifest_sha256": hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()}


def runtime_identity(root: str | Path | None = None, *, commit: str | None = None) -> dict:
    repo_root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    manifest = runtime_manifest(repo_root)
    return {
        "git_commit": commit or os.environ.get("HG_BUILD_COMMIT", "UNDECLARED"),
        "source_manifest_sha256": manifest["manifest_sha256"],
        "source_file_count": len(manifest["files"]),
        "process_pid": os.getpid(),
        "python_version": platform.python_version(),
        "entrypoint": str((repo_root / "hg" / "server.py").resolve()),
    }


def validate_build(root: str | Path | None = None) -> dict:
    required = os.environ.get("HG_REQUIRE_BUILD_ID", "1").strip().lower() not in ("0", "false", "no")
    commit = os.environ.get("HG_BUILD_COMMIT", "")
    expected = os.environ.get("HG_EXPECTED_SOURCE_MANIFEST_SHA256", "")
    manifest = runtime_manifest(root)
    if required and not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError("HG_BUILD_COMMIT must be a 40-character lowercase Git SHA")
    if required and not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise RuntimeError("HG_EXPECTED_SOURCE_MANIFEST_SHA256 must be configured")
    if expected and not hmac.compare_digest(expected, manifest["manifest_sha256"]):
        raise RuntimeError("runtime source manifest does not match the approved expected digest")
    return {"ok": True, "required": required, "git_commit": commit or "UNDECLARED",
            "source_manifest_sha256": manifest["manifest_sha256"],
            "source_file_count": len(manifest["files"])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--identity", action="store_true")
    args = parser.parse_args()
    result = runtime_identity(args.root) if args.identity else runtime_manifest(args.root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
