"""HG-native, offline-first skill contract validation.

A skill document is untrusted declarative input. This module validates its
metadata only; it never evaluates instructions, imports code, or executes hooks.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from .contracts import ContractError, canonical_digest, canonical_json

SKILL_SCHEMA_VERSION = "HG_SKILL_V1"
TRUST_LEVELS = frozenset({
    "BUILTIN_VERIFIED", "THIRD_PARTY_REVIEWED", "UNREVIEWED", "REJECTED",
})
SOURCE_KINDS = frozenset({"BUILTIN", "THIRD_PARTY"})
RISK_CLASSES = frozenset({
    "LOCAL_READ_ONLY", "LOCAL_WRITE", "OUTBOUND_PROVIDER_CALL",
    "EXTERNAL_WRITE", "DESTRUCTIVE",
})
_SKILL_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CAPABILITY = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
_MAX_MANIFEST_BYTES = 64 * 1024
_REQUIRED = {
    "schema_version", "skill_id", "version", "name", "description", "triggers",
    "required_capabilities", "risk_class", "input_contract", "output_contract",
    "verification_required", "source", "trust_level", "enabled",
}
_SOURCE_FIELDS = {"kind", "uri", "sha256", "license_id"}


class SkillContractError(ValueError):
    """Stable skill manifest validation error."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def validate_skill(skill: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(skill, Mapping):
        raise SkillContractError("SKILL_MUST_BE_OBJECT")
    if set(skill) != _REQUIRED:
        raise SkillContractError("SKILL_SCHEMA_FIELDS_INVALID")
    value = dict(skill)
    if value["schema_version"] != SKILL_SCHEMA_VERSION:
        raise SkillContractError("SKILL_SCHEMA_VERSION_UNSUPPORTED")
    for field, pattern in (("skill_id", _SKILL_ID), ("version", _VERSION)):
        item = value[field]
        if not isinstance(item, str) or not pattern.fullmatch(item):
            raise SkillContractError("SKILL_" + field.upper() + "_INVALID")
    for field, limit in (("name", 160), ("description", 2048),
                         ("input_contract", 128), ("output_contract", 128)):
        item = value[field]
        if not isinstance(item, str) or not item.strip() or len(item) > limit:
            raise SkillContractError("SKILL_" + field.upper() + "_INVALID")
    triggers = value["triggers"]
    if (not isinstance(triggers, list) or not triggers or len(triggers) > 32
            or any(not isinstance(item, str) or not item.strip() or len(item) > 160
                   for item in triggers)
            or len(set(triggers)) != len(triggers)):
        raise SkillContractError("SKILL_TRIGGERS_INVALID")
    caps = value["required_capabilities"]
    if (not isinstance(caps, list) or len(caps) > 32
            or any(not isinstance(item, str) or not _CAPABILITY.fullmatch(item) for item in caps)
            or len(set(caps)) != len(caps)):
        raise SkillContractError("SKILL_CAPABILITIES_INVALID")
    if not isinstance(value["risk_class"], str) or value["risk_class"] not in RISK_CLASSES:
        raise SkillContractError("SKILL_RISK_CLASS_INVALID")
    if type(value["verification_required"]) is not bool or type(value["enabled"]) is not bool:
        raise SkillContractError("SKILL_BOOLEAN_FIELD_INVALID")
    if not isinstance(value["trust_level"], str) or value["trust_level"] not in TRUST_LEVELS:
        raise SkillContractError("SKILL_TRUST_LEVEL_INVALID")
    source = value["source"]
    if not isinstance(source, Mapping) or set(source) != _SOURCE_FIELDS:
        raise SkillContractError("SKILL_SOURCE_INVALID")
    if not isinstance(source["kind"], str) or source["kind"] not in SOURCE_KINDS:
        raise SkillContractError("SKILL_SOURCE_KIND_INVALID")
    if not isinstance(source["uri"], str) or not source["uri"].strip() or len(source["uri"]) > 2048:
        raise SkillContractError("SKILL_SOURCE_URI_INVALID")
    if not isinstance(source["sha256"], str) or not _SHA256.fullmatch(source["sha256"]):
        raise SkillContractError("SKILL_SOURCE_DIGEST_INVALID")
    if not isinstance(source["license_id"], str) or not source["license_id"].strip() or len(source["license_id"]) > 128:
        raise SkillContractError("SKILL_SOURCE_LICENSE_REQUIRED")
    if source["kind"] == "BUILTIN" and not source["uri"].startswith("builtin:"):
        raise SkillContractError("SKILL_BUILTIN_SOURCE_URI_INVALID")
    if source["kind"] == "THIRD_PARTY" and not source["uri"].startswith(("https://", "git+https://")):
        raise SkillContractError("SKILL_THIRD_PARTY_SOURCE_URI_INVALID")
    if value["enabled"] and value["trust_level"] not in {"BUILTIN_VERIFIED", "THIRD_PARTY_REVIEWED"}:
        raise SkillContractError("SKILL_UNTRUSTED_CANNOT_BE_ENABLED")
    if value["enabled"] and value["verification_required"] is not True:
        raise SkillContractError("SKILL_VERIFICATION_MUST_BE_REQUIRED")
    try:
        canonical_json(value, max_bytes=_MAX_MANIFEST_BYTES)
    except ContractError as exc:
        raise SkillContractError("SKILL_RESOURCE_LIMIT") from exc
    return value


def skill_digest(skill: Mapping[str, Any]) -> str:
    return canonical_digest(validate_skill(skill), max_bytes=_MAX_MANIFEST_BYTES)


def skill_dispatchability(skill: Mapping[str, Any], available_capabilities) -> dict[str, Any]:
    """Decide whether metadata is eligible; this is not an execution authorization."""
    value = validate_skill(skill)
    if not isinstance(available_capabilities, (set, frozenset, list, tuple)):
        raise SkillContractError("SKILL_AVAILABLE_CAPABILITIES_INVALID")
    if any(not isinstance(cap, str) for cap in available_capabilities):
        raise SkillContractError("SKILL_AVAILABLE_CAPABILITIES_INVALID")
    missing = sorted(set(value["required_capabilities"]) - set(available_capabilities))
    if not value["enabled"]:
        return {"dispatchable": False, "reason_code": "SKILL_DISABLED", "missing_capabilities": missing}
    if value["trust_level"] not in {"BUILTIN_VERIFIED", "THIRD_PARTY_REVIEWED"}:
        return {"dispatchable": False, "reason_code": "SKILL_TRUST_NOT_ACCEPTED", "missing_capabilities": missing}
    if missing:
        return {"dispatchable": False, "reason_code": "SKILL_CAPABILITY_GAP", "missing_capabilities": missing}
    return {
        "dispatchable": True, "reason_code": "SKILL_METADATA_ELIGIBLE",
        "missing_capabilities": [], "skill_digest": skill_digest(value),
    }
