#!/usr/bin/env python3
"""Compare local source ZIP file trees with candidate upstream default-branch trees.

Requires an authenticated GitHub CLI session. A match binds the archive's file bytes to the
observed commit tree; a mismatch does not prove the archive is illegitimate, only that this
candidate revision is not an exact match.
"""
import hashlib, json, subprocess, sys, zipfile
from pathlib import Path

ARCHIVE_ROOT = Path("/storage/emulated/0/Download")
PROJECTS = {
    "memXT-main.zip": "Yupcha/memxt",
    "friday-main.zip": "debpalash/friday",
    "pp-finder-main.zip": "yeswehack/pp-finder",
    "Dom-Explorer-main.zip": "yeswehack/Dom-Explorer",
    "vulnerable-code-snippets-main.zip": "yeswehack/vulnerable-code-snippets",
    "PwnFox-master.zip": "B-i-t-K/PwnFox",
    "ywh2bugtracker-master.zip": "yeswehack/ywh2bugtracker",
    "YesWeBurp-master.zip": "yeswehack/YesWeBurp",
    "yeswecaido-main.zip": "yeswehack/yeswecaido",
    "myopenvdp-master.zip": "yeswehack/my-open-vdp",
    "xsstools-master.zip": "yeswehack/xsstools",
    "burp-addon-tutorial-main.zip": "yeswehack/burp-addon-tutorial",
    "hoglet-main.zip": "debpalash/hoglet",
    "OpenGTM-main.zip": "debpalash/OpenGTM",
    "VoiceStudio-main.zip": "debpalash/VoiceStudio",
    "Opal-main.zip": "debpalash/Opal",
    "bootable-main.zip": "debpalash/bootable",
    "homebrew-memxt-main.zip": "Yupcha/homebrew-memxt",
}

def gh_json(endpoint):
    p = subprocess.run(["gh", "api", endpoint], text=True, capture_output=True, timeout=60)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout).strip()[:500])
    return json.loads(p.stdout)

def git_blob_sha(data):
    return hashlib.sha1(("blob " + str(len(data)) + "\0").encode() + data).hexdigest()

def compare(archive, repository):
    path = ARCHIVE_ROOT / archive
    if not path.is_file():
        return {"archive": archive, "repository": repository, "result": "ARCHIVE_MISSING"}
    try:
        repo = gh_json("repos/" + repository)
        branch = repo["default_branch"]
        commit = gh_json("repos/" + repository + "/commits/" + branch)["sha"]
        tree = gh_json("repos/" + repository + "/git/trees/" + commit + "?recursive=1")
        if tree.get("truncated"):
            return {"archive": archive, "repository": repository, "branch": branch,
                    "commit": commit, "result": "TREE_TRUNCATED"}
        remote = {x["path"]: x["sha"] for x in tree.get("tree", []) if x.get("type") == "blob"}
        with zipfile.ZipFile(path) as z:
            files = {n: z.read(n) for n in z.namelist() if not n.endswith("/")}
        roots = {n.split("/", 1)[0] for n in files}
        if len(roots) != 1:
            return {"archive": archive, "repository": repository, "commit": commit,
                    "result": "ZIP_ROOT_AMBIGUOUS", "roots": sorted(roots)[:10]}
        root = next(iter(roots))
        local = {n[len(root)+1:]: git_blob_sha(data) for n, data in files.items() if n.startswith(root + "/")}
        missing = sorted(set(remote) - set(local))
        extra = sorted(set(local) - set(remote))
        changed = sorted(p for p in set(local) & set(remote) if local[p] != remote[p])
        result = "TREE_MATCH" if not missing and not extra and not changed else "TREE_MISMATCH"
        return {"archive": archive, "repository": repository, "default_branch": branch,
                "commit": commit, "result": result, "archive_file_count": len(local),
                "upstream_blob_count": len(remote), "missing_local_count": len(missing),
                "extra_local_count": len(extra), "content_mismatch_count": len(changed),
                "missing_local_sample": missing[:5], "extra_local_sample": extra[:5],
                "content_mismatch_sample": changed[:5]}
    except Exception as e:
        return {"archive": archive, "repository": repository, "result": "LOOKUP_FAILED",
                "error": str(e)[:500]}

results = [compare(a, r) for a, r in PROJECTS.items()]
out = {"schema": "HG-CTI-UPSTREAM-SNAPSHOT-COMPARISON-V1", "archive_count": len(results),
       "tree_matches": sum(x["result"] == "TREE_MATCH" for x in results), "results": results,
       "limitations": ["A tree match establishes byte equality to the observed commit tree, not license compatibility or semantic correctness.",
                       "A mismatch does not identify the exact historical revision.",
                       "Repository identity mappings must still be checked against project metadata."]}
print(json.dumps(out, indent=2))
sys.exit(0 if all(x["result"] in {"TREE_MATCH", "TREE_MISMATCH"} for x in results) else 2)
