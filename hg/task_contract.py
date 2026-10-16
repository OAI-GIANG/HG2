"""Immutable-by-convention HG Task Contract v1 schema and validation.

This module validates declarations only. It never authorizes or executes tasks.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

SCHEMA_VERSION = "hg.task-contract.v1"
MAX_CONTRACT_BYTES = 256_000
MAX_TASKS = 2_000
MAX_DEPENDENCIES_PER_TASK = 2_000
MAX_ID_LENGTH = 128
MAX_TEXT_LENGTH = 16_384
MAX_JSON_DEPTH = 48
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

TOP_LEVEL_FIELDS = frozenset({
    "schema_version", "task_id", "objective", "scope", "input", "output",
    "acceptance_criteria", "evidence_requirements", "risks", "stop_conditions",
    "next_action", "dependencies", "required_capabilities",
    "authorization_requirement", "created_at", "created_by", "contract_digest",
    "approval_ref",
})
REQUIRED_FIELDS = TOP_LEVEL_FIELDS
OBJECT_FIELDS = {
    "scope": frozenset({"include", "exclude"}),
    "next_action": frozenset({"action_id", "description", "preconditions", "on_blocked"}),
    "authorization_requirement": frozenset({"policy_ref", "action", "approval_required", "scope_ref"}),
}
NESTED_FIELDS = {
    "input": frozenset({"input_id", "description", "source_ref", "required", "validation_rule_refs"}),
    "output": frozenset({"output_id", "media_type", "description", "validation_rule_refs"}),
    "acceptance_criteria": frozenset({"criterion_id", "description", "severity", "oracle_ref", "required"}),
    "evidence_requirements": frozenset({"requirement_id", "evidence_type", "source_policy", "integrity_policy", "required"}),
    "risks": frozenset({"risk_id", "severity", "impact", "mitigation_ref", "residual_risk"}),
    "stop_conditions": frozenset({"condition_id", "predicate_ref", "reason_code", "minimum_status"}),
    "dependencies": frozenset({"dependency_task_id", "required_terminal_status", "dependency_kind"}),
    "required_capabilities": frozenset({"capability_id", "contract_version", "required"}),
}
NESTED_REQUIRED = {
    "input": NESTED_FIELDS["input"],
    "output": NESTED_FIELDS["output"],
    "acceptance_criteria": NESTED_FIELDS["acceptance_criteria"],
    "evidence_requirements": NESTED_FIELDS["evidence_requirements"],
    "risks": NESTED_FIELDS["risks"],
    "stop_conditions": NESTED_FIELDS["stop_conditions"],
    "dependencies": NESTED_FIELDS["dependencies"],
    "required_capabilities": NESTED_FIELDS["required_capabilities"],
}
TERMINAL_STATUSES = frozenset({"PASS", "FAIL", "BLOCKED", "INCONCLUSIVE", "NOT_RUN"})
SEVERITIES = frozenset({"P0", "P1", "P2", "P3", "INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"})
FORBIDDEN_DECLARED_ACTIONS = frozenset({
    "file.read", "file.write", "shell.exec", "network.fetch", "deploy",
    "identity.change", "state.import", "provider.invoke",
})


class ContractError(ValueError):
    """Validation error with a stable machine-readable code."""

    def __init__(self, code: str, path: str = "$", detail: str = "") -> None:
        self.code, self.path, self.detail = code, path, detail
        msg = f"{code} at {path}"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)


def _reject_constant(value: str) -> None:
    raise ContractError("CONTRACT_INVALID_JSON", "$", f"non-standard constant {value}")


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError("CONTRACT_INVALID_JSON", "$", f"duplicate key {key!r}")
        out[key] = value
    return out


def parse_json_strict(raw: str | bytes) -> dict[str, Any]:
    if isinstance(raw, bytes):
        if len(raw) > MAX_CONTRACT_BYTES:
            raise ContractError("CONTRACT_RESOURCE_LIMIT", "$", "contract exceeds byte limit")
        try:
            raw = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ContractError("CONTRACT_INVALID_JSON", "$", "input is not UTF-8") from exc
    elif not isinstance(raw, str):
        raise ContractError("CONTRACT_INVALID_JSON", "$", "expected str or bytes")
    if len(raw.encode("utf-8")) > MAX_CONTRACT_BYTES:
        raise ContractError("CONTRACT_RESOURCE_LIMIT", "$", "contract exceeds byte limit")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs_no_duplicates, parse_constant=_reject_constant)
    except ContractError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ContractError("CONTRACT_INVALID_JSON", "$", str(exc)) from exc
    if type(value) is not dict:
        raise ContractError("CONTRACT_SCHEMA_INVALID", "$", "top-level value must be object")
    _check_depth(value)
    return value


def _check_depth(value: Any, depth: int = 0, path: str = "$") -> None:
    if depth > MAX_JSON_DEPTH:
        raise ContractError("CONTRACT_RESOURCE_LIMIT", path, "maximum nesting depth exceeded")
    if isinstance(value, dict):
        for k, v in value.items():
            _check_depth(v, depth + 1, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _check_depth(v, depth + 1, f"{path}[{i}]")


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ContractError("CONTRACT_CANONICALIZATION_FAILED", "$", str(exc)) from exc


def contract_digest(contract: dict[str, Any]) -> str:
    """Digest of the full contract excluding contract_digest itself."""
    unsigned = dict(contract)
    unsigned.pop("contract_digest", None)
    return hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()


def _require(condition: bool, code: str, path: str, detail: str = "") -> None:
    if not condition:
        raise ContractError(code, path, detail)


def _str(value: Any, path: str, *, nonempty: bool = True, maximum: int = MAX_TEXT_LENGTH) -> str:
    _require(isinstance(value, str), "CONTRACT_SCHEMA_INVALID", path, "expected string")
    _require(len(value) <= maximum, "CONTRACT_RESOURCE_LIMIT", path, "string too long")
    if nonempty:
        _require(bool(value.strip()), "CONTRACT_SCHEMA_INVALID", path, "must not be blank")
    return value


def _id(value: Any, path: str) -> str:
    v = _str(value, path, maximum=MAX_ID_LENGTH)
    _require(ID_RE.fullmatch(v) is not None, "CONTRACT_SCHEMA_INVALID", path, "invalid identifier syntax")
    return v


def _bool(value: Any, path: str) -> bool:
    _require(type(value) is bool, "CONTRACT_SCHEMA_INVALID", path, "expected boolean")
    return value


def _ref(value: Any, path: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    return _str(value, path, maximum=512)


def _string_list(value: Any, path: str, *, nonempty: bool = False) -> list[str]:
    _require(type(value) is list, "CONTRACT_SCHEMA_INVALID", path, "expected array")
    if nonempty:
        _require(bool(value), "CONTRACT_REQUIRED_FIELD_MISSING", path, "array must not be empty")
    _require(len(value) <= MAX_TASKS, "CONTRACT_RESOURCE_LIMIT", path, "too many items")
    seen: set[str] = set()
    result: list[str] = []
    for i, item in enumerate(value):
        s = _str(item, f"{path}[{i}]", maximum=512)
        _require(s not in seen, "CONTRACT_DUPLICATE_ID", f"{path}[{i}]", "duplicate entry")
        seen.add(s)
        result.append(s)
    return result


def _check_object(value: Any, path: str, allowed: frozenset[str], required: frozenset[str]) -> dict[str, Any]:
    _require(type(value) is dict, "CONTRACT_SCHEMA_INVALID", path, "expected object")
    unknown = sorted(set(value) - allowed)
    _require(not unknown, "CONTRACT_SCHEMA_INVALID", path, f"unknown fields: {unknown}")
    missing = sorted(required - set(value))
    _require(not missing, "CONTRACT_REQUIRED_FIELD_MISSING", path, f"missing fields: {missing}")
    return value


def _check_array_objects(contract: dict[str, Any], field: str) -> list[dict[str, Any]]:
    arr = contract[field]
    path = f"$.{field}"
    _require(type(arr) is list, "CONTRACT_SCHEMA_INVALID", path, "expected array")
    _require(len(arr) <= MAX_TASKS, "CONTRACT_RESOURCE_LIMIT", path, "too many items")
    if field in {"acceptance_criteria", "evidence_requirements"}:
        _require(bool(arr), "CONTRACT_REQUIRED_FIELD_MISSING", path, "at least one item is required")
    result: list[dict[str, Any]] = []
    ids: set[str] = set()
    for i, raw in enumerate(arr):
        p = f"{path}[{i}]"
        item = _check_object(raw, p, NESTED_FIELDS[field], NESTED_REQUIRED[field])
        id_key = {
            "input": "input_id", "output": "output_id", "acceptance_criteria": "criterion_id",
            "evidence_requirements": "requirement_id", "risks": "risk_id",
            "stop_conditions": "condition_id", "dependencies": "dependency_task_id",
            "required_capabilities": "capability_id",
        }[field]
        identity = _id(item[id_key], f"{p}.{id_key}")
        if field != "dependencies":
            _require(identity not in ids, "CONTRACT_DUPLICATE_ID", f"{p}.{id_key}", "duplicate identifier")
            ids.add(identity)
        # Validate by declared field name, not by incidental runtime type.
        field_types = {
            "input": {"input_id": "id", "description": "str", "source_ref": "ref",
                      "required": "bool", "validation_rule_refs": "str_list"},
            "output": {"output_id": "id", "media_type": "str", "description": "str",
                       "validation_rule_refs": "str_list"},
            "acceptance_criteria": {"criterion_id": "id", "description": "str", "severity": "str",
                                    "oracle_ref": "ref", "required": "bool"},
            "evidence_requirements": {"requirement_id": "id", "evidence_type": "str",
                                      "source_policy": "str", "integrity_policy": "str", "required": "bool"},
            "risks": {"risk_id": "id", "severity": "str", "impact": "str",
                      "mitigation_ref": "nullable_ref", "residual_risk": "str"},
            "stop_conditions": {"condition_id": "id", "predicate_ref": "ref",
                                "reason_code": "str", "minimum_status": "str"},
            "dependencies": {"dependency_task_id": "id", "required_terminal_status": "str",
                             "dependency_kind": "str"},
            "required_capabilities": {"capability_id": "id", "contract_version": "str", "required": "bool"},
        }[field]
        for k, v in item.items():
            kp = f"{p}.{k}"
            kind = field_types[k]
            if kind == "id":
                pass
            elif kind == "str":
                _str(v, kp)
            elif kind == "ref":
                _ref(v, kp)
            elif kind == "nullable_ref":
                _ref(v, kp, nullable=True)
            elif kind == "bool":
                _bool(v, kp)
            elif kind == "str_list":
                _string_list(v, kp)
            else:
                _require(False, "CONTRACT_SCHEMA_INVALID", kp, "unsupported schema type")
        result.append(item)
    return result


def validate_contract(contract: dict[str, Any], *, check_digest: bool = True) -> dict[str, Any]:
    """Validate contract shape and deterministic metadata; does not authorize execution.

    Returns a shallow copy with no injected defaults. Raises ContractError on any invalidity.
    """
    _require(type(contract) is dict, "CONTRACT_SCHEMA_INVALID", "$", "expected object")
    unknown = sorted(set(contract) - TOP_LEVEL_FIELDS)
    _require(not unknown, "CONTRACT_SCHEMA_INVALID", "$", f"unknown fields: {unknown}")
    missing = sorted(REQUIRED_FIELDS - set(contract))
    _require(not missing, "CONTRACT_REQUIRED_FIELD_MISSING", "$", f"missing fields: {missing}")
    _require(contract["schema_version"] == SCHEMA_VERSION, "CONTRACT_SCHEMA_INVALID", "$.schema_version")
    _id(contract["task_id"], "$.task_id")
    _str(contract["objective"], "$.objective")
    _str(contract["created_by"], "$.created_by", maximum=256)
    try:
        dt = datetime.fromisoformat(_str(contract["created_at"], "$.created_at").replace("Z", "+00:00"))
        _require(dt.tzinfo is not None and dt.utcoffset() is not None, "CONTRACT_SCHEMA_INVALID", "$.created_at", "timezone required")
    except ValueError as exc:
        raise ContractError("CONTRACT_SCHEMA_INVALID", "$.created_at", "invalid RFC3339 timestamp") from exc
    _require(contract["approval_ref"] is None or isinstance(contract["approval_ref"], str),
             "CONTRACT_SCHEMA_INVALID", "$.approval_ref", "expected string or null")
    if contract["approval_ref"] is not None:
        _str(contract["approval_ref"], "$.approval_ref", maximum=512)

    scope = _check_object(contract["scope"], "$.scope", OBJECT_FIELDS["scope"], OBJECT_FIELDS["scope"])
    include = _string_list(scope["include"], "$.scope.include", nonempty=True)
    exclude = _string_list(scope["exclude"], "$.scope.exclude")
    _require(not (set(include) & set(exclude)), "CONTRACT_SCOPE_INVALID", "$.scope", "include/exclude overlap")

    for field in NESTED_FIELDS:
        _check_array_objects(contract, field)

    nxt = _check_object(contract["next_action"], "$.next_action", OBJECT_FIELDS["next_action"], OBJECT_FIELDS["next_action"])
    _id(nxt["action_id"], "$.next_action.action_id")
    _str(nxt["description"], "$.next_action.description")
    _string_list(nxt["preconditions"], "$.next_action.preconditions")
    _str(nxt["on_blocked"], "$.next_action.on_blocked")

    auth = _check_object(contract["authorization_requirement"], "$.authorization_requirement",
                         OBJECT_FIELDS["authorization_requirement"], OBJECT_FIELDS["authorization_requirement"])
    _str(auth["policy_ref"], "$.authorization_requirement.policy_ref", maximum=512)
    action = _str(auth["action"], "$.authorization_requirement.action", maximum=128)
    _bool(auth["approval_required"], "$.authorization_requirement.approval_required")
    _str(auth["scope_ref"], "$.authorization_requirement.scope_ref", maximum=512)
    if action in FORBIDDEN_DECLARED_ACTIONS:
        raise ContractError("AUTHORIZATION_DENIED", "$.authorization_requirement.action", "action explicitly forbidden by current policy")
    if auth["approval_required"]:
        _require(contract["approval_ref"] is not None, "APPROVAL_REQUIRED", "$.approval_ref")

    digest = contract["contract_digest"]
    _require(isinstance(digest, str) and SHA256_RE.fullmatch(digest) is not None,
             "CONTRACT_SCHEMA_INVALID", "$.contract_digest", "expected lower-case SHA-256")
    if check_digest:
        _require(digest == contract_digest(contract), "CONTRACT_DIGEST_MISMATCH", "$.contract_digest")

    return dict(contract)
