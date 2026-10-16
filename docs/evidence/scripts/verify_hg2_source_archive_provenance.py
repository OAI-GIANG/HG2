#!/usr/bin/env python3
"""Verify supplied ZIP comments, GitHub commit/tree identity, and Git blob contents.

The verifier reads ZIP members in place; it does not extract or execute archive content.
Requires Python 3 and the GitHub CLI (gh) authenticated for public API access.
"""
from __future__ import annotations
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

SOURCES = [
    {
        "archive": "/storage/emulated/0/Download/codebase-memory-mcp-main.zip",
        "repo": "DeusData/codebase-memory-mcp",
        "prefix": "codebase-memory-mcp-main/",
    },
    {
        "archive": "/storage/emulated/0/Download/awesome-mcp-servers-3-main.zip",
        "repo": "appcypher/awesome-mcp-servers",
        "prefix": "awesome-mcp-servers-3-main/",
    },
    {
        "archive": "/storage/emulated/0/Download/public-apis-master.zip",
        "repo": "public-apis/public-apis",
        "prefix": "public-apis-master/",
    },
    {
        "archive": "/storage/emulated/0/Download/myopenvdp-master.zip",
        "repo": "yeswehack/myopenvdp",
        "prefix": "myopenvdp-master/",
    },
]


def gh_json(endpoint: str) -> dict:
    result = subprocess.run(
        ["gh", "api", endpoint],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    return json.loads(result.stdout)


def git_blob_sha(data: bytes) -> str:
    header = b"blob " + str(len(data)).encode("ascii") + bytes([0])
    return hashlib.sha1(header + data).hexdigest()


def ignored_by_export_attributes(path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if pattern == "/.github" and (path == ".github" or path.startswith(".github/")):
            return True
        if pattern == "README.md" and path.rsplit("/", 1)[-1] == "README.md":
            return True
        if pattern == "/build" and (path == "build" or path.startswith("build/")):
            return True
        if pattern == ".travis.yml" and path == ".travis.yml":
            return True
    return False


def verify_source(source: dict) -> dict:
    archive_path = Path(source["archive"])
    archive_bytes_sha = hashlib.sha256()
    with archive_path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            archive_bytes_sha.update(block)
    with zipfile.ZipFile(archive_path) as archive:
        commit = archive.comment.decode("ascii", "strict")
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError(f"ZIP comment is not a 40-character lowercase SHA-1: {archive_path.name}")
        commit_info = gh_json(f"repos/{source['repo']}/commits/{commit}")
        if commit_info.get("sha") != commit:
            raise ValueError(f"GitHub commit SHA does not match ZIP comment for {archive_path.name}")
        tree_sha = commit_info["commit"]["tree"]["sha"]
        tree_info = gh_json(f"repos/{source['repo']}/git/trees/{tree_sha}?recursive=1")
        if tree_info.get("truncated"):
            raise ValueError(f"GitHub recursive tree was truncated for {source['repo']}@{commit}")
        expected = {
            item["path"]: {"blob_sha1": item["sha"], "mode": item["mode"]}
            for item in tree_info["tree"] if item["type"] == "blob"
        }
        actual = {}
        for info in archive.infolist():
            if info.is_dir():
                continue
            if not info.filename.startswith(source["prefix"]):
                raise ValueError(f"Archive member outside expected root: {info.filename}")
            relative = info.filename[len(source["prefix"]):]
            content = archive.read(info)
            actual[relative] = {
                "blob_sha1": git_blob_sha(content),
                "bytes": len(content),
            }
        attrs = archive.read(source["prefix"] + ".gitattributes").decode("utf-8", "replace") if source["prefix"] + ".gitattributes" in archive.namelist() else ""
        export_patterns = []
        for line in attrs.splitlines():
            parts = line.split()
            if len(parts) >= 2 and "export-ignore" in parts[1:]:
                export_patterns.append(parts[0])
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        changed = sorted(
            path for path in set(actual) & set(expected)
            if actual[path]["blob_sha1"] != expected[path]["blob_sha1"]
        )
        excluded = sorted(path for path in missing if ignored_by_export_attributes(path, export_patterns))
        unexplained_missing = sorted(set(missing) - set(excluded))
        status = (
            "VERIFIED_EXACT_COMMIT_CONTENT_WITH_EXPORT_IGNORE_EXCLUSIONS"
            if not extra and not changed and not unexplained_missing and not tree_info.get("truncated")
            else "MISMATCH"
        )
        return {
            "archive_filename": archive_path.name,
            "archive_path_on_device": str(archive_path),
            "archive_bytes": archive_path.stat().st_size,
            "archive_sha256": archive_bytes_sha.hexdigest(),
            "zip_comment_commit_candidate": commit,
            "github_commit_sha_verified": commit_info["sha"],
            "github_commit_url": commit_info["html_url"],
            "commit_date": commit_info["commit"]["committer"]["date"],
            "commit_message": commit_info["commit"]["message"].splitlines()[0],
            "tree_sha": tree_sha,
            "tree_url": f"https://github.com/{source['repo']}/tree/{commit}",
            "github_tree_truncated": tree_info.get("truncated", False),
            "tracked_blob_count_in_commit_tree": len(expected),
            "archive_file_count": len(actual),
            "archive_member_crc_verified": True,
            "missing_from_archive": missing,
            "export_ignore_patterns_from_archived_gitattributes": export_patterns,
            "missing_paths_explained_by_export_ignore": excluded,
            "unexplained_missing_paths": unexplained_missing,
            "extra_archive_paths": extra,
            "content_blob_mismatch_paths": changed,
            "path_and_blob_match_for_included_files": not extra and not changed,
            "status": status,
        }


def main() -> int:
    verifier_path = Path(__file__)
    results = {
        "schema": "HG2_SOURCE_ARCHIVE_PROVENANCE_RESULT_V1",
        "verified_at_local": datetime.now().astimezone().isoformat(),
        "method": [
            "Read ZIP comment as a candidate immutable commit SHA; do not infer revision from filename or branch tip.",
            "Resolve that exact SHA through GitHub commit API and record the immutable tree SHA.",
            "Fetch the recursive Git tree for that tree SHA; reject truncated tree results.",
            "Read each archive member in place without extracting or executing it and compute Git blob SHA-1.",
            "Compare archive relative paths and blob IDs against the immutable tree.",
            "Permit missing paths only when the archived .gitattributes explicitly marks them export-ignore and every missing path matches those rules.",
            "Record archive SHA-256 separately to bind the exact supplied ZIP bytes.",
        ],
        "verifier": {
            "path": str(verifier_path),
            "sha256": hashlib.sha256(verifier_path.read_bytes()).hexdigest(),
            "python_version": sys.version,
            "uses_archive_extraction": False,
            "executes_archive_content": False,
        },
        "sources": [verify_source(source) for source in SOURCES],
    }
    results["overall"] = (
        "PASS_ALL_FOUR_ARCHIVES_PROVEN_TO_EXACT_COMMIT_CONTENT"
        if all(item["status"] == "VERIFIED_EXACT_COMMIT_CONTENT_WITH_EXPORT_IGNORE_EXCLUSIONS" for item in results["sources"])
        else "BLOCKED_SOURCE_PROVENANCE"
    )
    output = Path("docs/evidence/HG2_SOURCE_PROVENANCE_RESULT_20261014.json")
    output.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for item in results["sources"]:
        print(
            f"{item['archive_filename']}: {item['status']}; "
            f"commit={item['github_commit_sha_verified']}; tree={item['tree_sha']}; "
            f"files={item['archive_file_count']}/{item['tracked_blob_count_in_commit_tree']}; "
            f"missing={len(item['missing_from_archive'])}; unexplained={len(item['unexplained_missing_paths'])}; "
            f"archive_sha256={item['archive_sha256']}"
        )
    print(f"OVERALL={results['overall']}")
    print(f"RESULT={output}")
    return 0 if results["overall"] == "PASS_ALL_FOUR_ARCHIVES_PROVEN_TO_EXACT_COMMIT_CONTENT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
