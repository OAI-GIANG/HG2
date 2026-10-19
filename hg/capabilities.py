"""Fail-closed capability registry and static agent router.

Registry records describe declarations that must be supplied by an external trust
authority. This module never discovers capabilities, verifies signatures, or grants
execution authority. In G2, caller-supplied records are explicitly UNVERIFIED.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from itertools import islice
from typing import Any, Callable, Iterable

from .task_contract import (AUTHORITY_POLICY_REF, ContractError, canonical_json,
                            DECLARED_ACTION_ALLOWLIST, FORBIDDEN_DECLARED_ACTIONS, validate_contract)

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


def _timestamp(value: Any, name: str) -> datetime:
    text = _nonblank(value, name, 64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CapabilityError("CAPABILITY_SCHEMA_INVALID", name + " invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CapabilityError("CAPABILITY_SCHEMA_INVALID", name + " timezone required")
    return parsed


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
    if not isinstance(record["effect_class"], str) or record["effect_class"] not in _EFFECTS:
        raise CapabilityError("CAPABILITY_SCHEMA_INVALID", "unknown effect_class")
    for name in ("authority_policy_ref", "source_ref", "revocation_ref"):
        _nonblank(record[name], name, 1024)
    if record["authority_policy_ref"] != AUTHORITY_POLICY_REF:
        raise CapabilityError("CAPABILITY_POLICY_UNRESOLVED", "not the canonical HG authority policy")
    if not isinstance(record["source_digest"], str) or not _SHA_RE.fullmatch(record["source_digest"]):
        raise CapabilityError("CAPABILITY_SCHEMA_INVALID", "source_digest must be SHA-256")
    valid_from = _timestamp(record["valid_from"], "valid_from")
    expires_at = _timestamp(record["expires_at"], "expires_at")
    if valid_from >= expires_at:
        raise CapabilityError("CAPABILITY_SCHEMA_INVALID", "validity interval must be increasing")
    normalized = dict(record)
    normalized["actions"] = sorted(actions)
    normalized["provenance_state"] = "UNVERIFIED"
    normalized["record_digest"] = hashlib.sha256(canonical_json(normalized).encode("utf-8")).hexdigest()
    return normalized


class CapabilityRegistry:
    """Deterministic in-memory registry; no record can be promoted to VERIFIED."""

    def __init__(self, records: Iterable[dict[str, Any]] = (), *, max_records: int = 2048,
                 trust_verifier: Callable[[dict[str, Any]], tuple[bool, str]] | None = None) -> None:
        if not 1 <= max_records <= 100_000:
            raise CapabilityError("CAPABILITY_RESOURCE_LIMIT", "invalid max_records")
        self._records: dict[str, dict[str, Any]] = {}
        self._trust_verifier = trust_verifier
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
        try:
            now = datetime.now(timezone.utc)
            valid_from = datetime.fromisoformat(record["valid_from"].replace("Z", "+00:00"))
            expires_at = datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return {"allowed": False, "reason": "CAPABILITY_VALIDITY_INVALID", "capability_id": capability_id}
        if now < valid_from:
            return {"allowed": False, "reason": "CAPABILITY_NOT_YET_VALID", "capability_id": capability_id}
        if now >= expires_at:
            return {"allowed": False, "reason": "CAPABILITY_EXPIRED", "capability_id": capability_id}
        if action not in record["actions"]:
            return {"allowed": False, "reason": "CAPABILITY_ACTION_MISMATCH", "capability_id": capability_id}
        # The verifier must be supplied by a trusted runtime bootstrap, never by a task.
        if self._trust_verifier is None:
            return {"allowed": False, "reason": "CAPABILITY_UNVERIFIED", "capability_id": capability_id,
                    "record_digest": record["record_digest"], "provenance_state": "UNVERIFIED"}
        try:
            decision = self._trust_verifier(dict(record))
        except Exception:
            return {"allowed": False, "reason": "CAPABILITY_VERIFIER_ERROR", "capability_id": capability_id,
                    "record_digest": record["record_digest"], "provenance_state": "UNVERIFIED"}
        if type(decision) is not tuple or len(decision) != 2 or type(decision[0]) is not bool or not isinstance(decision[1], str) or not decision[1].strip():
            return {"allowed": False, "reason": "CAPABILITY_VERIFIER_INVALID_RESPONSE", "capability_id": capability_id,
                    "record_digest": record["record_digest"], "provenance_state": "UNVERIFIED"}
        if not decision[0]:
            return {"allowed": False, "reason": "CAPABILITY_TRUST_REJECTED", "capability_id": capability_id,
                    "decision_ref": decision[1], "record_digest": record["record_digest"],
                    "provenance_state": "REJECTED"}
        return {"allowed": True, "reason": "CAPABILITY_TRUST_VERIFIED", "capability_id": capability_id,
                "provider_id": record["provider_id"], "decision_ref": decision[1],
                "record_digest": record["record_digest"], "provenance_state": "VERIFIED"}

    def inventory_digest(self) -> str:
        document = [self._records[key] for key in sorted(self._records)]
        return hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()


def route_agent(
    task: dict[str, Any],
    *,
    available_capability_ids: Iterable[str],
    capability_registry: CapabilityRegistry,
    authorization_verifier: Callable[[dict[str, Any]], tuple[bool, str]] | None = None,
) -> dict[str, Any]:
    """Validate a complete task contract and return route proposals, never execution."""
    try:
        task = validate_contract(task)
    except ContractError as exc:
        raise CapabilityError("TASK_CONTRACT_INVALID", exc.code) from exc
    requirements = task.get("required_capabilities")
    if type(requirements) is not list or len(requirements) > 2048:
        raise CapabilityError("TASK_CAPABILITY_REQUIREMENTS_INVALID")
    available_values = list(islice(iter(available_capability_ids), 4097))
    if len(available_values) > 4096:
        raise CapabilityError("CAPABILITY_RESOURCE_LIMIT", "available inventory too large")
    if any(not isinstance(item, str) or not item.strip() for item in available_values):
        raise CapabilityError("TASK_CAPABILITY_REQUIREMENTS_INVALID", "available IDs must be strings")
    available = set(available_values)
    auth = task.get("authorization_requirement")
    action = auth.get("action") if type(auth) is dict else None
    proposals: list[dict[str, str]] = []
    blocked: list[dict[str, str]] = []
    auth_required = auth["authenticated_actor_required"] or auth["approval_required"]
    if auth_required:
        if authorization_verifier is None:
            blocked.append({"capability_id": "__task_authorization__", "reason": "TASK_AUTHORIZATION_VERIFIER_UNAVAILABLE"})
        else:
            try:
                decision = authorization_verifier(dict(task))
                valid_decision = (type(decision) is tuple and len(decision) == 2 and
                                  type(decision[0]) is bool and isinstance(decision[1], str) and decision[1].strip())
                if not valid_decision or not decision[0]:
                    blocked.append({"capability_id": "__task_authorization__", "reason": "TASK_AUTHORIZATION_NOT_VERIFIED"})
            except Exception:
                blocked.append({"capability_id": "__task_authorization__", "reason": "TASK_AUTHORIZATION_VERIFIER_ERROR"})
    if requirements and (not isinstance(action, str) or not action.strip()):
        raise CapabilityError("TASK_AUTHORIZATION_ACTION_MISSING")
    for req in sorted(requirements, key=lambda r: str(r.get("capability_id", "")) if isinstance(r, dict) else ""):
        if type(req) is not dict or set(req) != {"capability_id", "contract_version", "required"} or req.get("required") is not True:
            raise CapabilityError("TASK_CAPABILITY_REQUIREMENTS_INVALID")
        cid = _nonblank(req["capability_id"], "capability_id", 128)
        ver = _nonblank(req["contract_version"], "contract_version", 128)
        if cid not in available:
            blocked.append({"capability_id": cid, "reason": "CAPABILITY_NOT_AVAILABLE_IN_CALLER_INVENTORY"})
            continue
        resolution = capability_registry.resolve(cid, required_version=ver, action=action)
        if resolution["allowed"]:
            proposals.append({"capability_id": cid, "provider_id": resolution["provider_id"],
                              "decision_ref": resolution["decision_ref"]})
        else:
            blocked.append({"capability_id": cid, "reason": resolution["reason"]})
    state = "BLOCKED" if blocked else ("ROUTED" if proposals else "NO_CAPABILITY_REQUIRED")
    return {
        "task_id": task.get("task_id"),
        "routing_state": state,
        "executable": False,
        "selected_provider": None,
        "routes": proposals,
        "blocked_requirements": blocked,
        "registry_digest": capability_registry.inventory_digest(),
    }
