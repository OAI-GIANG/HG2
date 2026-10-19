"""Safe manifest loading and SHA-256 verification; never downloads artifacts."""
import hashlib
import json
import re
from pathlib import Path

_SHA256 = re.compile(r"^[0-9a-f]{64}$")

class ManifestError(ValueError):
    pass

def load_manifest(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestError("manifest cannot be read as valid JSON") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ManifestError("unsupported manifest schema")
    engines = data.get("engines")
    if not isinstance(engines, list):
        raise ManifestError("engines must be a list")
    seen = set()
    for item in engines:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip():
            raise ManifestError("each engine requires a non-empty id")
        if item["id"] in seen:
            raise ManifestError("duplicate engine id")
        seen.add(item["id"])
        digest = item.get("sha256")
        if digest is not None and (not isinstance(digest, str) or not _SHA256.fullmatch(digest)):
            raise ManifestError("sha256 must be 64 lowercase hexadecimal characters")
        if item.get("processing") not in {"LOCAL", "DEVICE_SYSTEM_OR_UNKNOWN", "REMOTE"}:
            raise ManifestError("unknown processing boundary")
    return data

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def verify_artifact(path: Path, expected_sha256: str) -> bool:
    if not _SHA256.fullmatch(expected_sha256 or ""):
        raise ManifestError("invalid expected sha256")
    return path.is_file() and sha256_file(path) == expected_sha256
