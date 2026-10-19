"""Versioned command/event contract primitives for HG2's circulatory architecture.

This module is deliberately dependency-light and does not perform I/O.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
import uuid
from typing import Any, Mapping

SCHEMA_VERSION = "HG_EVENT_V1"
ZERO_DIGEST = "0" * 64
MAX_CANONICAL_BYTES = 1_048_576
MAX_DEPTH = 64
MAX_NODES = 20_000
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_EVENT_TYPE_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_SENSITIVE_KEY_FRAGMENTS = (
    "password", "passwd", "secret", "credential", "token", "apikey", "privatekey",
    "bearertoken", "modelkey",
)


class ContractError(ValueError):
    """Raised when an envelope violates its versioned contract."""


def _validate_json_value(value: Any, *, depth: int = 0, budget: list[int] | None = None) -> None:
    if budget is None:
        budget = [MAX_NODES]
    budget[0] -= 1
    if budget[0] < 0:
        raise ContractError("JSON_NODE_LIMIT_EXCEEDED")
    if depth > MAX_DEPTH:
        raise ContractError("JSON_DEPTH_LIMIT_EXCEEDED")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError("NON_FINITE_NUMBER")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item, depth=depth + 1, budget=budget)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractError("OBJECT_KEYS_MUST_BE_STRINGS")
            _validate_json_value(item, depth=depth + 1, budget=budget)
        return
    raise ContractError("UNSUPPORTED_JSON_VALUE_TYPE")


def canonical_json(value: Any, *, max_bytes: int = MAX_CANONICAL_BYTES) -> str:
    """Return deterministic JSON with an explicit byte limit.

    The default remains the strict 1 MiB runtime limit. Read-only developer
    reports may request a larger bound matching their own repository scan cap.
    """
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise ContractError("INVALID_CANONICAL_BYTE_LIMIT")
    _validate_json_value(value)
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise ContractError("CANONICALIZATION_FAILED") from exc
    if len(encoded.encode("utf-8")) > max_bytes:
        raise ContractError("CANONICAL_PAYLOAD_TOO_LARGE")
    return encoded


def canonical_digest(value: Any, *, max_bytes: int = MAX_CANONICAL_BYTES) -> str:
    return hashlib.sha256(canonical_json(value, max_bytes=max_bytes).encode("utf-8")).hexdigest()


def parse_json_no_duplicate_keys(raw: str) -> Any:
    """Parse JSON while rejecting duplicate object keys and non-standard constants."""
    if not isinstance(raw, str):
        raise ContractError("INVALID_JSON")
    try:
        raw_size = len(raw.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ContractError("INVALID_JSON_ENCODING") from exc
    if raw_size > MAX_CANONICAL_BYTES:
        raise ContractError("CANONICAL_PAYLOAD_TOO_LARGE")
    def pairs_to_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ContractError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    def reject_constant(_value):
        raise ContractError("NON_STANDARD_JSON_CONSTANT")

    try:
        value = json.loads(raw, object_pairs_hook=pairs_to_object, parse_constant=reject_constant)
    except ContractError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError, RecursionError) as exc:
        raise ContractError("INVALID_JSON") from exc
    _validate_json_value(value)
    return value


def _contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = "".join(ch.lower() for ch in key if ch.isalnum())
            if any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS):
                return True
            if _contains_sensitive_key(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def _require_text(value: Any, field: str, *, max_length: int = 256) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(field.upper() + "_REQUIRED")
    if len(value) > max_length:
        raise ContractError(field.upper() + "_TOO_LONG")


def validate_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Validate exact HG_EVENT_V1 structure and its content digest."""
    if not isinstance(event, Mapping):
        raise ContractError("EVENT_MUST_BE_OBJECT")
    required = {
        "schema_version", "event_id", "event_type", "sequence", "recorded_at",
        "actor_id", "authority_context", "correlation_id", "causation_id",
        "idempotency_key", "runtime_id", "state_owner_id", "payload",
        "previous_digest", "record_digest", "evidence_refs",
    }
    if set(event) != required:
        if required - set(event):
            raise ContractError("MISSING_EVENT_FIELDS")
        raise ContractError("UNKNOWN_EVENT_FIELDS")
    result = dict(event)
    _validate_json_value(result)
    if result["schema_version"] != SCHEMA_VERSION:
        raise ContractError("UNSUPPORTED_SCHEMA_VERSION")
    for field in ("event_id", "actor_id", "correlation_id", "runtime_id", "state_owner_id"):
        _require_text(result[field], field)
    event_type = result["event_type"]
    if not isinstance(event_type, str) or not _EVENT_TYPE_RE.fullmatch(event_type):
        raise ContractError("INVALID_EVENT_TYPE")
    sequence = result["sequence"]
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise ContractError("INVALID_SEQUENCE")
    recorded_at = result["recorded_at"]
    if isinstance(recorded_at, bool) or not isinstance(recorded_at, (int, float)) or not math.isfinite(recorded_at):
        raise ContractError("INVALID_RECORDED_AT")
    for field in ("causation_id", "idempotency_key"):
        value = result[field]
        if value is not None:
            _require_text(value, field)
    if not isinstance(result["authority_context"], dict):
        raise ContractError("AUTHORITY_CONTEXT_MUST_BE_OBJECT")
    if not isinstance(result["payload"], dict):
        raise ContractError("PAYLOAD_MUST_BE_OBJECT")
    if _contains_sensitive_key(result["authority_context"]) or _contains_sensitive_key(result["payload"]):
        raise ContractError("SENSITIVE_FIELD_NAME_FORBIDDEN")
    for field in ("previous_digest", "record_digest"):
        value = result[field]
        if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
            raise ContractError(field.upper() + "_INVALID")
    refs = result["evidence_refs"]
    if not isinstance(refs, list) or len(refs) > 256:
        raise ContractError("INVALID_EVIDENCE_REFS")
    for ref in refs:
        _require_text(ref, "evidence_ref", max_length=1024)
    core = {key: value for key, value in result.items() if key != "record_digest"}
    if canonical_digest(core) != result["record_digest"]:
        raise ContractError("RECORD_DIGEST_MISMATCH")
    return result


