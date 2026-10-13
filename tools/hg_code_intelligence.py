"""HG Code Intelligence V1: read-only, standard-library Python source index.

This module is clean-room code. It does not execute repository code, install
packages, access the network, change authority, or mutate the analyzed tree.
It produces a bounded structural report; its graph is not a proof of runtime
behavior or a complete graph for languages it does not parse.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable

SCHEMA = "HG_CODE_INTELLIGENCE_V1"
ANALYZER_VERSION = "1.0.0"
DEFAULT_MAX_FILES = 20_000
DEFAULT_MAX_FILE_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 128 * 1024 * 1024

_EXCLUDED_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv",
    "venv", "env", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", "target", "coverage", ".idea", ".gradle",
})
_SECRET_DIRS = frozenset({".ssh", ".gnupg", "secrets", "credentials", "private"})
_SECRET_NAMES = frozenset({
    ".netrc", ".npmrc", "id_rsa", "id_dsa", "id_ed25519", "id_ecdsa",
    "credentials.json", "secrets.json", "secret.json", "service-account.json",
})
_SECRET_SUFFIXES = frozenset({".pem", ".key", ".p12", ".pfx", ".keystore"})
_SOURCE_SUFFIXES = frozenset({
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".kts", ".c", ".h", ".cc", ".cpp",
    ".hpp", ".cs", ".php", ".rb", ".swift", ".scala", ".sh", ".bash",
    ".json", ".yaml", ".yml", ".toml", ".xml", ".sql", ".gradle",
    ".properties", ".ini", ".cfg", ".lock", ".mk",
})
_SOURCE_FILENAMES = frozenset({
    "dockerfile", "containerfile", "makefile", "gnumakefile", "justfile",
    "requirements.txt", "pipfile", "gemfile", "go.mod",
})


class CodeIntelligenceError(ValueError):
    """Base class for rejected input or incomplete scans."""


class ResourceLimitError(CodeIntelligenceError):
    """Raised when a hard resource limit prevents a trustworthy scan."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_secret_path(relative: Path) -> bool:
    if any(part.lower() in _SECRET_DIRS for part in relative.parts[:-1]):
        return True
    name = relative.name.lower()
    if name in _SECRET_NAMES or name.startswith(".env"):
        return True
    return relative.suffix.lower() in _SECRET_SUFFIXES


def _is_source_file(relative: Path) -> bool:
    name = relative.name.lower()
    return (
        relative.suffix.lower() in _SOURCE_SUFFIXES
        or name in _SOURCE_FILENAMES
        or name.startswith("dockerfile.")
    )


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normal_relative_path(value: str) -> str:
    """Validate a repository-relative path without resolving arbitrary paths."""
    if not isinstance(value, str) or not value.strip():
        raise CodeIntelligenceError("CHANGED_PATH_EMPTY_OR_INVALID")
    candidate = Path(value)
    if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
        raise CodeIntelligenceError("CHANGED_PATH_OUTSIDE_ROOT")
    normalized = candidate.as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized or normalized == ".":
        raise CodeIntelligenceError("CHANGED_PATH_EMPTY_OR_INVALID")
    return normalized


def _discover(root: Path, max_files: int) -> tuple[list[tuple[Path, Path]], int, int, int]:
    """Return regular files, secret-exclusion count, symlink count, total seen.

    Directory and file symlinks are never followed. Directories are visited in
    stable lexical order. Secret file paths are not returned or recorded.
    """
    found: list[tuple[Path, Path]] = []
    secret_count = 0
    symlink_count = 0
    seen = 0
    stack = [root]
    root_resolved = root.resolve(strict=True)
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name, reverse=True)
        except OSError as exc:
            raise CodeIntelligenceError("DIRECTORY_READ_FAILED:" + current.relative_to(root).as_posix()) from exc
        for entry in entries:
            if entry.is_symlink():
                symlink_count += 1
                continue
            entry_path = Path(entry.path)
            rel = entry_path.relative_to(root)
            try:
                if entry.is_dir(follow_symlinks=False):
                    if entry.name.lower() in _EXCLUDED_DIRS:
                        continue
                    stack.append(entry_path)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
            except OSError as exc:
                raise CodeIntelligenceError("PATH_STAT_FAILED:" + rel.as_posix()) from exc
            seen += 1
            if seen > max_files:
                raise ResourceLimitError("MAX_FILES_EXCEEDED; no partial index published")
            if _is_secret_path(rel):
                secret_count += 1
                continue
            try:
                resolved = entry_path.resolve(strict=True)
                resolved.relative_to(root_resolved)
            except (OSError, ValueError) as exc:
                raise CodeIntelligenceError("PATH_CONTAINMENT_FAILED:" + rel.as_posix()) from exc
            found.append((rel, entry_path))
    found.sort(key=lambda item: item[0].as_posix())
    return found, secret_count, symlink_count, seen


