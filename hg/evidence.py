"""Evidence envelopes and deterministic claim verification primitives.

Evidence structures are declarations about observations. SHA-256 detects byte changes only;
without trusted capture, authenticated actor identity and provenance verification, evidence
is not promoted to TRUSTED and claims remain UNVERIFIED.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Iterable

from .task_contract import canonical_json

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_OBSERVED = frozenset({"PASS", "FAIL", "INCONCLUSIVE", "NOT_RUN", "BLOCKED"})
_TRUST = frozenset({"UNVERIFIED", "VERIFIED", "REJECTED"})


class EvidenceError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _text(v: Any, name: str, max_len: int = 2048) -> str:
    if not isinstance(v, str) or not v.strip() or len(v) > max_len:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", name)
    return v


def _digest(v: Any, name: str) -> str:
    if not isinstance(v, str) or not _SHA256_RE.fullmatch(v):
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", name + " must be lowercase SHA-256")
    return v


def _timestamp(v: Any, name: str) -> datetime:
    text = _text(v, name, 64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", name + " invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", name + " timezone required")
    return parsed


def evidence_digest(envelope: dict[str, Any]) -> str:
    unsigned = dict(envelope)
    unsigned.pop("envelope_digest", None)
    return hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()


def validate_evidence_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    if type(envelope) is not dict:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "envelope must be object")
    required = {
        "schema_version", "evidence_id", "task_id", "test_id", "source_uri",
        "source_revision", "source_digest", "runtime_id", "build_id", "environment",
        "execution_id", "oracle_id", "oracle_version", "observed_status", "started_at",
        "finished_at", "exit_code", "raw_artifact_uri", "raw_artifact_digest",
        "parent_evidence_ids", "actor_ref", "correlation_id", "causation_id",
        "payload_digest", "trust_state", "envelope_digest",
    }
    if set(envelope) != required:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "missing or unknown fields")
    if envelope["schema_version"] != "hg.evidence-envelope.v1":
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "unsupported schema version")
    for key in ("evidence_id", "task_id", "test_id", "execution_id", "oracle_id", "correlation_id"):
        value = _text(envelope[key], key, 128)
        if not _ID_RE.fullmatch(value):
            raise EvidenceError("EVIDENCE_SCHEMA_INVALID", key + " invalid identifier")
    for key in ("source_uri", "source_revision", "runtime_id", "build_id", "oracle_version", "raw_artifact_uri", "actor_ref", "causation_id"):
        _text(envelope[key], key)
    for key in ("source_digest", "raw_artifact_digest", "payload_digest"):
        _digest(envelope[key], key)
    if type(envelope["environment"]) is not dict:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "environment must be object")
    if envelope["observed_status"] not in _OBSERVED:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "unknown observed_status")
    if type(envelope["exit_code"]) is not int or envelope["exit_code"] < -255 or envelope["exit_code"] > 255:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "exit_code must be bounded integer")
    started = _timestamp(envelope["started_at"], "started_at")
    finished = _timestamp(envelope["finished_at"], "finished_at")
    if finished < started:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "finished_at precedes started_at")
    if type(envelope["parent_evidence_ids"]) is not list or len(envelope["parent_evidence_ids"]) > 4096:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "parent_evidence_ids must be bounded array")
    parents = [_text(x, "parent_evidence_id", 128) for x in envelope["parent_evidence_ids"]]
    if len(parents) != len(set(parents)):
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "duplicate parent evidence IDs")
    if envelope["trust_state"] not in _TRUST:
        raise EvidenceError("EVIDENCE_SCHEMA_INVALID", "unknown trust_state")
    if envelope["trust_state"] == "VERIFIED":
        raise EvidenceError("EVIDENCE_TRUST_PROMOTION_FORBIDDEN", "schema validation cannot authenticate evidence")
    _digest(envelope["envelope_digest"], "envelope_digest")
    if envelope["envelope_digest"] != evidence_digest(envelope):
        raise EvidenceError("EVIDENCE_INTEGRITY_FAILED", "envelope digest mismatch")
    result = dict(envelope)
    result["parent_evidence_ids"] = parents
    return result


def verify_claim(
    *,
    claim_id: str,
    criterion_id: str,
    evidence_ids: Iterable[str],
    evidence_store: dict[str, dict[str, Any]],
    expected_source_revision: str,
    expected_oracle_id: str,
    expected_oracle_version: str,
) -> dict[str, Any]:
    """Verify references and consistency only; never authenticates remote provenance."""
    _text(claim_id, "claim_id", 128)
    _text(criterion_id, "criterion_id", 128)
    ids = list(evidence_ids)
    if not ids:
        return {"claim_id": claim_id, "criterion_id": criterion_id, "status": "UNVERIFIED",
                "reason": "EVIDENCE_MISSING", "evidence_ids": []}
    results = []
    for eid in ids:
        envelope = evidence_store.get(eid)
        if envelope is None:
            results.append({"evidence_id": eid, "ok": False, "reason": "EVIDENCE_MISSING"})
            continue
        try:
            checked = validate_evidence_envelope(envelope)
        except EvidenceError as exc:
            results.append({"evidence_id": eid, "ok": False, "reason": exc.code})
            continue
        reason = None
        if checked["source_revision"] != expected_source_revision:
            reason = "EVIDENCE_SOURCE_REVISION_MISMATCH"
        elif checked["oracle_id"] != expected_oracle_id or checked["oracle_version"] != expected_oracle_version:
            reason = "EVIDENCE_ORACLE_MISMATCH"
        elif checked["observed_status"] != "PASS":
            reason = "EVIDENCE_OBSERVED_STATUS_NOT_PASS"
        elif checked["trust_state"] != "VERIFIED":
            reason = "EVIDENCE_PROVENANCE_UNVERIFIED"
        results.append({"evidence_id": eid, "ok": reason is None, "reason": reason or "CONSISTENT"})
    ok = bool(results) and all(r["ok"] for r in results)
    # Current G1/G2 code cannot set trust_state=VERIFIED, so this normally remains UNVERIFIED.
    return {"claim_id": claim_id, "criterion_id": criterion_id,
            "status": "VERIFIED" if ok else "UNVERIFIED", "reason": "ALL_EVIDENCE_CONSISTENT" if ok else "EVIDENCE_NOT_VERIFIED",
            "evidence_results": results, "authenticated_provenance": False}
