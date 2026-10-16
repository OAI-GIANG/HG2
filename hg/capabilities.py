"""Fail-closed capability registry and static agent router.

Registry records describe declarations that must be supplied by an external trust
authority. This module never discovers capabilities, verifies signatures, or grants
execution authority. In G2, caller-supplied records are explicitly UNVERIFIED.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable

from .task_contract import canonical_json, DECLARED_ACTION_ALLOWLIST, FORBIDDEN_DECLARED_ACTIONS

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_STATES = frozenset({"UNVERIFIED", "VERIFIED", "REVOKED", "UNAVAILABLE"})
_EFFECTS = frozenset({"READ_ONLY", "LOCAL_MUTATION", "NETWORK", "EXTERNAL_MUTATION", "PRIVILEGED"})


class CapabilityError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _nonblank(value: Any, name: str, max_len: int = 512) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        raise CapabilityError("CAPABILITY_SCHEMA_INVALID", name)
    return value


def validate_capability_record(record: dict[str, Any]) -> dict[str, Any]:
    """Validate record shape only; always returns provenance_state UNVERIFIED."""
    if type(record) is not dict:
        raise CapabilityError("CAPABILITY_SCHEMA_INVALID", "record must be object")
    expected = {
        "capability_id", "contract_version", "provider_id", "actions",
        "effect_class", "authority_policy_ref", "source_ref", "source_digest",
        "valid_from", "expires_at", "revocation_ref",
    }
    if set(record) != expected:
        raise CapabilityError("CAPABILITY_SCHEMA_INVALID", "missing or unknown fields")
    cid = _nonblank(record["capability_id"], "capability_id", 128)
    if not _ID_RE.fullmatch(cid):
        raise CapabilityError("CAPABILITY_SCHEMA_INVALID", "capability_id syntax")
    _nonblank(record["contract_version"], "contract_version", 128)
    _nonblank(record["provider_id"], "provider_id", 128)
    if type(record["actions"]) is not list or not record["actions"]:
        raise CapabilityError("CAPABILITY_SCHEMA_INVALID", "actions must be nonempty array")
    actions = []
    for action in record["actions"]:
        action = _nonblank(action, "action", 128)
        if action in FORBIDDEN_DECLARED_ACTIONS or action not in DECLARED_ACTION_ALLOWLIST:
            raise CapabilityError("CAPABILITY_ACTION_NOT_ALLOWLISTED", action)
        actions.append(action)
    if len(set(actions)) != len(actions):
        raise CapabilityError("CAPABILITY_SCHEMA_INVALID", "duplicate actions")
    if record["effect_class"] not in _EFFECTS:
        raise CapabilityError("CAPABILITY_SCHEMA_INVALID", "unknown effect_class")
    for name in ("authority_policy_ref", "source_ref", "revocation_ref"):
        _nonblank(record[name], name, 1024)
    if not isinstance(record["source_digest"], str) or not _SHA_RE.fullmatch(record["source_digest"]):
        raise CapabilityError("CAPABILITY_SCHEMA_INVALID", "source_digest must be SHA-256")
    for name in ("valid_from", "expires_at"):
        _nonblank(record[name], name, 64)
    if record["valid_from"] >= record["expires_at"]:
        raise CapabilityError("CAPABILITY_SCHEMA_INVALID", "validity interval must be increasing")
    normalized = dict(record)
    normalized["actions"] = sorted(actions)
    normalized["provenance_state"] = "UNVERIFIED"
    normalized["record_digest"] = hashlib.sha256(canonical_json(normalized).encode("utf-8")).hexdigest()
    return normalized


class CapabilityRegistry:
    """Deterministic in-memory registry; no record can be promoted to VERIFIED."""

    def __init__(self, records: Iterable[dict[str, Any]] = (), *, max_records: int = 2048) -> None:
        if not 1 <= max_records <= 100_000:
            raise CapabilityError("CAPABILITY_RESOURCE_LIMIT", "invalid max_records")
        self._records: dict[str, dict[str, Any]] = {}
        for index, record in enumerate(records):
            if index >= max_records:
                raise CapabilityError("CAPABILITY_RESOURCE_LIMIT", "too many records")
            validated = validate_capability_record(record)
            cid = validated["capability_id"]
            if cid in self._records:
                raise CapabilityError("CAPABILITY_DUPLICATE_ID", cid)
            self._records[cid] = validated

    def describe(self, capability_id: str) -> dict[str, Any]:
        record = self._records.get(capability_id)
        if record is None:
            raise CapabilityError("CAPABILITY_UNAVAILABLE", capability_id)
        result = dict(record)
        result["actions"] = list(record["actions"])
        return result

    def resolve(self, capability_id: str, *, required_version: str, action: str) -> dict[str, Any]:
        record = self._records.get(capability_id)
        if record is None:
            return {"allowed": False, "reason": "CAPABILITY_UNAVAILABLE", "capability_id": capability_id}
        if record["contract_version"] != required_version:
            return {"allowed": False, "reason": "CAPABILITY_CONTRACT_MISMATCH", "capability_id": capability_id}
        if action not in record["actions"]:
            return {"allowed": False, "reason": "CAPABILITY_ACTION_MISMATCH", "capability_id": capability_id}
        # Caller-provided record has no authenticated provenance, time oracle, or revocation proof.
        return {"allowed": False, "reason": "CAPABILITY_UNVERIFIED", "capability_id": capability_id,
                "record_digest": record["record_digest"], "provenance_state": "UNVERIFIED"}

    def inventory_digest(self) -> str:
        document = [self._records[key] for key in sorted(self._records)]
        return hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()


def route_agent(
    task: dict[str, Any],
    *,
    available_capability_ids: Iterable[str],
    capability_registry: CapabilityRegistry,
) -> dict[str, Any]:
    """Return a deterministic routing proposal; never selects an executable adapter."""
    requirements = task.get("required_capabilities")
    if type(requirements) is not list:
        raise CapabilityError("TASK_CAPABILITY_REQUIREMENTS_INVALID")
    available = set(available_capability_ids)
    proposals = []
    blocked = []
    for req in sorted(requirements, key=lambda r: str(r.get("capability_id", "")) if isinstance(r, dict) else ""):
        if type(req) is not dict or set(req) != {"capability_id", "contract_version", "required"} or req.get("required") is not True:
            raise CapabilityError("TASK_CAPABILITY_REQUIREMENTS_INVALID")
        cid = _nonblank(req["capability_id"], "capability_id", 128)
        ver = _nonblank(req["contract_version"], "contract_version", 128)
        if cid not in available:
            blocked.append({"capability_id": cid, "reason": "CAPABILITY_NOT_AVAILABLE_IN_CALLER_INVENTORY"})
            continue
        resolution = capability_registry.resolve(cid, required_version=ver, action="__not_selected__")
        blocked.append({"capability_id": cid, "reason": resolution["reason"]})
    return {
        "task_id": task.get("task_id"),
        "routing_state": "BLOCKED" if blocked else "NO_CAPABILITY_REQUIRED",
        "executable": False,
        "selected_provider": None,
        "proposals": proposals,
        "blocked_requirements": blocked,
        "registry_digest": capability_registry.inventory_digest(),
    }
