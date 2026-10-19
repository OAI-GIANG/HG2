"""HG-native remote desktop command contracts and fail-closed admission policy.

This module defines an adapter boundary, not a general-purpose shell executor.
Operations must be explicitly registered by a trusted local adapter.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from .contracts import ContractError, canonical_digest, canonical_json

REMOTE_COMMAND_SCHEMA = "HG_REMOTE_DESKTOP_COMMAND_V1"
REMOTE_DECISION_SCHEMA = "HG_REMOTE_DESKTOP_DECISION_V1"
_RISK_CLASSES = frozenset({
    "LOCAL_READ_ONLY", "LOCAL_WRITE", "OUTBOUND_PROVIDER_CALL",
    "EXTERNAL_WRITE", "DESTRUCTIVE",
})
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]{0,127}$")
_CAP = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_NEVER_RAW_SHELL_OPS = frozenset({
    "shell.exec", "shell.execute", "raw_shell", "shell_command",
    "terminal.exec", "process.exec", "powershell.exec", "bash.exec",
})
_FORBIDDEN_ARGUMENT_KEYS = frozenset({
    "shell", "exec", "command", "cmd", "script", "shellcommand",
    "commandline", "powershell", "bash", "rawshell",
})
_SECRET_KEY_PARTS = (
    "password", "passwd", "secret", "clientsecret", "credential", "token",
    "apikey", "accesskey", "privatekey", "authorization", "bearer",
)
_HIGH_RISK = frozenset({"LOCAL_WRITE", "OUTBOUND_PROVIDER_CALL", "EXTERNAL_WRITE", "DESTRUCTIVE"})


class RemoteCommandError(ValueError):
    """Stable command-envelope or admission rejection."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class RemoteOperation:
    operation_id: str
    required_capabilities: tuple[str, ...]
    risk_class: str
    adapter_id: str
    adapter_version: str


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str):
                return True
            normalized = "".join(ch.lower() for ch in key if ch.isalnum())
            if normalized in _FORBIDDEN_ARGUMENT_KEYS or any(part in normalized for part in _SECRET_KEY_PARTS):
                return True
            if _contains_forbidden_key(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def validate_remote_command(command: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an exact versioned request; no operation is run here."""
    required = {
        "schema_version", "command_id", "request_id", "target_id", "operation_id",
        "arguments", "required_capabilities", "risk_class", "idempotency_key",
        "source_revision", "approval_ref",
    }
    if not isinstance(command, Mapping):
        raise RemoteCommandError("REMOTE_COMMAND_MUST_BE_OBJECT")
    if set(command) != required:
        raise RemoteCommandError("REMOTE_COMMAND_SCHEMA_INVALID")
    value = dict(command)
    if value["schema_version"] != REMOTE_COMMAND_SCHEMA:
        raise RemoteCommandError("REMOTE_COMMAND_VERSION_UNSUPPORTED")
    for field_name in ("command_id", "request_id", "target_id", "operation_id", "idempotency_key"):
        item = value[field_name]
        max_len = 512 if field_name == "idempotency_key" else 128
        if not isinstance(item, str) or not item.strip() or len(item) > max_len:
            raise RemoteCommandError("REMOTE_COMMAND_" + field_name.upper() + "_INVALID")
        if field_name != "idempotency_key" and not _ID.fullmatch(item):
            raise RemoteCommandError("REMOTE_COMMAND_" + field_name.upper() + "_INVALID")
    if value["operation_id"].lower() in _NEVER_RAW_SHELL_OPS:
        raise RemoteCommandError("REMOTE_RAW_SHELL_OPERATION_FORBIDDEN")
    if not isinstance(value["source_revision"], str) or not _SHA.fullmatch(value["source_revision"]):
        raise RemoteCommandError("REMOTE_COMMAND_SOURCE_REVISION_INVALID")
    if not isinstance(value["risk_class"], str) or value["risk_class"] not in _RISK_CLASSES:
        raise RemoteCommandError("REMOTE_COMMAND_RISK_CLASS_INVALID")
    caps = value["required_capabilities"]
    if not isinstance(caps, list) or not caps or len(caps) > 32:
        raise RemoteCommandError("REMOTE_COMMAND_CAPABILITIES_INVALID")
    if any(not isinstance(cap, str) or not _CAP.fullmatch(cap) for cap in caps):
        raise RemoteCommandError("REMOTE_COMMAND_CAPABILITIES_INVALID")
    if len(set(caps)) != len(caps):
        raise RemoteCommandError("REMOTE_COMMAND_CAPABILITY_DUPLICATE")
    if not isinstance(value["arguments"], dict):
        raise RemoteCommandError("REMOTE_COMMAND_ARGUMENTS_INVALID")
    if _contains_forbidden_key(value["arguments"]):
        raise RemoteCommandError("REMOTE_COMMAND_SECRET_OR_RAW_SHELL_FIELD_FORBIDDEN")
    if value["approval_ref"] is not None and (
        not isinstance(value["approval_ref"], str) or not value["approval_ref"].strip()
        or len(value["approval_ref"]) > 256
    ):
        raise RemoteCommandError("REMOTE_COMMAND_APPROVAL_REF_INVALID")
    try:
        canonical_json(value, max_bytes=64 * 1024)
    except ContractError as exc:
        raise RemoteCommandError("REMOTE_COMMAND_RESOURCE_LIMIT") from exc
    return value


class RemoteDesktopCommander:
    """Capability-bound command dispatcher front door.

    Registered adapters remain the only place allowed to cause effects. This gate
    emits a decision and envelope digest; it never shells out, connects remotely,
    reads a target filesystem, or silently executes a dry run.
    """

    def __init__(self, operations=()):
        self._operations: dict[str, RemoteOperation] = {}
        if not isinstance(operations, (tuple, list)):
            raise RemoteCommandError("REMOTE_OPERATION_LIST_INVALID")
        for operation in operations:
            self.register_operation(operation)

    def register_operation(self, operation: RemoteOperation) -> None:
        if not isinstance(operation, RemoteOperation):
            raise RemoteCommandError("REMOTE_OPERATION_INVALID")
        if (not isinstance(operation.operation_id, str) or not _ID.fullmatch(operation.operation_id)
                or operation.operation_id.lower() in _NEVER_RAW_SHELL_OPS):
            raise RemoteCommandError("REMOTE_OPERATION_ID_INVALID")
        if operation.operation_id in self._operations:
            raise RemoteCommandError("REMOTE_OPERATION_DUPLICATE")
        if not isinstance(operation.required_capabilities, tuple) or not operation.required_capabilities:
            raise RemoteCommandError("REMOTE_OPERATION_CAPABILITIES_INVALID")
        if (any(not isinstance(cap, str) or not _CAP.fullmatch(cap)
                for cap in operation.required_capabilities)
                or len(set(operation.required_capabilities)) != len(operation.required_capabilities)):
            raise RemoteCommandError("REMOTE_OPERATION_CAPABILITIES_INVALID")
        if not isinstance(operation.risk_class, str) or operation.risk_class not in _RISK_CLASSES:
            raise RemoteCommandError("REMOTE_OPERATION_RISK_CLASS_INVALID")
        for field_name in ("adapter_id", "adapter_version"):
            item = getattr(operation, field_name)
            if not isinstance(item, str) or not item.strip() or len(item) > 128:
                raise RemoteCommandError("REMOTE_OPERATION_METADATA_INVALID")
        self._operations[operation.operation_id] = operation

    def prepare(self, command: Mapping[str, Any], *, granted_capabilities,
                approval_verifier=None, dry_run: bool = True,
                allow_destructive: bool = False) -> dict[str, Any]:
        """Return a redacted deterministic decision; never dispatch the operation.

        High-risk approval must be verified by a trusted policy adapter against the
        exact request digest, principal, target, operation, and approval reference.
        A caller-supplied boolean or a non-empty approval string is never sufficient.
        """
        value = validate_remote_command(command)
        if type(dry_run) is not bool or type(allow_destructive) is not bool:
            raise RemoteCommandError("REMOTE_COMMAND_POLICY_FLAGS_INVALID")
        operation = self._operations.get(value["operation_id"])
        if operation is None:
            return self._decision(value, ok=False, executable=False,
                                  reason="REMOTE_OPERATION_UNREGISTERED", dry_run=dry_run)
        if (tuple(value["required_capabilities"]) != operation.required_capabilities
                or value["risk_class"] != operation.risk_class):
            return self._decision(value, ok=False, executable=False,
                                  reason="REMOTE_OPERATION_CONTRACT_MISMATCH", dry_run=dry_run)
        if not isinstance(granted_capabilities, (set, frozenset, tuple, list)) or any(
            not isinstance(cap, str) for cap in granted_capabilities
        ):
            raise RemoteCommandError("REMOTE_GRANTED_CAPABILITIES_INVALID")
        if not set(operation.required_capabilities).issubset(set(granted_capabilities)):
            return self._decision(value, ok=False, executable=False,
                                  reason="REMOTE_CAPABILITY_NOT_GRANTED", dry_run=dry_run)
        if operation.risk_class == "DESTRUCTIVE" and not allow_destructive:
            return self._decision(value, ok=False, executable=False,
                                  reason="REMOTE_DESTRUCTIVE_ACTION_DISABLED", dry_run=dry_run)
        if operation.risk_class in _HIGH_RISK:
            if not isinstance(value["approval_ref"], str) or not callable(approval_verifier):
                return self._decision(
                    value, ok=False, executable=False,
                    reason="REMOTE_APPROVAL_REQUIRED", dry_run=dry_run,
                )
            statement = {
                "schema_version": "HG_REMOTE_APPROVAL_REQUEST_V1",
                "approval_ref": value["approval_ref"],
                "command_id": value["command_id"],
                "request_id": value["request_id"],
                "target_id": value["target_id"],
                "operation_id": value["operation_id"],
                "risk_class": value["risk_class"],
                "source_revision": value["source_revision"],
                "idempotency_key": value["idempotency_key"],
                "arguments_sha256": canonical_digest(value["arguments"]),
                "command_sha256": canonical_digest(value),
            }
            try:
                approval_verified = approval_verifier(MappingProxyType(statement)) is True
            except Exception:
                approval_verified = False
            if not approval_verified:
                return self._decision(
                    value, ok=False, executable=False,
                    reason="REMOTE_APPROVAL_UNVERIFIED", dry_run=dry_run,
                )
        if dry_run:
            return self._decision(value, ok=True, executable=False,
                                  reason="REMOTE_DRY_RUN_VALIDATED", dry_run=True)
        return self._decision(value, ok=True, executable=True,
                              reason="REMOTE_COMMAND_ADMITTED_TO_ADAPTER", dry_run=False)

    @staticmethod
    def _decision(command: Mapping[str, Any], *, ok: bool, executable: bool,
                  reason: str, dry_run: bool) -> dict[str, Any]:
        envelope = {
            "schema_version": REMOTE_DECISION_SCHEMA,
            "command_id": command["command_id"],
            "request_id": command["request_id"],
            "target_id": command["target_id"],
            "operation_id": command["operation_id"],
            "source_revision": command["source_revision"],
            "risk_class": command["risk_class"],
            "ok": ok,
            "executable": executable,
            "dry_run": dry_run,
            "reason_code": reason,
            "argument_sha256": canonical_digest(command["arguments"]),
            "required_capabilities": list(command["required_capabilities"]),
        }
        envelope["decision_digest"] = canonical_digest(envelope)
        return envelope
