#!/usr/bin/env python3
"""Regenerate the source-integrity graph for selected HG2 files.

This graph inventories content hashes; it is not a trusted signature or an
independent assertion about the origin of a source file.
"""
from __future__ import annotations
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = Path("provenance/HG2_SOURCE_PROVENANCE_GRAPH_V1.json")
INVENTORY = [
    "README.md", "manifest.json",
    "contract/ARCHITECTURE_V1.md", "contract/AUTHENTICATION_V1.md",
    "contract/STATE_V1.md", "contract/ACCEPTANCE_MATRIX_V1.md",
    "hg/identity.py", "hg/auth.py", "hg/authority.py", "hg/history.py",
    "hg/phone_runtime.py", "hg/edge.py", "hg/provider.py", "hg/toolplane.py", "hg/agent.py",
    "tests/test_core.py", "tests/test_edge_schema_guard.py",
    "tests/test_native_intelligence_fixtures.py", "tests/test_auth.py",
    "tests/test_provider.py", "tests/test_toolplane.py", "tests/test_agent.py",
    "tests/test_contract_completeness.py", "scripts/update_provenance_graph.py",
]


def run_git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> int:
    try:
        base = run_git("merge-base", "HEAD", "origin/hg-genesis")
        branch = run_git("branch", "--show-current")
    except subprocess.CalledProcessError:
        raise SystemExit("Cannot establish canonical merge base; refusing to invent provenance.")
    if not base or not branch or branch == "hg-genesis":
        raise SystemExit("Run this tool from a non-canonical feature branch with origin/hg-genesis available.")
    nodes = []
    for rel in INVENTORY:
        path = ROOT / rel
        if not path.is_file():
            raise SystemExit(f"Required provenance input missing: {rel}")
        raw = path.read_bytes()
        git_blob_sha = run_git("hash-object", rel)
        role = "source" if rel.startswith("hg/") else "test" if rel.startswith("tests/") else "contract-or-documentation"
        nodes.append({"path": rel, "role": role, "bytes": len(raw),
                      "sha256": hashlib.sha256(raw).hexdigest(), "git_blob_sha": git_blob_sha})
    graph = {
        "schema": "HG2_SOURCE_PROVENANCE_GRAPH_V1",
        "repository": "OAI-GIANG/HG2",
        "canonical_branch": "hg-genesis",
        "candidate_branch": branch,
        "base_commit": base,
        "integrity_scope": "selected source, tests and contract/documentation files listed by this generator",
        "claim_level": "CONTENT_HASH_INTEGRITY_ONLY",
        "nodes": nodes,
        "limitations": [
            "This graph is generated from the candidate worktree and is not a signed or independent attestation.",
            "Matching SHA-256 and Git blob IDs establish content integrity for listed files, not semantic equivalence or clean-room origin.",
            "The graph excludes its own hash to avoid self-reference; the Git commit/tree binds the graph file.",
            "AI semantic behavior remains unverified until HG is evaluated against the V2.1 fixtures.",
        ],
    }
    target = ROOT / GRAPH_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(graph, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"PROVENANCE_GRAPH_WRITTEN nodes={len(nodes)} base={base} branch={branch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