BRAIN_REQUEST_V1 = "HG_BRAIN_REQUEST_V1"
BRAIN_REQUEST_AUDIT_V1 = "HG_BRAIN_REQUEST_AUDIT_V1"
BRAIN_WORKER_CONTEXT_V1 = "HG_BRAIN_WORKER_CONTEXT_V1"
CAPABILITY_RESULT_V1 = "HG_CAPABILITY_RESULT_V1"
_RESULT_STATUSES = frozenset({"SUCCESS", "FAIL", "BLOCKED", "PARTIAL", "NOT_RUN", "RESPONSE_ONLY"})


def validate_brain_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the shared, bounded input envelope accepted by the sole Brain facade."""
    if not isinstance(request, Mapping):
        raise ContractError("BRAIN_REQUEST_MUST_BE_OBJECT")
    required = {"schema_version", "request_id", "correlation_id", "goal", "constraints", "source_revision"}
    if set(request) != required:
        raise ContractError("BRAIN_REQUEST_SCHEMA_INVALID")
    result = dict(request)
    if result["schema_version"] != BRAIN_REQUEST_V1:
        raise ContractError("UNSUPPORTED_BRAIN_REQUEST_VERSION")
    for field in ("request_id", "correlation_id", "goal", "source_revision"):
        _require_text(result[field], field, max_length=16_000 if field == "goal" else 256)
    if not isinstance(result["constraints"], dict):
        raise ContractError("BRAIN_REQUEST_CONSTRAINTS_INVALID")
    canonical_json(result, max_bytes=64 * 1024)
    return result


def validate_brain_request_audit(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the redacted durable receipt for a Brain request without storing prompt text."""
    if not isinstance(record, Mapping):
        raise ContractError("BRAIN_REQUEST_AUDIT_MUST_BE_OBJECT")
    required = {
        "schema_version", "request_id", "correlation_id", "goal_sha256",
        "constraints_sha256", "source_revision", "status",
    }
    if set(record) != required:
        raise ContractError("BRAIN_REQUEST_AUDIT_SCHEMA_INVALID")
    value = dict(record)
    if value["schema_version"] != BRAIN_REQUEST_AUDIT_V1:
        raise ContractError("UNSUPPORTED_BRAIN_REQUEST_AUDIT_VERSION")
    for field in ("request_id", "correlation_id", "source_revision"):
        _require_text(value[field], field)
    for field in ("goal_sha256", "constraints_sha256"):
        if not isinstance(value[field], str) or not _DIGEST_RE.fullmatch(value[field]):
            raise ContractError("BRAIN_REQUEST_AUDIT_DIGEST_INVALID")
    if value["status"] != "ACCEPTED":
        raise ContractError("BRAIN_REQUEST_AUDIT_STATUS_INVALID")
    canonical_json(value, max_bytes=16 * 1024)
    return value