def _module_name(relative: Path) -> str | None:
    if relative.suffix != ".py":
        return None
    if relative.name == "__init__.py":
        parts = relative.parent.parts
    else:
        parts = relative.with_suffix("").parts
    if not parts:
        return None
    return ".".join(parts)


def _resolve_local_module(import_name: str, module_to_path: dict[str, str]) -> str | None:
    # Exact-only resolution avoids misclassifying imported attributes/classes
    # as modules merely because their parent package exists.
    return module_to_path.get(import_name)


def _extract_imports(tree: ast.AST, current_module: str | None, is_package_init: bool) -> tuple[list[dict[str, Any]], int]:
    imports: list[dict[str, Any]] = []
    dynamic_sites = 0
    package_name = current_module if is_package_init else ((current_module or "").rpartition(".")[0])
    importlib_module_aliases: set[str] = set()
    import_module_function_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib" or alias.name.startswith("importlib."):
                    importlib_module_aliases.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module == "importlib":
            for alias in node.names:
                if alias.name == "import_module":
                    import_module_function_aliases.add(alias.asname or alias.name)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({"imported_name": alias.name, "line": node.lineno})
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                if not package_name:
                    imports.append({"imported_name": "<relative-import-unresolved>", "line": node.lineno})
                    continue
                pkg_parts = package_name.split(".")
                remove_count = max(0, node.level - 1)
                if remove_count >= len(pkg_parts):
                    imports.append({"imported_name": "<relative-import-unresolved>", "line": node.lineno})
                    continue
                prefix = pkg_parts[:len(pkg_parts) - remove_count]
                full_base = ".".join(prefix + ([base] if base else []))
            else:
                full_base = base
            if full_base:
                imports.append({"imported_name": full_base, "line": node.lineno})
            for alias in node.names:
                if alias.name == "*" or not alias.name:
                    continue
                child = ".".join(part for part in (full_base, alias.name) if part)
                if child and not any(item["imported_name"] == child for item in imports):
                    imports.append({"imported_name": child, "line": node.lineno})
        elif isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name) and (
                function.id == "__import__" or function.id in import_module_function_aliases
            ):
                dynamic_sites += 1
            elif isinstance(function, ast.Attribute) and function.attr == "import_module":
                if isinstance(function.value, ast.Name) and function.value.id in importlib_module_aliases:
                    dynamic_sites += 1
    imports.sort(key=lambda item: (item["line"], item["imported_name"]))
    return imports, dynamic_sites


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def index_repository(
    repository_root: str | os.PathLike[str],
    *,
    source_revision: str = "UNKNOWN",
    changed_paths: Iterable[str] = (),
    max_files: int = DEFAULT_MAX_FILES,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> dict[str, Any]:
    """Index Python imports without executing or modifying repository files.

    `source_revision` is caller-declared, not independently verified by this
    module. Only `.py` files are parsed. Other recognized source languages are
    counted as unsupported so impact reports cannot claim full coverage.
    """
    root = Path(repository_root).resolve(strict=True)
    if not root.is_dir():
        raise CodeIntelligenceError("REPOSITORY_ROOT_NOT_DIRECTORY")
    if not isinstance(source_revision, str) or not source_revision.strip():
        raise CodeIntelligenceError("SOURCE_REVISION_REQUIRED; use UNKNOWN if unavailable")
    for label, value in (("max_files", max_files), ("max_file_bytes", max_file_bytes), ("max_total_bytes", max_total_bytes)):
        if not isinstance(value, int) or value < 1:
            raise CodeIntelligenceError("INVALID_RESOURCE_LIMIT:" + label)

    all_files, secrets_excluded, symlinks_excluded, files_seen = _discover(root, max_files)
    source_files: list[tuple[Path, Path]] = []
    python_files: list[tuple[Path, Path]] = []
    recognized_paths: set[str] = set()
    for relative, absolute in all_files:
        if _is_source_file(relative):
            source_files.append((relative, absolute))
            recognized_paths.add(relative.as_posix())
        if relative.suffix == ".py":
            python_files.append((relative, absolute))

    records: list[dict[str, Any]] = []
    parsed_trees: dict[str, ast.AST] = {}
    module_to_path: dict[str, str] = {}
    duplicate_modules: set[str] = set()
    total_source_bytes = 0
    for relative, absolute in source_files:
        rel = relative.as_posix()
        is_python = relative.suffix == ".py"
        analysis_support = "PYTHON_AST" if is_python else "UNSUPPORTED_LANGUAGE"
        try:
            size = absolute.stat(follow_symlinks=False).st_size
        except OSError as exc:
            raise CodeIntelligenceError("FILE_STAT_FAILED:" + rel) from exc
        total_source_bytes += size
        if total_source_bytes > max_total_bytes:
            raise ResourceLimitError("MAX_TOTAL_SOURCE_BYTES_EXCEEDED; no partial index published")
        if size > max_file_bytes:
            try:
                digest = _hash_file(absolute)
            except OSError as exc:
                raise CodeIntelligenceError("FILE_READ_FAILED:" + rel) from exc
            records.append({"path": rel, "status": "SKIPPED_FILE_SIZE", "analysis_support": analysis_support,
                            "size_bytes": size, "sha256": digest})
            continue
        if not is_python:
            try:
                digest = _hash_file(absolute)
            except OSError as exc:
                raise CodeIntelligenceError("FILE_READ_FAILED:" + rel) from exc
            records.append({"path": rel, "status": "UNSUPPORTED_LANGUAGE", "analysis_support": analysis_support,
                            "size_bytes": size, "sha256": digest})
            continue
        try:
            raw = absolute.read_bytes()
        except OSError as exc:
            raise CodeIntelligenceError("FILE_READ_FAILED:" + rel) from exc
        digest = _sha256(raw)
        try:
            source = raw.decode("utf-8")
            tree = ast.parse(source, filename=rel, type_comments=True)
        except UnicodeDecodeError:
            records.append({"path": rel, "status": "PARSE_ERROR_ENCODING", "analysis_support": analysis_support,
                            "size_bytes": size, "sha256": digest})
            continue
        except SyntaxError as exc:
            records.append({"path": rel, "status": "PARSE_ERROR_SYNTAX", "analysis_support": analysis_support,
                            "size_bytes": size, "sha256": digest, "error_line": exc.lineno})
            continue
        module = _module_name(relative)
        records.append({"path": rel, "status": "PARSED", "analysis_support": analysis_support,
                        "size_bytes": size, "sha256": digest, "module": module})
        parsed_trees[rel] = tree
        if module and module not in duplicate_modules:
            # Duplicate module names are not silently chosen.
            if module in module_to_path and module_to_path[module] != rel:
                module_to_path.pop(module, None)
                duplicate_modules.add(module)
            else:
                module_to_path[module] = rel

    # Fail closed for every regular non-secret file not covered by the explicit
    # source/config allowlist. Unknown extensions can still contain source code;
    # never claim whole-repository source coverage while silently omitting them.
    unclassified_count = 0
    for relative, absolute in all_files:
        rel = relative.as_posix()
        if rel in recognized_paths:
            continue
        unclassified_count += 1
        try:
            size = absolute.stat(follow_symlinks=False).st_size
        except OSError as exc:
            raise CodeIntelligenceError("FILE_STAT_FAILED:" + rel) from exc
        total_source_bytes += size
        if total_source_bytes > max_total_bytes:
            raise ResourceLimitError("MAX_TOTAL_SOURCE_BYTES_EXCEEDED; no partial index published")
        record = {"path": rel, "status": "UNCLASSIFIED_FILE_TYPE", "analysis_support": "UNCLASSIFIED_FILE_TYPE",
                  "size_bytes": size}
        if size <= max_file_bytes:
            try:
                record["sha256"] = _hash_file(absolute)
            except OSError as exc:
                raise CodeIntelligenceError("FILE_READ_FAILED:" + rel) from exc
        else:
            record["status"] = "UNCLASSIFIED_FILE_TYPE_SIZE_LIMIT"
        records.append(record)

    module_by_path = {rec["path"]: rec.get("module") for rec in records if rec["status"] == "PARSED"}
    edges: list[dict[str, Any]] = []
    dynamic_import_sites = 0
    for relative, _absolute in python_files:
        rel = relative.as_posix()
        tree = parsed_trees.get(rel)
        if tree is None:
            continue
        module = module_by_path.get(rel)
        imports, dynamic_count = _extract_imports(tree, module, relative.name == "__init__.py")
        dynamic_import_sites += dynamic_count
        for item in imports:
            imported = item["imported_name"]
            if imported.startswith("<relative-import-unresolved>"):
                target = None
            elif imported.split(".", 1)[0] in getattr(sys, "stdlib_module_names", set()):
                target = None
                # Standard-library imports are external to this repository graph.
                continue
            else:
                target = _resolve_local_module(imported, module_to_path)
            edges.append({
                "source_path": rel,
                "target_path": target,
                "imported_name": imported,
                "line": item["line"],
                "evidence_status": "INFERRED_LOCAL_MODULE" if target else "UNRESOLVED_OR_EXTERNAL",
            })
    edges.sort(key=lambda edge: (edge["source_path"], edge["line"], edge["imported_name"], edge["target_path"] or ""))

    parsed_count = sum(rec["status"] == "PARSED" for rec in records)
    syntax_error_count = sum(rec["status"] in {"PARSE_ERROR_SYNTAX", "PARSE_ERROR_ENCODING"} for rec in records)
    too_large_count = sum(rec["status"] == "SKIPPED_FILE_SIZE" and rec.get("analysis_support") == "PYTHON_AST" for rec in records)
    source_too_large_count = sum(rec["status"] == "SKIPPED_FILE_SIZE" for rec in records)
    unsupported_count = sum(rec.get("analysis_support") == "UNSUPPORTED_LANGUAGE" for rec in records)
    coverage_incomplete = bool(syntax_error_count or too_large_count or unsupported_count or source_too_large_count or unclassified_count or dynamic_import_sites or secrets_excluded or symlinks_excluded)
    source_records = [{"path": r["path"], "status": r["status"], "analysis_support": r.get("analysis_support"),
                       "size_bytes": r["size_bytes"], "sha256": r.get("sha256")}
                      for r in records]
    snapshot_material = {
        "schema": SCHEMA,
        "analyzer_version": ANALYZER_VERSION,
        "source_revision": source_revision.strip(),
        "files": sorted(source_records, key=lambda r: r["path"]),
    }
    snapshot_sha = _sha256(_canonical_bytes(snapshot_material))

    changed = sorted({_normal_relative_path(path) for path in changed_paths})
    valid_paths = {record["path"] for record in records}
    missing_changes = sorted(set(changed) - valid_paths)
    reverse_edges: dict[str, set[str]] = {}
    for edge in edges:
        target = edge["target_path"]
        if target:
            reverse_edges.setdefault(target, set()).add(edge["source_path"])
    impacted: set[str] = set()
    queue = list(changed)
    visited = set(changed)
    while queue:
        current = queue.pop(0)
        for parent in sorted(reverse_edges.get(current, set())):
            if parent not in visited:
                visited.add(parent)
                impacted.add(parent)
                queue.append(parent)
    impact_status = "NOT_REQUESTED"
    if changed:
        if missing_changes:
            impact_status = "UNRESOLVED_CHANGED_PATH"
        elif coverage_incomplete:
            impact_status = "KNOWN_DEPENDENTS_ONLY_INCOMPLETE_COVERAGE"
        else:
            impact_status = "KNOWN_LOCAL_PYTHON_DEPENDENTS"

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "analyzer_version": ANALYZER_VERSION,
        "source": {
            "repository_label": root.name,
            "source_revision": source_revision.strip(),
            "source_revision_status": "CALLER_DECLARED_NOT_VERIFIED",
            "root_path_disclosed": False,
        },
        "limits": {"max_files": max_files, "max_file_bytes": max_file_bytes, "max_total_bytes": max_total_bytes},
        "snapshot_sha256": snapshot_sha,
        "coverage": {
            "files_seen": files_seen,
            "secret_files_excluded_count": secrets_excluded,
            "symlink_entries_excluded_count": symlinks_excluded,
            "source_files_recognized": len(source_files),
            "python_files_total": len(python_files),
            "python_files_parsed": parsed_count,
            "python_files_parse_failed": syntax_error_count,
            "python_files_skipped_file_size": too_large_count,
            "source_files_skipped_file_size": source_too_large_count,
            "unsupported_source_files": unsupported_count,
            "unclassified_files_count": unclassified_count,
            "dynamic_import_sites": dynamic_import_sites,
            "parsed_python_ratio": _ratio(parsed_count, len(python_files)),
            "coverage_complete_for_all_repository_source": not coverage_incomplete,
            "limitations": [
                "Python AST import analysis only; no execution, call graph, data flow, or runtime behavior proof.",
                "Recognized non-Python source files are counted as unsupported and make impact analysis incomplete.",
                "Regular non-secret files with unrecognized names/extensions are listed as UNCLASSIFIED_FILE_TYPE and make coverage incomplete.",
                "Excluded secret-shaped files and skipped symlinks also make coverage incomplete because their contents are not analyzed.",
                "Dynamic import sites make impact analysis incomplete; source aliases/reflection may remain unresolved.",
                "Hash integrity and a caller-declared revision do not establish source authenticity or correctness.",
            ],
        },
        "files": sorted(records, key=lambda record: record["path"]),
        "edges": edges,
        "impact": {
            "changed_paths": changed,
            "missing_or_unparsed_changed_paths": missing_changes,
            "known_impacted_dependents": sorted(impacted),
            "status": impact_status,
        },
    }
    report["report_sha256"] = _sha256(_canonical_bytes(report))
    return report


