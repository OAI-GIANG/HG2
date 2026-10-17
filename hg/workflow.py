"""Pure, deterministic workflow/task state machine for HG2."""
from __future__ import annotations

import math
import re
import time
import uuid
from typing import Any, Mapping

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
TASK_STATES = frozenset({
    "PENDING", "RUNNING", "WAITING_APPROVAL", "SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED"
})
TERMINAL_STATES = frozenset({"SUCCEEDED", "CANCELLED", "EXPIRED"})
_REQUIRED_FIELDS = {
    "task_id", "task_type", "state", "version", "attempt", "max_attempts", "created_at",
    "updated_at", "deadline_at", "input_digest", "correlation_id", "idempotency_key",
    "result_digest", "error_code", "approval_id",
}


class WorkflowError(ValueError):
    """Raised when a task transition violates the workflow contract."""


def _text(value: Any, code: str, max_length: int = 256) -> None:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowError(code)
    if len(value) > max_length:
        raise WorkflowError(code + "_TOO_LONG")


def _time(value: Any, code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise WorkflowError(code)
    return float(value)


def create_task(
    *,
    task_type: str,
    input_digest: str,
    idempotency_key: str,
    now: float | None = None,
    deadline_at: float | None = None,
    max_attempts: int = 3,
    task_id: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    created_at = time.time() if now is None else _time(now, "TASK_TIME_INVALID")
    _text(task_type, "TASK_TYPE_REQUIRED")
    if not isinstance(input_digest, str) or not _DIGEST_RE.fullmatch(input_digest):
        raise WorkflowError("TASK_INPUT_DIGEST_INVALID")
    _text(idempotency_key, "TASK_IDEMPOTENCY_KEY_REQUIRED", 512)
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 20:
        raise WorkflowError("TASK_MAX_ATTEMPTS_INVALID")
    deadline = None if deadline_at is None else _time(deadline_at, "TASK_DEADLINE_INVALID")
    if deadline is not None and deadline <= created_at:
        raise WorkflowError("TASK_DEADLINE_NOT_IN_FUTURE")
    tid = uuid.uuid4().hex if task_id is None else task_id
    cid = uuid.uuid4().hex if correlation_id is None else correlation_id
    _text(tid, "TASK_ID_REQUIRED")
    _text(cid, "TASK_CORRELATION_ID_REQUIRED")
    return {
        "task_id": tid,
        "task_type": task_type,
        "state": "PENDING",
        "version": 1,
        "attempt": 0,
        "max_attempts": max_attempts,
        "created_at": created_at,
        "updated_at": created_at,
        "deadline_at": deadline,
        "input_digest": input_digest,
        "correlation_id": cid,
        "idempotency_key": idempotency_key,
        "result_digest": None,
        "error_code": None,
        "approval_id": None,
    }


def validate_task(task: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(task, Mapping) or set(task) != _REQUIRED_FIELDS:
        raise WorkflowError("TASK_SCHEMA_INVALID")
    result = dict(task)
    for field, code in (
        ("task_id", "TASK_ID_REQUIRED"),
        ("task_type", "TASK_TYPE_REQUIRED"),
        ("correlation_id", "TASK_CORRELATION_ID_REQUIRED"),
        ("idempotency_key", "TASK_IDEMPOTENCY_KEY_REQUIRED"),
    ):
        _text(result[field], code, 512)
    if not isinstance(result["state"], str) or result["state"] not in TASK_STATES:
        raise WorkflowError("TASK_STATE_INVALID")
    if isinstance(result["version"], bool) or not isinstance(result["version"], int) or result["version"] < 1:
        raise WorkflowError("TASK_VERSION_INVALID")
    if isinstance(result["attempt"], bool) or not isinstance(result["attempt"], int) or result["attempt"] < 0:
        raise WorkflowError("TASK_ATTEMPT_INVALID")
    if isinstance(result["max_attempts"], bool) or not isinstance(result["max_attempts"], int) or not 1 <= result["max_attempts"] <= 20:
        raise WorkflowError("TASK_MAX_ATTEMPTS_INVALID")
    if result["attempt"] > result["max_attempts"]:
        raise WorkflowError("TASK_ATTEMPT_LIMIT_EXCEEDED")
    result["created_at"] = _time(result["created_at"], "TASK_CREATED_AT_INVALID")
    result["updated_at"] = _time(result["updated_at"], "TASK_UPDATED_AT_INVALID")
    if result["updated_at"] < result["created_at"]:
        raise WorkflowError("TASK_TIME_REGRESSION")
    if result["deadline_at"] is not None:
        result["deadline_at"] = _time(result["deadline_at"], "TASK_DEADLINE_INVALID")
        if result["deadline_at"] <= result["created_at"]:
            raise WorkflowError("TASK_DEADLINE_INVALID")
    if not isinstance(result["input_digest"], str) or not _DIGEST_RE.fullmatch(result["input_digest"]):
        raise WorkflowError("TASK_INPUT_DIGEST_INVALID")
    for field, code in (("result_digest", "TASK_RESULT_DIGEST_INVALID"),):
        value = result[field]
        if value is not None and (not isinstance(value, str) or not _DIGEST_RE.fullmatch(value)):
            raise WorkflowError(code)
    for field in ("error_code", "approval_id"):
        value = result[field]
        if value is not None:
            _text(value, field.upper() + "_INVALID", 512)
    if result["state"] == "SUCCEEDED" and result["result_digest"] is None:
        raise WorkflowError("TASK_RESULT_REQUIRED")
    if result["state"] == "FAILED" and result["error_code"] is None:
        raise WorkflowError("TASK_ERROR_REQUIRED")
    if result["state"] == "WAITING_APPROVAL" and result["approval_id"] is None:
        raise WorkflowError("TASK_APPROVAL_REQUIRED")
    return result


def transition_task(
    task: Mapping[str, Any],
    *,
    target_state: str,
    actor_id: str,
    now: float,
    reason: str = "",
    result_digest: str | None = None,
    error_code: str | None = None,
    approval_id: str | None = None,
    approval_status: str | None = None,
) -> dict[str, Any]:
    current = validate_task(task)
    _text(actor_id, "TASK_ACTOR_REQUIRED")
    now_value = _time(now, "TASK_TIME_INVALID")
    if now_value < current["updated_at"]:
        raise WorkflowError("TASK_TIME_REGRESSION")
    if not isinstance(reason, str) or len(reason) > 512:
        raise WorkflowError("TASK_REASON_INVALID")
    if not isinstance(target_state, str) or target_state not in TASK_STATES:
        raise WorkflowError("TASK_STATE_INVALID")
    if current["state"] in TERMINAL_STATES:
        raise WorkflowError("TASK_TERMINAL_STATE")
    if current["deadline_at"] is not None and now_value >= current["deadline_at"] and target_state not in ("EXPIRED", "CANCELLED"):
        result = dict(current)
        result.update(state="EXPIRED", version=current["version"] + 1, updated_at=now_value, error_code="TASK_DEADLINE_EXCEEDED")
        return validate_task(result)

    allowed = {
        "PENDING": {"RUNNING", "WAITING_APPROVAL", "CANCELLED", "EXPIRED"},
        "RUNNING": {"SUCCEEDED", "FAILED", "WAITING_APPROVAL", "CANCELLED", "EXPIRED"},
        "WAITING_APPROVAL": {"PENDING", "FAILED", "CANCELLED", "EXPIRED"},
        "FAILED": {"PENDING", "CANCELLED", "EXPIRED"},
    }
    if target_state not in allowed.get(current["state"], set()):
        raise WorkflowError("TASK_TRANSITION_NOT_ALLOWED")
    if current["state"] == "FAILED" and target_state == "PENDING" and current["attempt"] >= current["max_attempts"]:
        raise WorkflowError("TASK_ATTEMPT_LIMIT_EXCEEDED")

    result = dict(current)
    result["state"] = target_state
    result["version"] = current["version"] + 1
    result["updated_at"] = now_value
    if target_state == "PENDING" and current["state"] == "FAILED":
        result["error_code"] = None
    if target_state == "RUNNING":
        if current["attempt"] >= current["max_attempts"]:
            raise WorkflowError("TASK_ATTEMPT_LIMIT_EXCEEDED")
        result["attempt"] = current["attempt"] + 1
        result["error_code"] = None
        result["result_digest"] = None
    elif target_state == "WAITING_APPROVAL":
        _text(approval_id, "TASK_APPROVAL_REQUIRED")
        result["approval_id"] = approval_id
    elif current["state"] == "WAITING_APPROVAL":
        if approval_id != current["approval_id"]:
            raise WorkflowError("TASK_APPROVAL_ID_MISMATCH")
        if target_state == "PENDING" and approval_status != "APPROVED":
            raise WorkflowError("TASK_APPROVAL_NOT_GRANTED")
        if target_state == "FAILED" and approval_status != "DENIED":
            raise WorkflowError("TASK_APPROVAL_NOT_DENIED")
        if target_state == "EXPIRED" and approval_status != "EXPIRED":
            raise WorkflowError("TASK_APPROVAL_NOT_EXPIRED")
        result["approval_id"] = None
    if target_state == "SUCCEEDED":
        if not isinstance(result_digest, str) or not _DIGEST_RE.fullmatch(result_digest):
            raise WorkflowError("TASK_RESULT_DIGEST_INVALID")
        result["result_digest"] = result_digest
        result["error_code"] = None
    if target_state == "FAILED":
        _text(error_code, "TASK_ERROR_REQUIRED", 512)
        result["error_code"] = error_code
        result["result_digest"] = None
    if target_state in ("CANCELLED", "EXPIRED"):
        result["error_code"] = "TASK_CANCELLED" if target_state == "CANCELLED" else "TASK_EXPIRED"
        result["result_digest"] = None
    return validate_task(result)


class WorkflowService:
    """Persist task commands through a transactional store implementing the HG2 state-store port."""

    def __init__(self, store, *, actor_id: str = "local-user", authority_context=None, clock=time.time):
        _text(actor_id, "TASK_ACTOR_REQUIRED")
        self.store = store
        self.actor_id = actor_id
        self.authority_context = authority_context if authority_context is not None else {"principal": actor_id}
        self.clock = clock

    def create(
        self,
        *,
        task_type: str,
        input_digest: str,
        idempotency_key: str,
        deadline_at: float | None = None,
        max_attempts: int = 3,
        task_id: str | None = None,
        correlation_id: str | None = None,
        sync_required: bool = False,
    ) -> dict[str, Any]:
        existing = self.store.get_event_by_idempotency(idempotency_key)
        if existing is not None:
            payload = existing.get("payload")
            if (
                existing.get("event_type") == "workflow.task.created"
                and existing.get("actor_id") == self.actor_id
                and isinstance(payload, dict)
                and payload.get("task_type") == task_type
                and payload.get("input_digest") == input_digest
                and payload.get("idempotency_key") == idempotency_key
            ):
                current = self.store.get_task(payload.get("task_id"))
                if current is not None:
                    return current
            raise WorkflowError("TASK_IDEMPOTENCY_CONFLICT")

        task = create_task(
            task_type=task_type,
            input_digest=input_digest,
            idempotency_key=idempotency_key,
            now=self.clock(),
            deadline_at=deadline_at,
            max_attempts=max_attempts,
            task_id=task_id,
            correlation_id=correlation_id,
        )
        self.store.emit(
            "workflow.task.created",
            task,
            actor_id=self.actor_id,
            authority_context=self.authority_context,
            idempotency_key=idempotency_key,
            sync_required=sync_required,
        )
        return task

    def transition(
        self,
        task_id: str,
        *,
        target_state: str,
        expected_version: int,
        idempotency_key: str | None = None,
        reason: str = "",
        result_digest: str | None = None,
        error_code: str | None = None,
        approval_id: str | None = None,
        approval_status: str | None = None,
        sync_required: bool = False,
    ) -> dict[str, Any]:
        _text(task_id, "TASK_ID_REQUIRED")
        if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 1:
            raise WorkflowError("TASK_VERSION_INVALID")
        transition_key = idempotency_key or "task:" + task_id + ":version:" + str(expected_version + 1)
        existing = self.store.get_event_by_idempotency(transition_key)
        if existing is not None:
            payload = existing.get("payload")
            if (
                existing.get("event_type") == "workflow.task.transitioned"
                and existing.get("actor_id") == self.actor_id
                and isinstance(payload, dict)
                and isinstance(payload.get("task"), dict)
                and payload["task"].get("task_id") == task_id
                and payload["transition"].get("requested_state") == target_state
            ):
                current = self.store.get_task(task_id)
                if current == payload["task"]:
                    return current
            current = self.store.get_task(task_id)
            if current is not None and current["version"] != expected_version:
                raise WorkflowError("TASK_VERSION_CONFLICT")
            raise WorkflowError("TASK_IDEMPOTENCY_CONFLICT")

        current = self.store.get_task(task_id)
        if current is None:
            raise WorkflowError("TASK_NOT_FOUND")
        if current["version"] != expected_version:
            raise WorkflowError("TASK_VERSION_CONFLICT")
        now_value = self.clock()
        updated = transition_task(
            current,
            target_state=target_state,
            actor_id=self.actor_id,
            now=now_value,
            reason=reason,
            result_digest=result_digest,
            error_code=error_code,
            approval_id=approval_id,
            approval_status=approval_status,
        )
        event_payload = {
            "task": updated,
            "transition": {
                "from_state": current["state"],
                "requested_state": target_state,
                "approval_id": approval_id,
                "approval_status": approval_status,
                "reason": reason,
            },
        }
        self.store.emit(
            "workflow.task.transitioned",
            event_payload,
            actor_id=self.actor_id,
            authority_context=self.authority_context,
            causation_id=None,
            idempotency_key=transition_key,
            sync_required=sync_required,
        )
        return updated
