"""Provenance-aware memory classification; no automatic fact promotion.

This module records trust metadata supplied by a caller but does not authenticate that
metadata. Only an external verified-trust adapter could promote a memory item.
"""
from __future__ import annotations

import hashlib
from typing import Any, Iterable

from .task_contract import canonical_json

_TRUST_LEVELS = ("UNVERIFIED", "CORROBORATED", "VERIFIED", "REVOKED")
_SENSITIVITY = frozenset({"PUBLIC", "INTERNAL", "CONFIDENTIAL", "SECRET"})


class MemoryError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _text(value: Any, field: str, max_len: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        raise MemoryError("MEMORY_SCHEMA_INVALID", field)
    return value


def create_memory_record(
    *,
    memory_id: str,
    statement: str,
    source_ref: str | None,
    source_digest: str | None,
    authority_ref: str | None,
    observed_at: str | None,
    expires_at: str | None,
    sensitivity: str = "INTERNAL",
    parent_memory_ids: Iterable[str] = (),
    supplied_trust_level: str = "UNVERIFIED",
) -> dict[str, Any]:
    """Create untrusted memory metadata. Caller labels cannot promote trust."""
    _text(memory_id, "memory_id", 128)
    _text(statement, "statement")
    if sensitivity not in _SENSITIVITY:
        raise MemoryError("MEMORY_SCHEMA_INVALID", "sensitivity")
    if supplied_trust_level not in _TRUST_LEVELS:
        raise MemoryError("MEMORY_SCHEMA_INVALID", "supplied_trust_level")
    problems = []
    if not source_ref:
        problems.append("SOURCE_MISSING")
    if not source_digest or len(source_digest) != 64 or any(c not in "0123456789abcdef" for c in source_digest):
        problems.append("SOURCE_DIGEST_MISSING_OR_INVALID")
    if not authority_ref:
        problems.append("AUTHORITY_MISSING")
    if not observed_at:
        problems.append("OBSERVATION_TIME_MISSING")
    if not expires_at:
        problems.append("EXPIRY_POLICY_MISSING")
    parents = sorted(set(parent_memory_ids))
    record = {
        "schema_version": "hg.provenance-memory.v1",
        "memory_id": memory_id,
        "statement": statement,
        "source_ref": source_ref,
        "source_digest": source_digest,
        "authority_ref": authority_ref,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "sensitivity": sensitivity,
        "parent_memory_ids": parents,
        "trust_level": "UNVERIFIED" if supplied_trust_level != "REVOKED" else "REVOKED",
        "source_trust_claim": supplied_trust_level,
        "blockers": sorted(set(problems)),
    }
    record["record_digest"] = hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()
    return record


def assess_memory(record: dict[str, Any], *, known_authority_refs: set[str] | None = None) -> dict[str, Any]:
    if type(record) is not dict or record.get("schema_version") != "hg.provenance-memory.v1":
        return {"trusted": False, "status": "UNVERIFIED", "reasons": ["MEMORY_SCHEMA_INVALID"]}
    reasons = list(record.get("blockers", []))
    if known_authority_refs is None or record.get("authority_ref") not in known_authority_refs:
        reasons.append("AUTHORITY_NOT_VERIFIED")
    if record.get("trust_level") != "VERIFIED":
        reasons.append("SOURCE_PROVENANCE_NOT_VERIFIED")
    # G2 provides no verifier capable of making a record VERIFIED.
    return {"trusted": False, "status": "REVOKED" if record.get("trust_level") == "REVOKED" else "UNVERIFIED",
            "reasons": sorted(set(reasons or ["TRUST_PROMOTION_ADAPTER_UNAVAILABLE"]))}


def detect_memory_conflicts(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect exact-key conflicts only; never choose a winner implicitly."""
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        if type(record) is not dict:
            continue
        source = record.get("source_ref")
        key = record.get("memory_key")
        value_digest = record.get("value_digest")
        if not isinstance(source, str) or not isinstance(key, str) or not isinstance(value_digest, str):
            continue
        by_key.setdefault((source, key), []).append(record)
    conflicts = []
    for (source, key), group in sorted(by_key.items()):
        digests = sorted({r["value_digest"] for r in group})
        if len(digests) > 1:
            conflicts.append({"source_ref": source, "memory_key": key,
                              "value_digests": digests, "status": "CONFLICT_UNRESOLVED"})
    return conflicts
