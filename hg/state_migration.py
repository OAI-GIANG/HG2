"""Fail-closed envelope for preserving legacy state bytes before any migration.

This module records source identity and integrity metadata only. It does not
attest legacy authority, authorize production import, or mutate either store.
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

SCHEMA_VERSION = "HG_STATE_MIGRATION_ENVELOPE_V1"
LEGACY_AUTHORITY_UNATTESTED = "LEGACY_AUTHORITY_UNATTESTED"
_REQUIRED = {
    "schema_version", "source_log_base64", "source_runtime_id",
    "source_head_digest", "source_state_sha256", "source_head_sha256",
    "source_runtime_id_sha256", "source_log_sha256", "event_count",
    "legacy_authority", "production_import_authorized",
}
_DIGEST_FIELDS = (
    "source_head_digest", "source_state_sha256", "source_head_sha256",
    "source_runtime_id_sha256", "source_log_sha256",
)


class MigrationEnvelopeError(ValueError):
    """Invalid or tampered migration envelope; import must remain disabled."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise MigrationEnvelopeError("ENVELOPE_NOT_CANONICAL_JSON") from exc


def canonical_envelope_bytes(envelope: dict[str, Any]) -> bytes:
    if type(envelope) is not dict:
        raise MigrationEnvelopeError("ENVELOPE_SCHEMA_INVALID")
    return _canonical(envelope)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _validate_jsonl(source_log: bytes) -> int:
    if not source_log or not source_log.endswith(b"\n"):
        raise MigrationEnvelopeError("SOURCE_EVENT_JSON_INVALID")
    count = 0
    for line in source_log.splitlines():
        if not line.strip():
            raise MigrationEnvelopeError("SOURCE_EVENT_JSON_INVALID")
        try:
            event = json.loads(line.decode("utf-8", errors="strict"),
                               object_pairs_hook=_reject_duplicate_keys,
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise MigrationEnvelopeError("SOURCE_EVENT_JSON_INVALID") from exc
        if type(event) is not dict:
            raise MigrationEnvelopeError("SOURCE_EVENT_JSON_INVALID")
        count += 1
    if count == 0:
        raise MigrationEnvelopeError("SOURCE_EVENT_JSON_INVALID")
    return count


def build_envelope(*, source_log: bytes, source_runtime_id: str,
                   source_head_digest: str, source_state_sha256: str,
                   source_head_sha256: str, source_runtime_id_sha256: str) -> dict[str, Any]:
    if not isinstance(source_log, bytes):
        raise MigrationEnvelopeError("SOURCE_EVENT_LOG_MUST_BE_BYTES")
    event_count = _validate_jsonl(source_log)
    if not isinstance(source_runtime_id, str) or not source_runtime_id.strip():
        raise MigrationEnvelopeError("SOURCE_RUNTIME_ID_INVALID")
    values = {
        "source_head_digest": source_head_digest,
        "source_state_sha256": source_state_sha256,
        "source_head_sha256": source_head_sha256,
        "source_runtime_id_sha256": source_runtime_id_sha256,
        "source_log_sha256": _sha256(source_log),
    }
    for field, value in values.items():
        if (not isinstance(value, str) or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)):
            raise MigrationEnvelopeError("SOURCE_DIGEST_INVALID:" + field)
    return {
        "schema_version": SCHEMA_VERSION,
        "source_log_base64": base64.b64encode(source_log).decode("ascii"),
        "source_runtime_id": source_runtime_id,
        **values,
        "event_count": event_count,
        "legacy_authority": LEGACY_AUTHORITY_UNATTESTED,
        "production_import_authorized": False,
    }


