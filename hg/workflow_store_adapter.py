"""One-task-store workflow adapter for the HG2 P1 closure.

This adapter refuses legacy append-only StateStore and any non-SQLite backend.
SQLiteStateStore owns task events and projections in the same transaction. The adapter
provides health/restart checks but does not migrate or cut over the live PhoneRuntime.
"""
from __future__ import annotations

import hashlib
import os
import re
from typing import Any

from .auth import AuthenticatedPrincipal
from .sqlite_state import SQLiteStateStore
from .task_contract import canonical_json
from .workflow import WorkflowError, WorkflowService, validate_task

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class WorkflowStoreContractError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class CanonicalWorkflowAdapter:
    """Explicit task-store owner wrapping one SQLiteStateStore and WorkflowService."""

    def __init__(self, store: SQLiteStateStore, *, principal: AuthenticatedPrincipal,
                 actor_id: str, clock, owner_id: str = "phone"):
        if not isinstance(store, SQLiteStateStore):
            raise WorkflowStoreContractError("WORKFLOW_STORE_MUST_BE_SQLITE_STATE_STORE")
        if not isinstance(principal, AuthenticatedPrincipal):
            raise WorkflowStoreContractError("WORKFLOW_SEALED_PRINCIPAL_REQUIRED")
        if not isinstance(actor_id, str) or actor_id != principal.principal_id or not actor_id.strip():
            raise WorkflowStoreContractError("WORKFLOW_ACTOR_PRINCIPAL_MISMATCH")
        if not isinstance(owner_id, str) or owner_id != "phone":
            raise WorkflowStoreContractError("WORKFLOW_STATE_OWNER_MUST_BE_PHONE")
        if not callable(clock):
            raise WorkflowStoreContractError("WORKFLOW_CLOCK_REQUIRED")
        verification = store.verify()
        if not isinstance(verification, dict) or verification.get("ok") is not True:
            raise WorkflowStoreContractError("WORKFLOW_STORE_INTEGRITY_NOT_VERIFIED")
        self.store = store
        self.principal = principal
        self.actor_id = actor_id
        self.clock = clock
        self.owner_id = owner_id
        self.service = WorkflowService(store, actor_id=actor_id, clock=clock, principal=principal)

    @property
    def runtime_id(self) -> str:
        return self.store.runtime_id

    def maep_orchestrator(self, *, handlers=None, authorizer=None, evidence_verifier=None):
        """Create MAEP on this canonical SQLite store and sealed principal; never use legacy StateStore."""
        from .maep import MaepOrchestrator

        return MaepOrchestrator(
            self.store,
            principal=self.principal,
            actor_id=self.actor_id,
            handlers=handlers,
            authorizer=authorizer,
            evidence_verifier=evidence_verifier,
            clock=self.clock,
        )

    def create(self, **kwargs) -> dict[str, Any]:
        task = self.service.create(**kwargs)
        return self._confirm_projection(task)

    def transition(self, task_id: str, **kwargs) -> dict[str, Any]:
        task = self.service.transition(task_id, **kwargs)
        return self._confirm_projection(task)

    def get(self, task_id: str) -> dict[str, Any] | None:
        task = self.store.get_task(task_id)
        return None if task is None else validate_task(task)

    def _confirm_projection(self, task: dict[str, Any]) -> dict[str, Any]:
        normalized = validate_task(task)
        persisted = self.store.get_task(normalized["task_id"])
        if persisted != normalized:
            raise WorkflowStoreContractError("WORKFLOW_TASK_PROJECTION_MISMATCH")
        return persisted

    def verify_contract(self) -> dict[str, Any]:
        """Verify store chain + task replay projection equivalence and stable owner identity."""
        verification = self.store.verify()
        if not isinstance(verification, dict) or verification.get("ok") is not True:
            raise WorkflowStoreContractError("WORKFLOW_STORE_INTEGRITY_NOT_VERIFIED")
        events = self.store.replay()
        projected: dict[str, dict[str, Any]] = {}
        for event in events:
            event_type = event.get("event_type")
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            if event_type == "workflow.task.created":
                task = validate_task(payload)
                if task["task_id"] in projected or task["version"] != 1 or task["state"] != "PENDING":
                    raise WorkflowStoreContractError("WORKFLOW_REPLAY_CREATE_CONFLICT")
                projected[task["task_id"]] = task
            elif event_type == "workflow.task.transitioned":
                if set(payload) != {"task", "transition"} or not isinstance(payload.get("task"), dict):
                    raise WorkflowStoreContractError("WORKFLOW_REPLAY_EVENT_SCHEMA_INVALID")
                task = validate_task(payload["task"])
                meta = payload["transition"]
                prior = projected.get(task["task_id"])
                if prior is None:
                    raise WorkflowStoreContractError("WORKFLOW_REPLAY_TRANSITION_WITHOUT_CREATE")
                if not isinstance(meta, dict) or meta.get("from_state") != prior["state"]:
                    raise WorkflowStoreContractError("WORKFLOW_REPLAY_SOURCE_STATE_MISMATCH")
                if task["version"] != prior["version"] + 1 or task["correlation_id"] != prior["correlation_id"]:
                    raise WorkflowStoreContractError("WORKFLOW_REPLAY_VERSION_OR_CORRELATION_MISMATCH")
                projected[task["task_id"]] = task
        exported = self.store.audit_export().get("state", {}).get("tasks")
        if not isinstance(exported, dict) or exported != projected:
            raise WorkflowStoreContractError("WORKFLOW_REPLAY_PROJECTION_MISMATCH")
        for task_id, task in projected.items():
            if self.store.get_task(task_id) != task:
                raise WorkflowStoreContractError("WORKFLOW_TASK_ROW_MISMATCH")
        result = {
            "schema_version": "HG_WORKFLOW_STORE_CONTRACT_V1",
            "ok": True,
            "state_owner_id": self.owner_id,
            "backend": "SQLiteStateStore",
            "runtime_id": self.runtime_id,
            "events": verification.get("events"),
            "tasks": len(projected),
            "head_digest": verification.get("head_digest"),
            "task_projection_digest": hashlib.sha256(canonical_json(projected).encode("utf-8")).hexdigest(),
            "replayed_at": self.clock(),
            "runtime_cutover_performed": False,
        }
        result["contract_digest"] = hashlib.sha256(canonical_json(result).encode("utf-8")).hexdigest()
        return result

    @staticmethod
    def reject_legacy_state_store(store: Any) -> None:
        """Produce a stable and explicit failure for the append-only file store."""
        if not isinstance(store, SQLiteStateStore):
            raise WorkflowStoreContractError("LEGACY_OR_UNKNOWN_STORE_NOT_ACCEPTED")
