"""Candidate, test-run, artifact, and live-module integrity evidence.

This module records deterministic local identity and linkage. Hashes establish
byte integrity only; they do not prove who produced or authorized an artifact.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import subprocess
import sys
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import CodeType, FunctionType, ModuleType
from typing import Any, Mapping, Sequence

SCHEMA = "HG2_PROVENANCE_MANIFEST_V1"
RUN_SCHEMA = "HG2_TEST_RUN_V1"
REASON_CODES = {
    "MISSING": "PROV_MISSING",
    "MISMATCH": "PROV_MISMATCH",
    "UNVERIFIABLE": "PROV_UNVERIFIABLE",
    "UNTRUSTED_SOURCE": "PROV_UNTRUSTED_SOURCE",
    "BLOCKED": "PROV_BLOCKED",
    "CHAIN_BROKEN": "PROV_CHAIN_BROKEN",
    "CIRCULAR_EVIDENCE": "PROV_CIRCULAR_EVIDENCE",
    "ID_COLLISION": "PROV_ID_COLLISION",
    "CANONICALIZATION_INVALID": "PROV_CANONICALIZATION_INVALID",
    "MANIFEST_BINDING_INVALID": "PROV_MANIFEST_BINDING_INVALID",
    "RUN_REPLAY": "PROV_RUN_REPLAY",
    "RUNTIME_IDENTITY_INCOMPLETE": "PROV_RUNTIME_IDENTITY_INCOMPLETE",
    "ARTIFACT_HASH_MISMATCH": "PROV_ARTIFACT_HASH_MISMATCH",
    "POLICY_INVALID": "PROV_POLICY_INVALID",
}
EXCLUDED_COMPONENTS = {
    ".git": "Git object database and local ref storage; commit/tree are recorded separately",
    "__pycache__": "Generated Python bytecode cache, never a source input",
    ".pytest_cache": "Generated test cache, never a source input",
    ".mypy_cache": "Generated type-check cache, never a source input",
    ".ruff_cache": "Generated lint cache, never a source input",
    ".tox": "Generated test environment, never a source input",
    ".venv": "Generated virtual environment, never a source input",
    "venv": "Generated virtual environment, never a source input",
    "node_modules": "Generated third-party install tree, never a source input",
}
IDENTITY_MODULES = (
    "hg.phone_runtime",
    "hg.sync",
    "hg.sync_auth",
    "hg.authority",
    "hg.history",
    "hg.provenance",
)


class ProvenanceError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def canonical_json(value: Any) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ProvenanceError(REASON_CODES["CANONICALIZATION_INVALID"],
                              "value cannot be serialized canonically") from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | os.PathLike[str]) -> str:
    """Hash bytes from one stable, non-symlink file descriptor."""
    file_path = os.fspath(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(file_path, flags)
    except FileNotFoundError as exc:
        raise ProvenanceError(REASON_CODES["MISSING"], f"file missing: {file_path}") from exc
    except OSError as exc:
        raise ProvenanceError(REASON_CODES["UNVERIFIABLE"], f"cannot open file safely: {file_path}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ProvenanceError(REASON_CODES["UNVERIFIABLE"], f"not a regular file: {file_path}")
        hasher = hashlib.sha256()
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
        after = os.fstat(fd)
        current = os.stat(file_path, follow_symlinks=False)
        stable = (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns
        ) == (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns
        )
        same_path = (after.st_dev, after.st_ino) == (current.st_dev, current.st_ino)
        if not stable or not same_path:
            raise ProvenanceError(REASON_CODES["MISMATCH"], f"file changed while hashing: {file_path}")
        return hasher.hexdigest()
    finally:
        os.close(fd)


def _git(root: Path, *args: str) -> bytes:
    try:
        proc = subprocess.run(["git", "-C", str(root), *args], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ProvenanceError(REASON_CODES["UNVERIFIABLE"],
                              "required Git identity could not be read") from exc
    return proc.stdout.rstrip(b"\n")


def _git_metadata(root: Path) -> dict[str, Any]:
    head = _git(root, "rev-parse", "--verify", "HEAD").decode("ascii")
    tree = _git(root, "rev-parse", "--verify", "HEAD^{tree}").decode("ascii")
    status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    return {
        "commit_sha": head,
        "tree_sha": tree,
        "working_tree_clean": len(status) == 0,
        "working_tree_status_sha256": sha256_bytes(status),
        "working_tree_status_entry_count": sum(1 for item in status.split(b"\0") if item),
    }


def _relative_path(path: str) -> str:
    normalized = unicodedata.normalize("NFC", path.replace(os.sep, "/"))
    if normalized != path.replace(os.sep, "/"):
        raise ProvenanceError(REASON_CODES["CANONICALIZATION_INVALID"],
                              f"path is not Unicode NFC: {path!r}")
    if (not normalized or normalized.startswith("/") or "\\" in normalized
            or "\x00" in normalized or any(part in ("", ".", "..") for part in normalized.split("/"))):
        raise ProvenanceError(REASON_CODES["CANONICALIZATION_INVALID"],
                              f"unsafe or non-canonical relative path: {path!r}")
    return normalized


def _is_excluded(rel: str) -> tuple[bool, str | None]:
    parts = rel.split("/")
    for part in parts:
        if part in EXCLUDED_COMPONENTS:
            return True, EXCLUDED_COMPONENTS[part]
    return False, None


def _scan_inventory(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    inventory: list[dict[str, Any]] = []
    exclusions: dict[str, str] = {}
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        cur = Path(current)
        kept_dirs: list[str] = []
        for name in sorted(dirs):
            p = cur / name
            rel = _relative_path(p.relative_to(root).as_posix())
            excluded, reason = _is_excluded(rel)
            if p.is_symlink():
                if excluded:
                    exclusions[rel] = str(reason)
                    continue
                raise ProvenanceError(REASON_CODES["UNVERIFIABLE"], f"candidate contains symlink directory: {rel}")
            if excluded:
                exclusions[rel] = str(reason)
                continue
            if not p.is_dir():
                raise ProvenanceError(REASON_CODES["UNVERIFIABLE"], f"non-directory entry in directory list: {rel}")
            kept_dirs.append(name)
        dirs[:] = kept_dirs
        for name in sorted(files):
            p = cur / name
            rel = _relative_path(p.relative_to(root).as_posix())
            excluded, reason = _is_excluded(rel)
            if excluded:
                exclusions[rel] = str(reason)
                continue
            if p.is_symlink():
                raise ProvenanceError(REASON_CODES["UNVERIFIABLE"], f"candidate contains symlink file: {rel}")
            try:
                before = p.stat(follow_symlinks=False)
            except OSError as exc:
                raise ProvenanceError(REASON_CODES["UNVERIFIABLE"], f"cannot stat candidate file: {rel}") from exc
            if not stat.S_ISREG(before.st_mode):
                raise ProvenanceError(REASON_CODES["UNVERIFIABLE"], f"candidate contains special file: {rel}")
            file_hash = sha256_file(p)
            after = p.stat(follow_symlinks=False)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns
            ):
                raise ProvenanceError(REASON_CODES["MISMATCH"], f"candidate file changed during inventory: {rel}")
            inventory.append({
                "path": rel,
                "size": after.st_size,
                "executable": bool(after.st_mode & 0o111),
                "sha256": file_hash,
            })
    inventory.sort(key=lambda row: row["path"])
    return inventory, [{"path": p, "reason": exclusions[p]} for p in sorted(exclusions)]


def _manifest_body(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in manifest.items() if k != "manifest_id"}


def snapshot_candidate(
    repo: str | os.PathLike[str],
    *,
    repository_identity: str = "OAI-GIANG/HG2",
) -> dict[str, Any]:
    root = Path(repo).resolve(strict=True)
    if not root.is_dir():
        raise ProvenanceError(REASON_CODES["UNVERIFIABLE"], "repository root is not a directory")
    git_before = _git_metadata(root)
    inventory, excluded = _scan_inventory(root)
    # A second complete pass detects directory-entry changes that a per-file
    # descriptor check alone cannot observe (for example, a file added after walk).
    inventory_check, excluded_check = _scan_inventory(root)
    git_after = _git_metadata(root)
    if git_before != git_after or inventory != inventory_check or excluded != excluded_check:
        raise ProvenanceError(REASON_CODES["MISMATCH"], "Git identity/status or inventory changed during snapshot")
    inventory_sha = sha256_bytes(canonical_json(inventory))
    exclusion_policy = [{"component": k, "reason": EXCLUDED_COMPONENTS[k]}
                        for k in sorted(EXCLUDED_COMPONENTS)]
    policy_sha = sha256_bytes(canonical_json({"schema": SCHEMA, "exclusion_policy": exclusion_policy}))
    identity_fields = {
        "schema": SCHEMA,
        "repository_identity": repository_identity,
        "commit_sha": git_before["commit_sha"],
        "tree_sha": git_before["tree_sha"],
        "working_tree_clean": git_before["working_tree_clean"],
        "working_tree_status_sha256": git_before["working_tree_status_sha256"],
        "inventory_sha256": inventory_sha,
        "exclusion_policy_sha256": policy_sha,
    }
    candidate_id = sha256_bytes(b"HG2-CANDIDATE-V1\0" + canonical_json(identity_fields))
    body = {
        **identity_fields,
        "candidate_id": candidate_id,
        "inventory_entry_count": len(inventory),
        "inventory": inventory,
        "inventory_sha256": inventory_sha,
        "exclusion_policy": exclusion_policy,
        "excluded_entries": excluded,
        "policy_sha256": policy_sha,
        "hash_semantics": "SHA-256 binds observed bytes; it does not authenticate identity or authority",
        "evidence_scope": "LOCAL_ONLY",
        "limitations": [
            "Git commit/tree metadata and local inventory are observations from this environment.",
            "Excluded generated directories follow the fixed versioned exclusion policy above."
        ],
    }
    body["manifest_id"] = sha256_bytes(canonical_json(body))
    return body


def verify_manifest(repo: str | os.PathLike[str], manifest: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(manifest, Mapping) or manifest.get("schema") != SCHEMA:
        raise ProvenanceError(REASON_CODES["MANIFEST_BINDING_INVALID"], "unknown manifest schema")
    body = _manifest_body(manifest)
    expected_manifest_id = sha256_bytes(canonical_json(body))
    if manifest.get("manifest_id") != expected_manifest_id:
        raise ProvenanceError(REASON_CODES["MISMATCH"], "manifest self-binding does not match")
    inventory = manifest.get("inventory")
    if not isinstance(inventory, list):
        raise ProvenanceError(REASON_CODES["MISSING"], "manifest inventory missing")
    if sha256_bytes(canonical_json(inventory)) != manifest.get("inventory_sha256"):
        raise ProvenanceError(REASON_CODES["MISMATCH"], "manifest inventory digest does not match")
    actual = snapshot_candidate(repo, repository_identity=str(manifest.get("repository_identity", "")))
    if actual.get("candidate_id") != manifest.get("candidate_id"):
        raise ProvenanceError(REASON_CODES["MISMATCH"], "repository candidate identity changed since snapshot")
    if actual.get("manifest_id") != manifest.get("manifest_id"):
        raise ProvenanceError(REASON_CODES["MISMATCH"], "observed snapshot differs from manifest")
    return {
        "status": "PASS",
        "candidate_id": actual["candidate_id"],
        "manifest_id": actual["manifest_id"],
        "inventory_sha256": actual["inventory_sha256"],
        "working_tree_clean": actual["working_tree_clean"],
        "evidence_scope": "LOCAL_ONLY",
        "reason_codes": [],
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_test_command(
    repo: str | os.PathLike[str],
    manifest_path: str | os.PathLike[str],
    output_dir: str | os.PathLike[str],
    command: Sequence[str],
) -> dict[str, Any]:
    root = Path(repo).resolve(strict=True)
    raw_manifest_file = Path(manifest_path).expanduser()
    raw_output_dir = Path(output_dir).expanduser()
    if raw_manifest_file.is_symlink():
        raise ProvenanceError(REASON_CODES["UNVERIFIABLE"], "manifest path must not be a symlink")
    if raw_output_dir.is_symlink():
        raise ProvenanceError(REASON_CODES["UNVERIFIABLE"], "output directory path must not be a symlink")
    manifest_file = raw_manifest_file.resolve(strict=True)
    out = raw_output_dir.resolve()
    if not command or any(not isinstance(item, str) for item in command):
        raise ProvenanceError(REASON_CODES["MISSING"], "test command argv is required")
    try:
        out.relative_to(root)
    except ValueError:
        pass
    else:
        raise ProvenanceError(REASON_CODES["POLICY_INVALID"], "evidence output directory must be outside candidate repository")
    if out.exists():
        raise ProvenanceError(REASON_CODES["MISMATCH"], "output directory must be new to prevent artifact overwrite")
    if manifest_file.is_symlink():
        raise ProvenanceError(REASON_CODES["UNVERIFIABLE"], "manifest path must not be a symlink")
    manifest_bytes = manifest_file.read_bytes()
    manifest_initial_hash = sha256_file(manifest_file)
    if manifest_initial_hash != sha256_bytes(manifest_bytes):
        raise ProvenanceError(REASON_CODES["MISMATCH"], "manifest changed while being read")
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProvenanceError(REASON_CODES["MANIFEST_BINDING_INVALID"], "manifest is not valid UTF-8 JSON") from exc
    pre = verify_manifest(root, manifest)
    out.mkdir(parents=True, exist_ok=False)
    stdout_path, stderr_path = out / "stdout.log", out / "stderr.log"
    start = _utc_now()
    try:
        proc = subprocess.Popen(list(command), cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        process_pid = proc.pid
        stdout_bytes, stderr_bytes = proc.communicate()
        return_code = proc.returncode
    except OSError as exc:
        stdout_bytes, stderr_bytes = b"", str(exc).encode("utf-8", "replace")
        process_pid = None
        return_code = 127
    end = _utc_now()
    stdout_path.write_bytes(stdout_bytes)
    stderr_path.write_bytes(stderr_bytes)
    stdout_hash, stderr_hash = sha256_file(stdout_path), sha256_file(stderr_path)
    try:
        manifest_after_hash = sha256_file(manifest_file)
        if manifest_after_hash != manifest_initial_hash:
            raise ProvenanceError(REASON_CODES["MISMATCH"], "manifest bytes changed during test run")
        post = verify_manifest(root, manifest)
        stable = post["candidate_id"] == pre["candidate_id"]
        source_status = "PASS" if stable else "BLOCKED"
    except ProvenanceError as exc:
        post = {"status": "BLOCKED", "reason_code": exc.code, "message": exc.message}
        stable = False
        source_status = "BLOCKED"
    run_id = uuid.uuid4().hex
    result_status = "PASS" if return_code == 0 and stable else ("FAIL" if return_code != 0 and stable else "BLOCKED")
    run_doc = {
        "schema": RUN_SCHEMA,
        "test_run_id": run_id,
        "candidate_id": manifest["candidate_id"],
        "manifest_id": manifest["manifest_id"],
        "manifest_file_sha256": sha256_bytes(manifest_bytes),
        "repository_identity": manifest["repository_identity"],
        "command_argv": list(command),
        "cwd_repo_relative": ".",
        "pid": process_pid,
        "started_at_utc": start,
        "finished_at_utc": end,
        "return_code": return_code,
        "source_identity_status": source_status,
        "candidate_before_sha256": pre["candidate_id"],
        "candidate_after_sha256": post.get("candidate_id"),
        "stdout": {"path": stdout_path.name, "size": len(stdout_bytes), "sha256": stdout_hash},
        "stderr": {"path": stderr_path.name, "size": len(stderr_bytes), "sha256": stderr_hash},
        "environment": {
            "python": sys.version,
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "status": result_status,
        "evidence_scope": "LOCAL_ONLY",
        "reason_codes": [] if result_status == "PASS" else (
            ["PROV_TEST_COMMAND_FAILED"] if return_code != 0 and stable else ["PROV_CHAIN_BROKEN"]
        ),
        "limitations": [
            "This record binds local source, command, process result, and log bytes only.",
            "It does not establish remote runtime state or who authorized the run."
        ],
    }
    run_path = out / "test-run.json"
    raw_run = canonical_json(run_doc)
    run_path.write_bytes(raw_run)
    (out / "test-run.json.sha256").write_text(sha256_bytes(raw_run) + "  test-run.json\n", encoding="ascii")
    return {**run_doc, "output_dir": str(out), "test_run_sha256": sha256_bytes(raw_run)}


def verify_test_run(run_path: str | os.PathLike[str], *, manifest_path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Verify a saved run record and every referenced artifact; local integrity only."""
    raw_path = Path(run_path).expanduser()
    if raw_path.is_symlink():
        raise ProvenanceError(REASON_CODES["UNVERIFIABLE"], "test-run path must not be a symlink")
    path = raw_path.resolve(strict=True)
    sidecar = path.with_name(path.name + ".sha256")
    if sidecar.is_symlink() or not sidecar.is_file():
        raise ProvenanceError(REASON_CODES["MISSING"], "test-run SHA-256 sidecar missing or unsafe")
    raw = path.read_bytes()
    expected_sidecar = sidecar.read_text(encoding="ascii").strip().split()
    actual_hash = sha256_bytes(raw)
    if len(expected_sidecar) != 2 or expected_sidecar[0] != actual_hash or expected_sidecar[1] != path.name:
        raise ProvenanceError(REASON_CODES["ARTIFACT_HASH_MISMATCH"], "test-run bytes do not match sidecar")
    try:
        doc = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProvenanceError(REASON_CODES["MISMATCH"], "test-run is not valid JSON") from exc
    if doc.get("schema") != RUN_SCHEMA or not isinstance(doc.get("test_run_id"), str) or not doc["test_run_id"]:
        raise ProvenanceError(REASON_CODES["MISMATCH"], "test-run schema or identity invalid")
    artifact_results = {}
    for key in ("stdout", "stderr"):
        desc = doc.get(key)
        if not isinstance(desc, dict) or not isinstance(desc.get("path"), str):
            raise ProvenanceError(REASON_CODES["MISSING"], f"{key} artifact descriptor missing")
        name = desc["path"]
        if os.path.basename(name) != name or name in ("", ".", ".."):
            raise ProvenanceError(REASON_CODES["MISMATCH"], f"unsafe {key} artifact path")
        artifact_path = path.parent / name
        if artifact_path.is_symlink() or not artifact_path.is_file():
            raise ProvenanceError(REASON_CODES["MISSING"], f"{key} artifact missing or unsafe")
        digest_value = sha256_file(artifact_path)
        size = artifact_path.stat().st_size
        if digest_value != desc.get("sha256") or size != desc.get("size"):
            raise ProvenanceError(REASON_CODES["ARTIFACT_HASH_MISMATCH"], f"{key} artifact does not match recorded bytes")
        artifact_results[key] = {"status": "PASS", "sha256": digest_value, "size": size}
    if manifest_path is not None:
        manifest_file = Path(manifest_path).expanduser()
        if manifest_file.is_symlink():
            raise ProvenanceError(REASON_CODES["UNVERIFIABLE"], "manifest path must not be a symlink")
        manifest_file = manifest_file.resolve(strict=True)
        manifest_raw = manifest_file.read_bytes()
        if sha256_bytes(manifest_raw) != doc.get("manifest_file_sha256"):
            raise ProvenanceError(REASON_CODES["MISMATCH"], "run does not bind the supplied manifest bytes")
        try:
            manifest = json.loads(manifest_raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProvenanceError(REASON_CODES["MANIFEST_BINDING_INVALID"], "manifest is invalid JSON") from exc
        if manifest.get("candidate_id") != doc.get("candidate_id") or manifest.get("manifest_id") != doc.get("manifest_id"):
            raise ProvenanceError(REASON_CODES["MISMATCH"], "run candidate/manifest identity differs")
    return {
        "evidence_integrity_status": "PASS",
        "test_outcome": doc.get("status"),
        "test_run_id": doc["test_run_id"],
        "candidate_id": doc.get("candidate_id"),
        "manifest_id": doc.get("manifest_id"),
        "test_run_sha256": actual_hash,
        "artifacts": artifact_results,
        "candidate_binding_status": "PASS" if manifest_path is not None else "UNVERIFIED_NO_MANIFEST",
        "evidence_scope": doc.get("evidence_scope", "UNKNOWN"),
        "note": "Artifact bytes and local linkage verified only; this result does not establish remote runtime state or authorization.",
    }


def _const_shape(value: Any) -> Any:
    if isinstance(value, CodeType):
        return _code_shape(value)
    if value is None or type(value) in (bool, int, float, complex, str, type(Ellipsis)):
        return {"type": type(value).__name__, "repr": repr(value)}
    if isinstance(value, bytes):
        return {"type": "bytes", "size": len(value), "sha256": sha256_bytes(value)}
    if isinstance(value, tuple):
        return {"type": "tuple", "items": [_const_shape(v) for v in value]}
    if isinstance(value, frozenset):
        items = [_const_shape(v) for v in value]
        return {"type": "frozenset", "items": sorted(items, key=lambda v: canonical_json(v))}
    return {"type": f"{type(value).__module__}.{type(value).__qualname__}"}


def _code_shape(code: CodeType) -> dict[str, Any]:
    return {
        "bytecode_sha256": sha256_bytes(code.co_code),
        "argcount": code.co_argcount,
        "posonlyargcount": code.co_posonlyargcount,
        "kwonlyargcount": code.co_kwonlyargcount,
        "flags": code.co_flags,
        "stacksize": code.co_stacksize,
        "exceptiontable_sha256": sha256_bytes(getattr(code, "co_exceptiontable", b"")),
        "names": list(code.co_names),
        "varnames": list(code.co_varnames),
        "freevars": list(code.co_freevars),
        "cellvars": list(code.co_cellvars),
        "constants": [_const_shape(v) for v in code.co_consts],
    }


def _module_code_inventory(module: ModuleType) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, obj in sorted(vars(module).items()):
        fn = None
        if isinstance(obj, FunctionType) and obj.__module__ == module.__name__:
            fn = obj
        elif isinstance(obj, type) and obj.__module__ == module.__name__:
            for member_name, member in sorted(vars(obj).items()):
                raw = member.__func__ if isinstance(member, (staticmethod, classmethod)) else member
                if isinstance(raw, property):
                    funcs = [raw.fget, raw.fset, raw.fdel]
                else:
                    funcs = [raw]
                for method in funcs:
                    if isinstance(method, FunctionType):
                        rows.append({"name": f"{name}.{member_name}", "code": _code_shape(method.__code__)})
        if fn is not None:
            rows.append({"name": name, "code": _code_shape(fn.__code__)})
    rows.sort(key=lambda row: row["name"])
    return rows


def loaded_module_identity(module_names: Sequence[str] | None = None) -> dict[str, Any]:
    """Fingerprint modules already loaded in THIS process; never inspect other PIDs."""
    if not module_names:
        module_names = IDENTITY_MODULES
    modules = []
    missing = []
    for name in module_names:
        module = sys.modules.get(name)
        if not isinstance(module, ModuleType):
            missing.append(name)
            continue
        origin = getattr(getattr(module, "__spec__", None), "origin", None)
        file_path = getattr(module, "__file__", None)
        disk_hash = None
        if isinstance(file_path, str) and os.path.isfile(file_path):
            try:
                disk_hash = sha256_file(file_path)
            except ProvenanceError:
                disk_hash = None
        code_inventory = _module_code_inventory(module)
        code_digest = sha256_bytes(canonical_json(code_inventory))
        modules.append({
            "name": name,
            "spec_origin": origin,
            "file": os.path.realpath(file_path) if isinstance(file_path, str) else None,
            "disk_sha256": disk_hash,
            "loaded_code_inventory_sha256": code_digest,
            "loaded_code_object_count": len(code_inventory),
        })
    proc_exe = None
    proc_stat_start_ticks = None
    try:
        proc_exe = os.path.realpath("/proc/self/exe")
        stat_line = Path("/proc/self/stat").read_text(encoding="ascii")
        # The comm field can contain spaces or parentheses; split after the final ')'.
        suffix = stat_line[stat_line.rfind(")") + 2:].split()
        proc_stat_start_ticks = int(suffix[19])  # field 22 (starttime), after pid+comm
    except (OSError, ValueError, IndexError):
        pass
    core = {
        "schema": "HG2_LOADED_MODULE_IDENTITY_V1",
        "pid": os.getpid(),
        "process_start_ticks": proc_stat_start_ticks,
        "executable": proc_exe or sys.executable,
        "cwd": os.path.realpath(os.getcwd()),
        "python": sys.version,
        "modules": modules,
        "missing_modules": missing,
    }
    core["module_identity_sha256"] = sha256_bytes(canonical_json(core))
    core["status"] = "OBSERVED_UNMATCHED" if not missing and all(m["disk_sha256"] for m in modules) else "BLOCKED"
    core["source_comparison_status"] = "NOT_RUN_NO_EXPECTED_CODE_FINGERPRINT"
    core["evidence_scope"] = "PROCESS_LOCAL_OBSERVATION"
    core["limitations"] = [
        "Loaded code fingerprint covers Python code objects and selected metadata, not mutable globals, native extensions, or all interpreter state.",
        "disk_sha256 describes the path currently on disk and is not equivalent to loaded_code_inventory_sha256.",
        "The report is a process-local observation and does not establish remote process state."
    ]
    return core
