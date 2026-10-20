"""Governed append-preserving experience memory on the existing provenance store.

This layer adds scope, validity, explicit supersession and conflict-aware retrieval over
SQLiteProvenanceMemoryStore. Trust labels remain untrusted unless a separate trust-root
adapter verifies the exact source; a digest alone is never a promotion credential.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Mapping

from .provenance_memory import (
    MemoryError as ProvenanceMemoryError,
    SQLiteProvenanceMemoryStore,
    create_memory_record,
    detect_memory_conflicts,
    effective_memory_trust,
    memory_freshness,
)
from .task_contract import canonical_json

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_EXPERIENCE_TYPES = frozenset({
    "OBSERVATION", "HYPOTHESIS", "DECISION", "FAILURE", "LESSON", "PLAN_RESULT",
})
_STATUSES = frozenset({"ACTIVE", "SUPERSEDED", "REVOKED"})


class ExperienceMemoryError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ExperienceMemoryError("EXPERIENCE_" + field.upper() + "_INVALID")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExperienceMemoryError("EXPERIENCE_" + field.upper() + "_INVALID") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ExperienceMemoryError("EXPERIENCE_" + field.upper() + "_TIMEZONE_REQUIRED")
    return dt.astimezone(timezone.utc)


def create_experience(
    *,
    memory_id: str,
    statement: str,
    source_ref: str,
    source_digest: str,
    authority_ref: str,
    observed_at: str,
    expires_at: str,
    memory_key: str,
    experience_type: str,
    scope: str,
    task_id: str | None = None,
    parent_memory_ids: list[str] | None = None,
    sensitivity: str = "INTERNAL",
    supersedes: str | None = None,
    superseded_by: str | None = None,
    status: str = "ACTIVE",
    conflict_ids: list[str] | None = None,
) -> dict[str, Any]:
    for field, value, limit in (
        ("memory_id", memory_id, 128), ("statement", statement, 4096),
        ("source_ref", source_ref, 1024), ("authority_ref", authority_ref, 1024),
        ("memory_key", memory_key, 256), ("scope", scope, 512),
    ):
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ExperienceMemoryError("EXPERIENCE_" + field.upper() + "_INVALID")
    if not _ID.fullmatch(memory_id):
        raise ExperienceMemoryError("EXPERIENCE_MEMORY_ID_INVALID")
    if not isinstance(experience_type, str) or experience_type not in _EXPERIENCE_TYPES:
        raise ExperienceMemoryError("EXPERIENCE_TYPE_INVALID")
    if task_id is not None and (not isinstance(task_id, str) or not _ID.fullmatch(task_id)):
        raise ExperienceMemoryError("EXPERIENCE_TASK_ID_INVALID")
    observed = _timestamp(observed_at, "observed_at")
    expires = _timestamp(expires_at, "expires_at")
    if expires <= observed:
        raise ExperienceMemoryError("EXPERIENCE_EXPIRY_NOT_AFTER_OBSERVATION")
    record = create_memory_record(
        memory_id=memory_id, statement=statement, source_ref=source_ref,
        source_digest=source_digest, authority_ref=authority_ref,
        observed_at=observed.isoformat(), expires_at=expires.isoformat(),
        memory_key=memory_key, sensitivity=sensitivity,
        parent_memory_ids=parent_memory_ids or [], supplied_trust_level="UNVERIFIED",
    )
    value = dict(record)
    value["schema_version"] = "hg.experience-memory.v1"
    value["experience_type"] = experience_type
    value["scope"] = scope
    value["task_id"] = task_id
    value["valid_from"] = observed.isoformat()
    value["valid_until"] = expires.isoformat()
    if not isinstance(status, str) or status not in _STATUSES:
        raise ExperienceMemoryError("EXPERIENCE_STATUS_INVALID")
    for field, linked_id in (("supersedes", supersedes), ("superseded_by", superseded_by)):
        if linked_id is not None and (
            not isinstance(linked_id, str) or not _ID.fullmatch(linked_id)
            or linked_id == memory_id
        ):
            raise ExperienceMemoryError("EXPERIENCE_" + field.upper() + "_INVALID")
    conflicts = [] if conflict_ids is None else conflict_ids
    if not isinstance(conflicts, list) or any(
        not isinstance(item, str) or not _ID.fullmatch(item) for item in conflicts
    ):
        raise ExperienceMemoryError("EXPERIENCE_CONFLICT_IDS_INVALID")
    value["status"] = status
    value["supersedes"] = supersedes
    value["superseded_by"] = superseded_by
    value["conflict_ids"] = sorted(set(conflicts))
    value["trust_level"] = "UNVERIFIED"
    value.pop("record_digest", None)
    value["record_digest"] = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return value


class ExperienceMemoryStore:
    """Experience records built over the canonical provenance-memory store.

    The backing store is authoritative for immutable append evidence. Supersession is
    expressed by additional versioned records; previous records remain preserved.
    """

    def __init__(self, store: SQLiteProvenanceMemoryStore):
        if not isinstance(store, SQLiteProvenanceMemoryStore):
            raise ExperienceMemoryError("EXPERIENCE_STORE_MUST_BE_PROVENANCE_SQLITE")
        self.store = store

    @staticmethod
    def _digest(record: Mapping[str, Any]) -> str:
        body = dict(record)
        body.pop("record_digest", None)
        return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()

    def put(self, record: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(record, Mapping):
            raise ExperienceMemoryError("EXPERIENCE_RECORD_INVALID")
        value = dict(record)
        if value.get("schema_version") != "hg.experience-memory.v1":
            raise ExperienceMemoryError("EXPERIENCE_SCHEMA_UNSUPPORTED")
        required = {
            "experience_type", "scope", "task_id", "valid_from", "valid_until",
            "status", "supersedes", "superseded_by", "conflict_ids",
        }
        if not required.issubset(value):
            raise ExperienceMemoryError("EXPERIENCE_FIELDS_MISSING")
        if value["experience_type"] not in _EXPERIENCE_TYPES or value["status"] not in _STATUSES:
            raise ExperienceMemoryError("EXPERIENCE_TYPE_OR_STATUS_INVALID")
        if value["trust_level"] != "UNVERIFIED":
            raise ExperienceMemoryError("EXPERIENCE_CANNOT_SELF_PROMOTE_TRUST")
        valid_from = _timestamp(value["valid_from"], "valid_from")
        valid_until = _timestamp(value["valid_until"], "valid_until")
        if valid_until <= valid_from:
            raise ExperienceMemoryError("EXPERIENCE_VALIDITY_INTERVAL_INVALID")
        if value["supersedes"] is not None and (
            not isinstance(value["supersedes"], str) or not _ID.fullmatch(value["supersedes"])
        ):
            raise ExperienceMemoryError("EXPERIENCE_SUPERSEDES_INVALID")
        if value["superseded_by"] is not None and (
            not isinstance(value["superseded_by"], str) or not _ID.fullmatch(value["superseded_by"])
        ):
            raise ExperienceMemoryError("EXPERIENCE_SUPERSEDED_BY_INVALID")
        if not isinstance(value["conflict_ids"], list) or any(
            not isinstance(x, str) or not _ID.fullmatch(x) for x in value["conflict_ids"]
        ):
            raise ExperienceMemoryError("EXPERIENCE_CONFLICT_IDS_INVALID")
        if value.get("record_digest") != self._digest(value):
            raise ExperienceMemoryError("EXPERIENCE_RECORD_DIGEST_MISMATCH")
        # Convert only the envelope to the base schema that the durable store understands,
        # with a distinct memory id per immutable version. Keep the full record inside statement-free metadata.
        base = {key: value[key] for key in (
            "memory_id", "statement", "value_digest", "source_ref", "source_digest",
            "authority_ref", "observed_at", "expires_at", "memory_key", "sensitivity",
            "parent_memory_ids", "trust_level", "source_trust_claim", "blockers",
        ) if key in value}
        base["schema_version"] = "hg.provenance-memory.v1"
        # The existing store preserves a canonical record. Encode the complete extension
        # envelope as the statement so every field remains recoverable through get().
        value["record_digest"] = self._digest(value)
        base["statement"] = canonical_json(value)
        base["memory_key"] = value["memory_key"]
        base["source_ref"] = value["source_ref"]
        base["value_digest"] = hashlib.sha256(base["statement"].encode("utf-8")).hexdigest()
        base["record_digest"] = self._digest(base)
        result = self.store.put(base)
        return {
            "stored": result["stored"],
            "idempotent": result["idempotent"],
            "memory_id": value["memory_id"],
            "experience_digest": value["record_digest"],
            "trust_level": "UNVERIFIED",
            "conflict": result.get("conflict", False),
            "storage_record_digest": result["record_digest"],
        }

    def get(self, memory_id: str) -> dict[str, Any]:
        try:
            base = self.store.get(memory_id)
        except ProvenanceMemoryError as exc:
            raise ExperienceMemoryError("EXPERIENCE_" + exc.code) from exc
        statement = base.get("statement")
        if not isinstance(statement, str):
            raise ExperienceMemoryError("EXPERIENCE_RECORD_NOT_IN_STORE")
        import json
        try:
            value = json.loads(statement)
        except (ValueError, TypeError) as exc:
            raise ExperienceMemoryError("EXPERIENCE_RECORD_ENCODING_INVALID") from exc
        if not isinstance(value, dict) or value.get("schema_version") != "hg.experience-memory.v1":
            raise ExperienceMemoryError("EXPERIENCE_RECORD_NOT_IN_STORE")
        if canonical_json(value) != statement or self._digest(value) != value.get("record_digest"):
            raise ExperienceMemoryError("EXPERIENCE_RECORD_DIGEST_MISMATCH")
        return value

    def conflicts(self) -> list[dict[str, Any]]:
        return self.store.list_conflicts()

    def decide_supersession(self, old_id: str, new_record: Mapping[str, Any]) -> dict[str, Any]:
        """Return a proposal only; do not mutate the old record or auto-resolve a conflict."""
        if not isinstance(old_id, str) or not _ID.fullmatch(old_id):
            raise ExperienceMemoryError("EXPERIENCE_SUPERSESSION_ID_INVALID")
        old = self.get(old_id)
        new_value = dict(new_record)
        if new_value.get("memory_id") == old_id:
            raise ExperienceMemoryError("EXPERIENCE_SUPERSESSION_SELF_REFERENCE")
        if new_value.get("memory_key") != old.get("memory_key") or new_value.get("scope") != old.get("scope"):
            raise ExperienceMemoryError("EXPERIENCE_SUPERSESSION_SCOPE_MISMATCH")
        if new_value.get("source_ref") != old.get("source_ref"):
            raise ExperienceMemoryError("EXPERIENCE_SUPERSESSION_SOURCE_MISMATCH")
        if new_value.get("supersedes") != old_id:
            raise ExperienceMemoryError("EXPERIENCE_SUPERSESSION_LINK_MISMATCH")
        return {
            "status": "SUPERSESSION_PROPOSED_NOT_APPLIED",
            "old_memory_id": old_id,
            "new_memory_id": new_value.get("memory_id"),
            "scope": old["scope"],
            "memory_key": old["memory_key"],
            "old_digest": old["record_digest"],
            "new_digest": new_value.get("record_digest"),
            "automatic_activation": False,
        }

    def eligible_records(self, *, scope: str, now: str) -> list[dict[str, Any]]:
        current = _timestamp(now, "now")
        if not isinstance(scope, str) or not scope.strip():
            raise ExperienceMemoryError("EXPERIENCE_SCOPE_REQUIRED")
        records = []
        for event in self.store.events():
            if event.get("event_type") not in {"MEMORY_STORED", "MEMORY_CONFLICT"}:
                continue
            memory_id = event.get("memory_id")
            try:
                record = self.get(memory_id)
            except ExperienceMemoryError:
                continue
            if record.get("scope") != scope or record.get("status") != "ACTIVE":
                continue
            freshness = memory_freshness(record, now=current)
            if not freshness["usable"]:
                continue
            if _timestamp(record["valid_from"], "valid_from") <= current < _timestamp(record["valid_until"], "valid_until"):
                records.append(record)
        conflicts = self.conflicts()
        conflicted_ids = {mid for group in conflicts for mid in group.get("memory_ids", [])}
        return [r for r in records if r["memory_id"] not in conflicted_ids
                and effective_memory_trust(r) != "REVOKED"]


    def supersede(self, old_id: str, new_record: Mapping[str, Any], *,
                  principal: Any, verifier=None, verifier_id: str | None = None) -> dict[str, Any]:
        """Persist a two-record, evidence-linked supersession without deleting history.

        The previous and successor records are immutable versions. Caller-supplied
        trust levels are ignored; source verification must be provided by a verifier.
        This operation writes the successor as PROPOSED until source verification returns
        a typed, source-bound decision reference.
        """
        from .policy import authorize_service_mutation

        decision = authorize_service_mutation("audit.append", principal)
        if not decision.allowed:
            raise ExperienceMemoryError("EXPERIENCE_AUTHORIZATION_" + decision.reason)
        if not callable(verifier) or not isinstance(verifier_id, str) or not _ID.fullmatch(verifier_id):
            raise ExperienceMemoryError("EXPERIENCE_SUPERSESSION_VERIFIER_REQUIRED")
        old = self.get(old_id)
        candidate = dict(new_record)
        if candidate.get("supersedes") != old_id:
            raise ExperienceMemoryError("EXPERIENCE_SUPERSESSION_LINK_MISMATCH")
        self.decide_supersession(old_id, candidate)
        if candidate.get("status") != "ACTIVE":
            raise ExperienceMemoryError("EXPERIENCE_SUCCESSOR_MUST_START_ACTIVE")
        try:
            trust_decision = verifier(dict(candidate))
        except Exception as exc:
            raise ExperienceMemoryError("EXPERIENCE_SUPERSESSION_VERIFIER_ERROR") from exc
        if (not isinstance(trust_decision, tuple) or len(trust_decision) != 2
                or type(trust_decision[0]) is not bool or not isinstance(trust_decision[1], str)
                or not trust_decision[1].strip()):
            raise ExperienceMemoryError("EXPERIENCE_SUPERSESSION_VERIFIER_INVALID_RESPONSE")
        if not trust_decision[0]:
            raise ExperienceMemoryError("EXPERIENCE_SUPERSESSION_SOURCE_UNVERIFIED")

        # Preserve old content; supersession is represented as a new decision event rather
        # than rewriting/deleting the old immutable record. Query then interprets the link.
        decision_payload = {
            "schema_version": "HG_EXPERIENCE_SUPERSESSION_V1",
            "old_memory_id": old_id,
            "new_memory_id": candidate.get("memory_id"),
            "old_record_digest": old["record_digest"],
            "new_record_digest": candidate.get("record_digest"),
            "scope": old["scope"],
            "memory_key": old["memory_key"],
            "verifier_id": verifier_id,
            "verifier_decision_ref": trust_decision[1],
            "result": "SUPERSESSION_DECISION_RECORDED_NOT_ACTIVATED",
            "automatic_activation": False,
        }
        decision_digest = hashlib.sha256(canonical_json(decision_payload).encode("utf-8")).hexdigest()
        event_memory_id = "supersession-" + decision_digest[:32]
        statement = canonical_json(decision_payload)
        base = {
            "schema_version": "hg.provenance-memory.v1",
            "memory_id": event_memory_id,
            "memory_key": "hg.experience.supersession",
            "statement": statement,
            "value_digest": hashlib.sha256(statement.encode("utf-8")).hexdigest(),
            "source_ref": old["source_ref"],
            "source_digest": old["source_digest"],
            "authority_ref": old["authority_ref"],
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": old["expires_at"],
            "sensitivity": old["sensitivity"],
            "parent_memory_ids": sorted({old_id, candidate["memory_id"]}),
            "trust_level": "UNVERIFIED",
            "source_trust_claim": "UNVERIFIED",
            "blockers": ["SUPERSESSION_DECISION_ONLY"],
        }
        base["record_digest"] = self._digest(base)
        stored = self.store.put(base)
        return {**decision_payload, "decision_digest": decision_digest,
                "decision_record_id": event_memory_id, "storage_idempotent": stored["idempotent"],
                "trust_level": "UNVERIFIED", "note": "historical records preserved; successor activation is separate"}

    def lineage(self, memory_id: str, *, max_depth: int = 64) -> dict[str, Any]:
        if not isinstance(memory_id, str) or not _ID.fullmatch(memory_id):
            raise ExperienceMemoryError("EXPERIENCE_MEMORY_ID_INVALID")
        if isinstance(max_depth, bool) or not isinstance(max_depth, int) or not 1 <= max_depth <= 512:
            raise ExperienceMemoryError("EXPERIENCE_LINEAGE_DEPTH_INVALID")
        root = self.get(memory_id)
        queue = [(memory_id, 0)]
        visited = set()
        edges = []
        while queue:
            current_id, depth = queue.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)
            if depth >= max_depth:
                continue
            current = self.get(current_id)
            parents = current.get("parent_memory_ids", [])
            if not isinstance(parents, list):
                raise ExperienceMemoryError("EXPERIENCE_PARENT_IDS_INVALID")
            for parent in sorted(parents):
                if not isinstance(parent, str) or not _ID.fullmatch(parent):
                    raise ExperienceMemoryError("EXPERIENCE_PARENT_ID_INVALID")
                edges.append({"from": current_id, "to": parent, "relation": "DERIVED_FROM"})
                queue.append((parent, depth + 1))
            supersedes = current.get("supersedes")
            if supersedes:
                edges.append({"from": current_id, "to": supersedes, "relation": "SUPERSEDES"})
                queue.append((supersedes, depth + 1))
        return {
            "schema_version": "HG_EXPERIENCE_LINEAGE_V1",
            "root_memory_id": memory_id,
            "root_digest": root["record_digest"],
            "visited_memory_ids": sorted(visited),
            "edges": sorted(edges, key=lambda edge: (edge["from"], edge["relation"], edge["to"])),
            "truncated": bool(queue),
        }