def validate_capability_result(
    result: Mapping[str, Any], *, expected_request_id: str | None = None,
    expected_correlation_id: str | None = None, expected_source_revision: str | None = None,
    evidence_verifier=None,
) -> dict[str, Any]:
    """Validate a versioned result; SUCCESS additionally requires a trusted evidence verifier.

    A well-formed URI/hash string proves only shape. It is not proof that the referenced
    artifact exists, matches the claimed digest, or came from an accepted source.
    """
    if not isinstance(result, Mapping):
        raise ContractError("CAPABILITY_RESULT_MUST_BE_OBJECT")
    required = {
        "schema_version", "request_id", "correlation_id", "status", "output_digest",
        "error_code", "evidence_refs", "source_revision",
    }
    if set(result) != required:
        raise ContractError("CAPABILITY_RESULT_SCHEMA_INVALID")
    value = dict(result)
    if value["schema_version"] != CAPABILITY_RESULT_V1:
        raise ContractError("UNSUPPORTED_CAPABILITY_RESULT_VERSION")
    for field in ("request_id", "correlation_id", "source_revision"):
        _require_text(value[field], field)
    if expected_request_id is not None and value["request_id"] != expected_request_id:
        raise ContractError("CAPABILITY_RESULT_REQUEST_ID_MISMATCH")
    if expected_correlation_id is not None and value["correlation_id"] != expected_correlation_id:
        raise ContractError("CAPABILITY_RESULT_CORRELATION_ID_MISMATCH")
    if expected_source_revision is not None and value["source_revision"] != expected_source_revision:
        raise ContractError("CAPABILITY_RESULT_SOURCE_REVISION_MISMATCH")
    if not isinstance(value["status"], str) or value["status"] not in _RESULT_STATUSES:
        raise ContractError("CAPABILITY_RESULT_STATUS_INVALID")
    digest = value["output_digest"]
    if digest is not None and (not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest)):
        raise ContractError("CAPABILITY_RESULT_DIGEST_INVALID")
    error_code = value["error_code"]
    if error_code is not None and (not isinstance(error_code, str) or not error_code.strip() or len(error_code) > 256):
        raise ContractError("CAPABILITY_RESULT_ERROR_CODE_INVALID")
    refs = value["evidence_refs"]
    if not isinstance(refs, list) or len(refs) > 256 or any(not isinstance(ref, str) or not ref.strip() for ref in refs):
        raise ContractError("CAPABILITY_RESULT_EVIDENCE_INVALID")
    if value["status"] == "SUCCESS" and (digest is None or not refs or error_code is not None):
        raise ContractError("CAPABILITY_SUCCESS_PROVENANCE_REQUIRED")
    if value["status"] == "RESPONSE_ONLY" and (
        digest is None or refs or error_code != "PROVIDER_RESPONSE_ONLY_NOT_EXECUTION_PROOF"
    ):
        raise ContractError("CAPABILITY_RESPONSE_ONLY_CONTRACT_INVALID")
    if value["status"] == "SUCCESS" and not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value["source_revision"]):
        raise ContractError("CAPABILITY_SUCCESS_SOURCE_REVISION_UNATTESTED")
    if value["status"] == "SUCCESS" and any(
        not re.fullmatch(r"(?:test-artifact:sha256:|evidence:sha256:)[0-9a-f]{64}", ref)
        for ref in refs
    ):
        raise ContractError("CAPABILITY_SUCCESS_EVIDENCE_REFERENCE_INVALID")
    if value["status"] == "SUCCESS" and any(ref.startswith("test-artifact:") for ref in refs):
        raise ContractError("CAPABILITY_SUCCESS_TEST_ARTIFACT_NOT_RUNTIME_PROOF")
    if value["status"] == "SUCCESS":
        if not callable(evidence_verifier):
            raise ContractError("CAPABILITY_EVIDENCE_VERIFIER_REQUIRED")
        try:
            verified = all(evidence_verifier(ref) is True for ref in refs)
        except Exception as exc:
            raise ContractError("CAPABILITY_EVIDENCE_REFERENCE_UNVERIFIED") from exc
        if not verified:
            raise ContractError("CAPABILITY_EVIDENCE_REFERENCE_UNVERIFIED")
    if value["status"] in {"FAIL", "BLOCKED", "PARTIAL", "NOT_RUN"} and error_code is None:
        raise ContractError("CAPABILITY_FAILURE_REASON_REQUIRED")
    canonical_json(value, max_bytes=64 * 1024)
    return value


def create_event(
    *,
    event_type: str,
    sequence: int,
    actor_id: str,
    authority_context: dict[str, Any],
    runtime_id: str,
    state_owner_id: str,
    payload: dict[str, Any],
    previous_digest: str = ZERO_DIGEST,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    idempotency_key: str | None = None,
    evidence_refs: list[str] | None = None,
    event_id: str | None = None,
    recorded_at: int | float | None = None,
) -> dict[str, Any]:
    """Create a validated event mapping. Callers must not mutate it after commit."""
    if evidence_refs is not None and not isinstance(evidence_refs, list):
        raise ContractError("INVALID_EVIDENCE_REFS")
    core = {
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id if event_id is not None else uuid.uuid4().hex,
        "event_type": event_type,
        "sequence": sequence,
        "recorded_at": time.time() if recorded_at is None else recorded_at,
        "actor_id": actor_id,
        "authority_context": authority_context,
        "correlation_id": correlation_id if correlation_id is not None else uuid.uuid4().hex,
        "causation_id": causation_id,
        "idempotency_key": idempotency_key,
        "runtime_id": runtime_id,
        "state_owner_id": state_owner_id,
        "payload": payload,
        "previous_digest": previous_digest,
        "evidence_refs": [] if evidence_refs is None else evidence_refs,
    }
    event = dict(core)
    event["record_digest"] = canonical_digest(core)
    return validate_event(event)


def verify_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Return a bounded machine-readable verification result."""
    try:
        validated = validate_event(event)
    except ContractError as exc:
        return {"ok": False, "reason": str(exc)}
    return {
        "ok": True,
        "reason": "EVENT_VALID",
        "event_id": validated["event_id"],
        "sequence": validated["sequence"],
        "record_digest": validated["record_digest"],
    }