def validate_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    if type(envelope) is not dict or set(envelope) != _REQUIRED:
        raise MigrationEnvelopeError("ENVELOPE_SCHEMA_INVALID")
    if envelope.get("schema_version") != SCHEMA_VERSION:
        raise MigrationEnvelopeError("ENVELOPE_SCHEMA_VERSION_INVALID")
    if envelope.get("legacy_authority") != LEGACY_AUTHORITY_UNATTESTED:
        raise MigrationEnvelopeError("LEGACY_AUTHORITY_MUST_REMAIN_UNATTESTED")
    if envelope.get("production_import_authorized") is not False:
        raise MigrationEnvelopeError("PRODUCTION_IMPORT_MUST_REMAIN_DISABLED")
    encoded = envelope.get("source_log_base64")
    if not isinstance(encoded, str):
        raise MigrationEnvelopeError("SOURCE_LOG_ENCODING_INVALID")
    try:
        source_log = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise MigrationEnvelopeError("SOURCE_LOG_ENCODING_INVALID") from exc
    count = _validate_jsonl(source_log)
    if envelope.get("source_log_sha256") != _sha256(source_log):
        raise MigrationEnvelopeError("SOURCE_METADATA_MISMATCH")
    if envelope.get("event_count") != count or isinstance(envelope.get("event_count"), bool):
        raise MigrationEnvelopeError("SOURCE_METADATA_MISMATCH")
    if not isinstance(envelope.get("source_runtime_id"), str) or not envelope["source_runtime_id"].strip():
        raise MigrationEnvelopeError("SOURCE_METADATA_MISMATCH")
    for field in _DIGEST_FIELDS:
        value = envelope.get(field)
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise MigrationEnvelopeError("SOURCE_METADATA_MISMATCH")
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "event_count": count,
        "source_log_sha256": _sha256(source_log),
        "legacy_authority": LEGACY_AUTHORITY_UNATTESTED,
        "production_import_authorized": False,
        "migration_performed": False,
    }


# V2 carries the exact bytes of every durable legacy state file. V1 remains
# readable for compatibility but only embeds history.jsonl; V1 alone is not a
# complete state backup and must not be used to claim lossless migration.
STATE_MIGRATION_SCHEMA_V2 = "HG_STATE_MIGRATION_ENVELOPE_V2"
STATE_FILES_V2 = ("history.jsonl", "head.json", "state.json", "runtime_id")