def compare_staleness(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Compare two report identities; does not silently bless an old index."""
    if previous.get("schema") != SCHEMA or current.get("schema") != SCHEMA:
        raise CodeIntelligenceError("INDEX_SCHEMA_MISMATCH")
    old_source = previous.get("source", {})
    new_source = current.get("source", {})
    reasons: list[str] = []
    if old_source.get("source_revision") != new_source.get("source_revision"):
        reasons.append("SOURCE_REVISION_CHANGED")
    if previous.get("snapshot_sha256") != current.get("snapshot_sha256"):
        reasons.append("SOURCE_SNAPSHOT_CHANGED")
    if previous.get("analyzer_version") != current.get("analyzer_version"):
        reasons.append("ANALYZER_VERSION_CHANGED")
    return {"status": "STALE" if reasons else "CURRENT_BY_DECLARED_IDENTITIES", "reasons": reasons}


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Build a bounded, read-only HG Python import graph.")
    parser.add_argument("--repo", required=True, help="Repository root to read; repository code is never executed.")
    parser.add_argument("--revision", default="UNKNOWN", help="Caller-declared immutable source revision; not verified by this tool.")
    parser.add_argument("--changed", action="append", default=[], help="Repository-relative changed path; repeatable.")
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    parser.add_argument("--max-file-bytes", type=int, default=DEFAULT_MAX_FILE_BYTES)
    parser.add_argument("--max-total-bytes", type=int, default=DEFAULT_MAX_TOTAL_BYTES)
    parser.add_argument("--output", help="Optional JSON output path; keep it outside the analyzed repository.")
    args = parser.parse_args()
    try:
        report = index_repository(args.repo, source_revision=args.revision, changed_paths=args.changed,
                                  max_files=args.max_files, max_file_bytes=args.max_file_bytes,
                                  max_total_bytes=args.max_total_bytes)
    except (OSError, CodeIntelligenceError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "BLOCKED", "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    payload = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output_path = Path(args.output).resolve()
        root = Path(args.repo).resolve()
        try:
            output_path.relative_to(root)
        except ValueError:
            pass
        else:
            print("BLOCKED: output must be outside the repository root", file=sys.stderr)
            return 2
        output_path.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
