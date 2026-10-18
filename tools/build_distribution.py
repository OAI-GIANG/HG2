#!/usr/bin/env python3
"""Build a minimal HG2 source distribution from the manifest module allowlist.

The repository checkout is a development/test tree, not the shipped package.
The output archive contains the root manifest, README, and only modules explicitly
listed in manifest.json. Output must be outside the repository and must not exist.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LEGACY_V1 = "hg.creative_assimilation"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


class DistributionError(Exception):
    pass


def _outside_repo(output: Path) -> Path:
    resolved = output.expanduser().resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return resolved
    raise DistributionError("output must be outside repository checkout")


def distribution_files(root: Path = ROOT) -> tuple[dict, list[tuple[str, Path]]]:
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    modules = manifest.get("modules")
    optional_modules = manifest.get("optional_modules", [])
    if not isinstance(modules, list) or not modules or any(not isinstance(x, str) for x in modules):
        raise DistributionError("manifest modules must be a non-empty string list")
    if not isinstance(optional_modules, list) or any(not isinstance(x, str) for x in optional_modules):
        raise DistributionError("manifest optional_modules must be a string list")
    allowed_modules = modules + optional_modules
    if len(set(allowed_modules)) != len(allowed_modules):
        raise DistributionError("duplicate module in manifest allowlists")
    if LEGACY_V1 in allowed_modules:
        raise DistributionError("legacy V1 module must not be in distribution allowlist")

    files: dict[str, Path] = {"manifest.json": manifest_path, "README.md": root / "README.md"}
    for module in allowed_modules:
        parts = module.split(".")
        if not parts or any(not p.isidentifier() for p in parts):
            raise DistributionError("invalid module path in manifest")
        source = root.joinpath(*parts).with_suffix(".py")
        try:
            source.resolve(strict=True).relative_to(root.resolve(strict=True))
        except (OSError, ValueError) as exc:
            raise DistributionError("manifest module missing or outside repository: " + module) from exc
        files[PurePosixPath(*parts).with_suffix(".py").as_posix()] = source
        # Include package initializers needed for nested allowlisted modules.
        for index in range(1, len(parts)):
            init_parts = parts[:index] + ["__init__"]
            init_source = root.joinpath(*init_parts).with_suffix(".py")
            if not init_source.is_file():
                raise DistributionError("package initializer missing: " + ".".join(parts[:index]))
            files[PurePosixPath(*init_parts).with_suffix(".py").as_posix()] = init_source
    if "hg/__init__.py" not in files:
        init = root / "hg" / "__init__.py"
        if not init.is_file():
            raise DistributionError("hg package initializer missing")
        files["hg/__init__.py"] = init
    return manifest, sorted(files.items())


def build_archive(output: Path, root: Path = ROOT) -> dict:
    output = _outside_repo(output)
    if output.exists():
        raise DistributionError("output already exists; overwrite is forbidden")
    manifest, files = distribution_files(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for archive_name, source in files:
                info = zipfile.ZipInfo(archive_name, date_time=FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, source.read_bytes())
        with zipfile.ZipFile(output, "r") as archive:
            names = set(archive.namelist())
            expected = {name for name, _ in files}
            if names != expected:
                raise DistributionError("archive inventory mismatch")
            if "hg/creative_assimilation.py" in names:
                raise DistributionError("legacy V1 module unexpectedly included")
            packaged_manifest = json.loads(archive.read("manifest.json"))
            for module in packaged_manifest["modules"] + packaged_manifest.get("optional_modules", []):
                if module.replace(".", "/") + ".py" not in names:
                    raise DistributionError("manifest module absent from archive: " + module)
        return {
            "status": "PASS",
            "artifact": str(output),
            "artifact_sha256": __import__("hashlib").sha256(output.read_bytes()).hexdigest(),
            "files": sorted(expected),
            "module_count": len(manifest["modules"]) + len(manifest.get("optional_modules", [])),
            "legacy_v1_excluded": True,
        }
    except Exception:
        output.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="new ZIP path outside repository")
    args = parser.parse_args()
    try:
        result = build_archive(Path(args.output))
    except (DistributionError, OSError, UnicodeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
