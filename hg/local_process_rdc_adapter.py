"""Explicitly allowlisted local POSIX adapter behind the HG RDC admission gate.

This is a local Android/Termux execution adapter, not a network desktop client.
It dispatches only operation IDs registered by trusted application code.
"""
from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .process_supervisor import PosixProcessSupervisor, ProcessResult, ProcessSupervisorError
from .remote_desktop_commander import (
    RemoteCommandError, RemoteDesktopCommander, RemoteOperation,
)

ArgvBuilder = Callable[[Mapping[str, Any]], Sequence[str]]


@dataclass(frozen=True)
class LocalProcessOperation:
    operation: RemoteOperation
    argv_builder: ArgvBuilder
    timeout_seconds: float


class PosixLocalRdcAdapter:
    """Execute registered local operations only after RDC admission succeeds."""

    def __init__(self, *, target_id: str, adapter_id: str, adapter_version: str,
                 operations: Sequence[LocalProcessOperation],
                 supervisor: PosixProcessSupervisor | None = None):
        if os.name != "posix" or not hasattr(os, "killpg"):
            raise ProcessSupervisorError("PROCESS_SUPERVISOR_POSIX_REQUIRED")
        if not isinstance(target_id, str) or not target_id or len(target_id) > 128:
            raise RemoteCommandError("LOCAL_RDC_TARGET_ID_INVALID")
        if not isinstance(adapter_id, str) or not adapter_id.strip():
            raise RemoteCommandError("LOCAL_RDC_ADAPTER_ID_INVALID")
        if not isinstance(adapter_version, str) or not adapter_version.strip():
            raise RemoteCommandError("LOCAL_RDC_ADAPTER_VERSION_INVALID")
        if not isinstance(operations, (list, tuple)) or not operations:
            raise RemoteCommandError("LOCAL_RDC_OPERATIONS_INVALID")
        self.target_id = target_id
        self.adapter_id = adapter_id
        self.adapter_version = adapter_version
        self._operations: dict[str, LocalProcessOperation] = {}
        for item in operations:
            if not isinstance(item, LocalProcessOperation):
                raise RemoteCommandError("LOCAL_RDC_OPERATION_INVALID")
            op = item.operation
            if op.adapter_id != adapter_id or op.adapter_version != adapter_version:
                raise RemoteCommandError("LOCAL_RDC_OPERATION_ADAPTER_MISMATCH")
            if op.operation_id in self._operations:
                raise RemoteCommandError("LOCAL_RDC_OPERATION_DUPLICATE")
            if not callable(item.argv_builder):
                raise RemoteCommandError("LOCAL_RDC_ARGV_BUILDER_INVALID")
            # Validate timeout before any operation can be dispatched.
            PosixProcessSupervisor._validate_timeout(item.timeout_seconds)
            self._operations[op.operation_id] = item
        self._commander = RemoteDesktopCommander(tuple(item.operation for item in operations))
        self._supervisor = supervisor or PosixProcessSupervisor()

    @staticmethod
    def local_target_fingerprint() -> str:
        """Non-secret descriptive runtime fingerprint; not a cryptographic identity."""
        return f"{platform.system().lower()}-{platform.machine().lower()}"

    def execute(self, command: Mapping[str, Any], *, granted_capabilities,
                approval_verifier=None, allow_destructive: bool = False) -> dict[str, Any]:
        """Admit and run a single allowlisted local operation; never invokes a shell."""
        if not isinstance(command, Mapping):
            raise RemoteCommandError("REMOTE_COMMAND_MUST_BE_OBJECT")
        if command.get("target_id") != self.target_id:
            return {
                "status": "BLOCKED", "reason_code": "LOCAL_RDC_TARGET_MISMATCH",
                "target_id": self.target_id, "result": None,
            }
        operation_id = command.get("operation_id")
        registered = self._operations.get(operation_id) if isinstance(operation_id, str) else None
        if registered is None:
            return {
                "status": "BLOCKED", "reason_code": "LOCAL_RDC_OPERATION_UNREGISTERED",
                "target_id": self.target_id, "result": None,
            }
        decision = self._commander.prepare(
            command, granted_capabilities=granted_capabilities,
            approval_verifier=approval_verifier, dry_run=False,
            allow_destructive=allow_destructive,
        )
        if not decision.get("ok") or decision.get("executable") is not True:
            return {
                "status": "BLOCKED", "reason_code": decision.get("reason_code"),
                "decision": decision, "result": None,
            }
        if (decision.get("adapter_id") != self.adapter_id
                or decision.get("adapter_version") != self.adapter_version):
            return {
                "status": "BLOCKED", "reason_code": "LOCAL_RDC_ADAPTER_BINDING_MISMATCH",
                "decision": decision, "result": None,
            }
        try:
            argv = registered.argv_builder(command["arguments"])
            result = self._supervisor.run(
                argv, timeout_seconds=registered.timeout_seconds,
            )
        except ProcessSupervisorError as exc:
            return {
                "status": "BLOCKED", "reason_code": exc.code,
                "decision": decision, "result": None,
            }
        return {
            "status": "COMPLETED" if result.status == "COMPLETED" else result.status,
            "reason_code": "LOCAL_RDC_PROCESS_" + result.status,
            "target_id": self.target_id,
            "decision": decision,
            "result": {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "elapsed_seconds": result.elapsed_seconds,
                "status": result.status,
            },
        }