def _strict_json_object(raw: bytes, *, code: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise MigrationEnvelopeError(code) from exc
    if type(value) is not dict:
        raise MigrationEnvelopeError(code)
    return value


def build_envelope_v2(*, source_files: dict[str, bytes],
                      source_runtime_id: str,
                      source_head_digest: str) -> dict[str, Any]:
    """Package exact bytes for all durable legacy state files; never authorizes import."""
    if type(source_files) is not dict or set(source_files) != set(STATE_FILES_V2):
        raise MigrationEnvelopeError("V2_SOURCE_FILE_SET_INVALID")
    if not isinstance(source_runtime_id, str) or not source_runtime_id.strip():
        raise MigrationEnvelopeError("SOURCE_RUNTIME_ID_INVALID")
    if (not isinstance(source_head_digest, str) or len(source_head_digest) != 64
            or any(char not in "0123456789abcdef" for char in source_head_digest)):
        raise MigrationEnvelopeError("SOURCE_DIGEST_INVALID:source_head_digest")

    files: dict[str, dict[str, Any]] = {}
    for name in STATE_FILES_V2:
        raw = source_files[name]
        if not isinstance(raw, bytes) or not raw:
            raise MigrationEnvelopeError("V2_SOURCE_FILE_INVALID:" + name)
        if name == "history.jsonl":
            event_count = _validate_jsonl(raw)
        elif name in {"head.json", "state.json"}:
            _strict_json_object(raw, code="V2_SOURCE_JSON_INVALID:" + name)
        else:
            try:
                decoded_runtime_id = raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise MigrationEnvelopeError("V2_RUNTIME_ID_INVALID") from exc
            if not decoded_runtime_id.strip() or decoded_runtime_id.strip() != source_runtime_id:
                raise MigrationEnvelopeError("V2_RUNTIME_ID_MISMATCH")
        files[name] = {
            "base64": base64.b64encode(raw).decode("ascii"),
            "sha256": _sha256(raw),
            "size_bytes": len(raw),
        }
    return {
        "schema_version": STATE_MIGRATION_SCHEMA_V2,
        "source_runtime_id": source_runtime_id,
        "source_head_digest": source_head_digest,
        "source_files": files,
        "event_count": event_count,
        "legacy_authority": LEGACY_AUTHORITY_UNATTESTED,
        "production_import_authorized": False,
        "migration_performed": False,
    }


def validate_envelope_v2(envelope: dict[str, Any]) -> dict[str, Any]:
    """Validate exact file-byte preservation and metadata; authenticity remains unproven."""
    required = {
        "schema_version", "source_runtime_id", "source_head_digest",
        "source_files", "event_count", "legacy_authority",
        "production_import_authorized", "migration_performed",
    }
    if type(envelope) is not dict or set(envelope) != required:
        raise MigrationEnvelopeError("V2_ENVELOPE_SCHEMA_INVALID")
    if envelope.get("schema_version") != STATE_MIGRATION_SCHEMA_V2:
        raise MigrationEnvelopeError("V2_SCHEMA_VERSION_INVALID")
    if envelope.get("legacy_authority") != LEGACY_AUTHORITY_UNATTESTED:
        raise MigrationEnvelopeError("LEGACY_AUTHORITY_MUST_REMAIN_UNATTESTED")
    if envelope.get("production_import_authorized") is not False:
        raise MigrationEnvelopeError("PRODUCTION_IMPORT_MUST_REMAIN_DISABLED")
    if envelope.get("migration_performed") is not False:
        raise MigrationEnvelopeError("MIGRATION_MUST_REMAIN_NOT_PERFORMED")
    if type(envelope.get("event_count")) is not int:
        raise MigrationEnvelopeError("V2_EVENT_COUNT_INVALID")
    source_files = envelope.get("source_files")
    if type(source_files) is not dict or set(source_files) != set(STATE_FILES_V2):
        raise MigrationEnvelopeError("V2_SOURCE_FILE_SET_INVALID")
    decoded: dict[str, bytes] = {}
    for name in STATE_FILES_V2:
        record = source_files[name]
        if type(record) is not dict or set(record) != {"base64", "sha256", "size_bytes"}:
            raise MigrationEnvelopeError("V2_SOURCE_FILE_METADATA_INVALID:" + name)
        encoded = record.get("base64")
        if not isinstance(encoded, str):
            raise MigrationEnvelopeError("V2_SOURCE_FILE_ENCODING_INVALID:" + name)
        try:
            raw = base64.b64decode(encoded.encode("ascii"), validate=True)
        except (ValueError, UnicodeEncodeError) as exc:
            raise MigrationEnvelopeError("V2_SOURCE_FILE_ENCODING_INVALID:" + name) from exc
        if record.get("sha256") != _sha256(raw):
            raise MigrationEnvelopeError("V2_SOURCE_FILE_DIGEST_MISMATCH:" + name)
        if type(record.get("size_bytes")) is not int or record["size_bytes"] != len(raw):
            raise MigrationEnvelopeError("V2_SOURCE_FILE_SIZE_MISMATCH:" + name)
        decoded[name] = raw
    rebuilt = build_envelope_v2(
        source_files=decoded,
        source_runtime_id=envelope.get("source_runtime_id"),
        source_head_digest=envelope.get("source_head_digest"),
    )
    if rebuilt != envelope:
        raise MigrationEnvelopeError("V2_SOURCE_METADATA_MISMATCH")
    return {
        "ok": True,
        "schema_version": STATE_MIGRATION_SCHEMA_V2,
        "event_count": rebuilt["event_count"],
        "source_file_count": len(decoded),
        "source_file_sha256": {
            name: source_files[name]["sha256"] for name in STATE_FILES_V2
        },
        "legacy_authority": LEGACY_AUTHORITY_UNATTESTED,
        "production_import_authorized": False,
        "migration_performed": False,
        "semantic_truth_verified": False,
    }
