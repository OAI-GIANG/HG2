"""MAEP-2.0 stateful task orchestrator.

The engine sequences stages and checkpoints them through the existing hash-chained
StateStore. It does not grant host capabilities or execute shell commands itself.
A host must inject explicit authorization, evidence-verification, and stage adapters.
Missing adapters fail closed; interrupted in-flight work is never retried blindly.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Callable

from .history import StateStore
from .task_contract import ID_RE, canonical_json

SCHEMA = "hg.maep-checkpoint.v1"
PHASES = (
    ("S0", "INTAKE"),
    ("S1", "ACCESS_AND_BASELINE"),
    ("S2", "RESEARCH"),
    ("S3", "DIAGNOSIS"),
    ("S4", "PLAN"),
    ("S5", "ADVERSARIAL_REVIEW"),
    ("S6", "FINAL_PLAN"),
    ("S7", "CHANGE_PREPARATION"),
    ("S8", "IMPLEMENTATION"),
    ("S9", "TESTING"),
    ("S10", "INTEGRATION"),
    ("S11", "DEPLOYMENT_OR_RUNTIME_VERIFICATION"),
    ("S12", "ACCEPTANCE_AUDIT"),
    ("S13", "CHECKPOINT_AND_CLOSURE"),
)
PHASE_IDS = tuple(item[0] for item in PHASES)
PHASE_NAME = dict(PHASES)
_REQUIRED_INPUTS = (
    "task_id", "OBJECTIVE", "SCOPE", "INPUT", "OUTPUT",
    "ACCEPTANCE_CRITERIA", "EVIDENCE", "RISKS", "STOP_CONDITION",
    "NEXT_ACTION", "CLOSURE_CONDITIONS",
)


class MaepError(ValueError):
    """Stable MAEP orchestration error."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(code + (": " + detail if detail else ""))


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MaepError("MAEP_SCHEMA_INVALID", name + " must be nonempty text")
    return value.strip()


def _refs(value: Any, name: str) -> list[str]:
    if type(value) is not list or not value:
        raise MaepError("MAEP_EVIDENCE_REQUIRED", name)
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise MaepError("MAEP_SCHEMA_INVALID", name + " must contain nonempty evidence IDs")
    if len(value) != len(set(value)):
        raise MaepError("MAEP_SCHEMA_INVALID", name + " contains duplicate evidence IDs")
    return list(value)


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8", errors="strict")).hexdigest()


class MaepOrchestrator:
    """Durable sequential stage controller with injected, fail-closed adapters.

    Handler format: {phase_id: {"action": str, "prepare": read_only_callable, "run": callable}}.
    Authorizer and evidence_verifier return (bool, nonempty_decision_reference).
    prepare() proves ENTRY before dispatch; run() returns EXIT evidence and a result:
    {"status": "COMPLETE"|"BLOCKED"|"NOT_APPLICABLE", "exit_criteria": {...},
    "evidence_ids": [...], "reason": optional text, plus S12 criterion_results or
    S13 closure_checks when applicable.
    """

    def __init__(
        self,
        state_store: StateStore,
        *,
        handlers: dict[str, dict[str, Any]] | None = None,
        authorizer: Callable[[str, dict[str, Any]], tuple[bool, str]] | None = None,
        evidence_verifier: Callable[[list[str], dict[str, Any]], tuple[bool, str]] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.store = state_store
        self.handlers = dict(handlers or {})
        self.authorizer = authorizer
        self.evidence_verifier = evidence_verifier
        self.clock = clock

    def _verified_refs(self, refs: Any, context: dict[str, Any]) -> tuple[list[str], str]:
        ids = _refs(refs, "evidence_ids")
        if self.evidence_verifier is None:
            raise MaepError("EVIDENCE_VERIFIER_UNAVAILABLE")
        try:
            decision = self.evidence_verifier(ids, context)
        except Exception:
            raise MaepError("EVIDENCE_VERIFIER_ERROR") from None
        if (type(decision) is not tuple or len(decision) != 2
                or type(decision[0]) is not bool
                or not isinstance(decision[1], str) or not decision[1].strip()):
            raise MaepError("EVIDENCE_VERIFIER_INVALID_RESPONSE")
        if not decision[0]:
            raise MaepError("EVIDENCE_NOT_VERIFIED", decision[1])
        return ids, decision[1]

    def _save(self, state: dict[str, Any]) -> dict[str, Any]:
        next_state = dict(state)
        next_state["revision"] = int(state["revision"]) + 1
        next_state["CHECKPOINT"] = {
            "revision": next_state["revision"],
            "recorded_at": self.clock(),
            "phase": next_state["CURRENT_STATE"],
            "status": next_state["status"],
        }
        payload_core = dict(next_state)
        payload = {
            "task_id": next_state["task_id"],
            "revision": next_state["revision"],
            "checkpoint": next_state,
            "checkpoint_digest": _digest(payload_core),
        }
        event = self.store.emit(
            "maep.task_checkpoint", payload,
            correlation_id=next_state["task_id"],
            event_id="maep:" + next_state["task_id"] + ":" + str(next_state["revision"]),
        )
        stored = event.get("payload", {})
        if (stored.get("checkpoint_digest") != payload["checkpoint_digest"]
                or stored.get("revision") != next_state["revision"]):
            raise MaepError("MAEP_CHECKPOINT_CONFLICT", next_state["task_id"])
        return next_state

    def create_task(self, task: dict[str, Any]) -> dict[str, Any]:
        if type(task) is not dict:
            raise MaepError("MAEP_SCHEMA_INVALID", "task must be an object")
        missing = [key for key in _REQUIRED_INPUTS if key not in task]
        if missing:
            raise MaepError("MAEP_REQUIRED_FIELD_MISSING", ",".join(missing))
        task_id = _nonempty(task["task_id"], "task_id")
        if not ID_RE.fullmatch(task_id):
            raise MaepError("MAEP_SCHEMA_INVALID", "task_id has invalid identifier syntax")
        if any(e.get("event_type") == "maep.task_checkpoint"
               and e.get("payload", {}).get("task_id") == task_id
               for e in self.store.replay()):
            raise MaepError("MAEP_TASK_ALREADY_EXISTS", task_id)
        repository = task.get("REPOSITORY", "OAI-GIANG/HG2")
        if repository != "OAI-GIANG/HG2":
            raise MaepError("MAEP_SCOPE_VIOLATION", "repository must be OAI-GIANG/HG2")
        objective = _nonempty(task["OBJECTIVE"], "OBJECTIVE")
        next_action = task["NEXT_ACTION"]
        if isinstance(next_action, str):
            next_action = _nonempty(next_action, "NEXT_ACTION")
        elif type(next_action) is dict:
            if not next_action:
                raise MaepError("MAEP_SCHEMA_INVALID", "NEXT_ACTION object must not be empty")
            canonical_json(next_action)
        else:
            raise MaepError("MAEP_SCHEMA_INVALID", "NEXT_ACTION must be text or an object")
        if type(task["ACCEPTANCE_CRITERIA"]) is not list or not task["ACCEPTANCE_CRITERIA"]:
            raise MaepError("MAEP_SCHEMA_INVALID", "ACCEPTANCE_CRITERIA must be nonempty list")
        criteria = []
        seen = set()
        for item in task["ACCEPTANCE_CRITERIA"]:
            if type(item) is not dict:
                raise MaepError("MAEP_SCHEMA_INVALID", "acceptance criterion must be object")
            cid = _nonempty(item.get("id"), "criterion.id")
            if not ID_RE.fullmatch(cid):
                raise MaepError("MAEP_SCHEMA_INVALID", "criterion ID has invalid identifier syntax")
            if cid in seen:
                raise MaepError("MAEP_SCHEMA_INVALID", "duplicate criterion " + cid)
            seen.add(cid)
            if type(item.get("required")) is not bool:
                raise MaepError("MAEP_SCHEMA_INVALID", cid + ".required must be boolean")
            criteria.append({
                "id": cid,
                "description": _nonempty(item.get("description"), cid + ".description"),
                "required": item["required"],
                "verification": _nonempty(item.get("verification"), cid + ".verification"),
                "status": "PENDING",
                "evidence_ids": [],
            })
        if type(task["CLOSURE_CONDITIONS"]) is not list or not task["CLOSURE_CONDITIONS"]:
            raise MaepError("MAEP_SCHEMA_INVALID", "CLOSURE_CONDITIONS must be nonempty list")
        closure = [_nonempty(x, "CLOSURE_CONDITIONS item") for x in task["CLOSURE_CONDITIONS"]]
        if len(closure) != len(set(closure)):
            raise MaepError("MAEP_SCHEMA_INVALID", "duplicate closure condition")
        for key in ("EVIDENCE", "RISKS"):
            if type(task[key]) is not list:
                raise MaepError("MAEP_SCHEMA_INVALID", key + " must be a list")
        initial = {
            "schema": SCHEMA,
            "task_id": task_id,
            "OBJECTIVE": objective,
            "SCOPE": task["SCOPE"],
            "INPUT": task["INPUT"],
            "OUTPUT": task["OUTPUT"],
            "ACCEPTANCE_CRITERIA": criteria,
            "EVIDENCE": task["EVIDENCE"],
            "RISKS": task["RISKS"],
            "STOP_CONDITION": _nonempty(task["STOP_CONDITION"], "STOP_CONDITION"),
            "NEXT_ACTION": next_action,
            "CLOSURE_CONDITIONS": closure,
            "REPOSITORY": task.get("REPOSITORY", "OAI-GIANG/HG2"),
            "BRANCH": task.get("BRANCH", ""),
            "HEAD": task.get("HEAD", ""),
            "WORKING_TREE": task.get("WORKING_TREE", ""),
            "CURRENT_STATE": "S0",
            "status": "IN_PROGRESS",
            "stage_results": {},
            "block": None,
            "revision": 0,
            "CHECKPOINT": {},
            "created_at": self.clock(),
        }
        try:
            canonical_json(initial)
        except (TypeError, ValueError, RecursionError):
            raise MaepError("MAEP_SCHEMA_INVALID", "task fields must be JSON serializable") from None
        return self._save(initial)

    def load_task(self, task_id: str) -> dict[str, Any]:
        _nonempty(task_id, "task_id")
        integrity = self.store.verify()
        if not integrity.get("ok"):
            raise MaepError("MAEP_HISTORY_INTEGRITY_FAILED", str(integrity.get("reason")))
        matches = []
        for event in self.store.replay():
            if event.get("event_type") != "maep.task_checkpoint":
                continue
            payload = event.get("payload", {})
            if payload.get("task_id") != task_id:
                continue
            checkpoint = payload.get("checkpoint")
            if type(checkpoint) is not dict or _digest(checkpoint) != payload.get("checkpoint_digest"):
                raise MaepError("MAEP_CHECKPOINT_DIGEST_MISMATCH", task_id)
            if payload.get("revision") != checkpoint.get("revision"):
                raise MaepError("MAEP_CHECKPOINT_REVISION_MISMATCH", task_id)
            if (checkpoint.get("schema") != SCHEMA
                    or checkpoint.get("CURRENT_STATE") not in PHASE_IDS
                    or checkpoint.get("status") not in {"IN_PROGRESS", "BLOCKED", "CLOSED_VERIFIED"}
                    or type(checkpoint.get("revision")) is not int
                    or checkpoint["revision"] < 1
                    or type(checkpoint.get("CHECKPOINT")) is not dict
                    or checkpoint["CHECKPOINT"].get("revision") != checkpoint["revision"]
                    or checkpoint["CHECKPOINT"].get("phase") != checkpoint["CURRENT_STATE"]
                    or checkpoint["CHECKPOINT"].get("status") != checkpoint["status"]):
                raise MaepError("MAEP_CHECKPOINT_SCHEMA_INVALID", task_id)
            matches.append(checkpoint)
        if not matches:
            raise MaepError("MAEP_TASK_NOT_FOUND", task_id)
        matches.sort(key=lambda item: item["revision"])
        revisions = [item["revision"] for item in matches]
        if revisions != list(range(1, len(revisions) + 1)):
            raise MaepError("MAEP_CHECKPOINT_REVISION_GAP", task_id)
        return dict(matches[-1])

    def _block(self, state: dict[str, Any], code: str, detail: str = "") -> dict[str, Any]:
        updated = dict(state)
        updated["status"] = "BLOCKED"
        updated["block"] = {"code": code, "detail": detail, "phase": state["CURRENT_STATE"]}
        updated["NEXT_ACTION"] = "Resolve " + code + " for " + state["CURRENT_STATE"] + " before continuing."
        return self._save(updated)

    def _validate_closure(self, state: dict[str, Any], result: dict[str, Any],
                          evidence_context: dict[str, Any]) -> tuple[bool, str]:
        prior = state["stage_results"]
        for phase_id in PHASE_IDS[:-1]:
            if prior.get(phase_id, {}).get("status") not in {"COMPLETE", "NOT_APPLICABLE"}:
                return False, "REQUIRED_PHASE_INCOMPLETE:" + phase_id
        criterion_results = prior.get("S12", {}).get("criterion_results")
        if type(criterion_results) is not dict:
            return False, "ACCEPTANCE_RESULTS_MISSING"
        expected_ids = {item["id"] for item in state["ACCEPTANCE_CRITERIA"]}
        if set(criterion_results) != expected_ids:
            return False, "ACCEPTANCE_RESULT_SET_MISMATCH"
        allowed_statuses = {"PASS", "FAIL", "INCONCLUSIVE", "NOT_APPLICABLE"}
        for criterion in state["ACCEPTANCE_CRITERIA"]:
            observed = criterion_results.get(criterion["id"])
            if type(observed) is not dict or observed.get("status") not in allowed_statuses:
                return False, "ACCEPTANCE_RESULT_INVALID:" + criterion["id"]
            if criterion["required"] and observed["status"] != "PASS":
                return False, "REQUIRED_CRITERION_NOT_PASS:" + criterion["id"]
            criterion["status"] = observed["status"]
            criterion["evidence_ids"] = []
            if observed["status"] == "PASS":
                try:
                    ids, verification_ref = self._verified_refs(observed.get("evidence_ids"), {
                        **evidence_context, "criterion_id": criterion["id"]
                    })
                except MaepError as exc:
                    return False, exc.code + ":" + criterion["id"]
                observed["evidence_ids"] = ids
                observed["verification_ref"] = verification_ref
                criterion["evidence_ids"] = ids
        closure_checks = result.get("closure_checks")
        if type(closure_checks) is not dict:
            return False, "CLOSURE_CHECKS_MISSING"
        if set(closure_checks) != set(state["CLOSURE_CONDITIONS"]):
            return False, "CLOSURE_CHECK_SET_MISMATCH"
        for condition in state["CLOSURE_CONDITIONS"]:
            check = closure_checks.get(condition)
            if type(check) is not dict or check.get("passed") is not True:
                return False, "CLOSURE_CONDITION_NOT_MET:" + condition
            try:
                ids, verification_ref = self._verified_refs(check.get("evidence_ids"), {
                    **evidence_context, "closure_condition": condition
                })
            except MaepError as exc:
                return False, exc.code + ":" + condition
            check["evidence_ids"] = ids
            check["verification_ref"] = verification_ref
        return True, "CLOSURE_GATE_PASS"

    def run_next(self, task_id: str) -> dict[str, Any]:
        state = self.load_task(task_id)
        if state["status"] != "IN_PROGRESS":
            return state
        phase_id = state["CURRENT_STATE"]
        previous = state["stage_results"].get(phase_id)
        if previous and previous.get("status") == "RUNNING":
            return self._block(state, "INTERRUPTED_IN_FLIGHT_REQUIRES_RECONCILIATION")
        spec = self.handlers.get(phase_id)
        if (type(spec) is not dict or not callable(spec.get("prepare"))
                or not callable(spec.get("run")) or not isinstance(spec.get("action"), str)):
            return self._block(state, "STAGE_HANDLER_UNAVAILABLE")
        if self.authorizer is None:
            return self._block(state, "ACTION_AUTHORIZER_UNAVAILABLE")
        context = {
            "task_id": task_id,
            "phase_id": phase_id,
            "phase_name": PHASE_NAME[phase_id],
            "idempotency_key": task_id + ":" + phase_id,
            "repository": state["REPOSITORY"],
            "branch": state["BRANCH"],
            "head": state["HEAD"],
            "scope": state["SCOPE"],
            "checkpoint_revision": state["revision"],
        }
        try:
            decision = self.authorizer(spec["action"], context)
        except Exception:
            return self._block(state, "ACTION_AUTHORIZER_ERROR")
        if (type(decision) is not tuple or len(decision) != 2
                or type(decision[0]) is not bool
                or not isinstance(decision[1], str) or not decision[1].strip()):
            return self._block(state, "ACTION_AUTHORIZER_INVALID_RESPONSE")
        if not decision[0]:
            return self._block(state, "ACTION_NOT_AUTHORIZED", decision[1])
        try:
            entry = spec["prepare"](dict(state), dict(context))
        except Exception:
            return self._block(state, "ENTRY_CHECK_ERROR")
        if type(entry) is not dict or entry.get("passed") is not True:
            return self._block(state, "ENTRY_GATE_NOT_PASSED")
        try:
            entry_ids, entry_ref = self._verified_refs(entry.get("evidence_ids"), {
                **context, "gate": "entry",
            })
        except MaepError as exc:
            return self._block(state, "ENTRY_EVIDENCE_UNVERIFIED", exc.code)
        running = dict(state)
        running["stage_results"] = dict(state["stage_results"])
        running["stage_results"][phase_id] = {
            "status": "RUNNING", "action": spec["action"],
            "authorization_ref": decision[1], "started_at": self.clock(),
            "idempotency_key": context["idempotency_key"],
            "entry_gate": {"passed": True, "evidence_ids": entry_ids,
                           "verification_ref": entry_ref},
        }
        running["block"] = None
        state = self._save(running)
        try:
            result = spec["run"](dict(state), dict(context))
        except Exception as exc:
            failed = dict(state)
            failed["stage_results"] = dict(state["stage_results"])
            failed["stage_results"][phase_id] = {
                **state["stage_results"][phase_id],
                "status": "IN_DOUBT",
                "reason": "HANDLER_EXCEPTION_REQUIRES_RECONCILIATION",
                "error_type": type(exc).__name__,
            }
            failed["status"] = "BLOCKED"
            failed["block"] = {"code": "HANDLER_EXCEPTION_REQUIRES_RECONCILIATION", "phase": phase_id}
            failed["NEXT_ACTION"] = "Reconcile side effects for " + phase_id + " before any retry."
            return self._save(failed)
        if type(result) is not dict or result.get("status") not in {"COMPLETE", "BLOCKED", "NOT_APPLICABLE"}:
            uncertain = dict(state)
            uncertain["stage_results"] = dict(state["stage_results"])
            uncertain["stage_results"][phase_id] = {
                **state["stage_results"][phase_id], "status": "IN_DOUBT",
                "reason": "HANDLER_RESULT_INVALID",
            }
            uncertain["status"] = "BLOCKED"
            uncertain["block"] = {"code": "HANDLER_RESULT_INVALID", "phase": phase_id}
            return self._save(uncertain)
        status = result["status"]
        if status == "BLOCKED":
            blocked = dict(state)
            blocked["stage_results"] = dict(state["stage_results"])
            blocked["stage_results"][phase_id] = {
                **state["stage_results"][phase_id], "status": "BLOCKED",
                "reason": str(result.get("reason", "HANDLER_BLOCKED")),
                "side_effect_state": result.get("side_effect_state", "UNKNOWN"),
            }
            blocked["status"] = "BLOCKED"
            blocked["block"] = {"code": "STAGE_HANDLER_BLOCKED", "phase": phase_id}
            return self._save(blocked)
        if phase_id == "S13" and status != "COMPLETE":
            return self._block(state, "CLOSURE_PHASE_CANNOT_BE_SKIPPED", phase_id)
        gate_results = {}
        for gate_name in ("exit_criteria",):
            gate = result.get(gate_name)
            if type(gate) is not dict or gate.get("passed") is not True:
                uncertain = dict(state)
                uncertain["stage_results"] = dict(state["stage_results"])
                uncertain["stage_results"][phase_id] = {
                    **state["stage_results"][phase_id], "status": "IN_DOUBT",
                    "reason": gate_name.upper() + "_GATE_NOT_PROVEN",
                }
                uncertain["status"] = "BLOCKED"
                uncertain["block"] = {"code": gate_name.upper() + "_GATE_NOT_PROVEN", "phase": phase_id}
                uncertain["NEXT_ACTION"] = "Reconcile the stage action and collect verifiable gate evidence before retrying."
                return self._save(uncertain)
            try:
                gate_ids, gate_ref = self._verified_refs(gate.get("evidence_ids"), {
                    **context, "gate": gate_name,
                })
            except MaepError as exc:
                uncertain = dict(state)
                uncertain["stage_results"] = dict(state["stage_results"])
                uncertain["stage_results"][phase_id] = {
                    **state["stage_results"][phase_id], "status": "IN_DOUBT",
                    "reason": gate_name.upper() + ":" + exc.code,
                }
                uncertain["status"] = "BLOCKED"
                uncertain["block"] = {"code": gate_name.upper() + "_EVIDENCE_UNVERIFIED", "phase": phase_id}
                uncertain["NEXT_ACTION"] = "Reconcile the stage action and collect verifiable gate evidence before retrying."
                return self._save(uncertain)
            gate_results[gate_name] = {
                "passed": True, "evidence_ids": gate_ids,
                "verification_ref": gate_ref,
            }
        try:
            refs, evidence_ref = self._verified_refs(result.get("evidence_ids"), context)
        except MaepError as exc:
            uncertain = dict(state)
            uncertain["stage_results"] = dict(state["stage_results"])
            uncertain["stage_results"][phase_id] = {
                **state["stage_results"][phase_id], "status": "IN_DOUBT",
                "reason": exc.code,
            }
            uncertain["status"] = "BLOCKED"
            uncertain["block"] = {"code": exc.code, "phase": phase_id}
            uncertain["NEXT_ACTION"] = "Reconcile the completed action and its evidence before retrying."
            return self._save(uncertain)
        stage_result = {
            **state["stage_results"][phase_id],
            "status": status,
            "entry_gate": state["stage_results"][phase_id]["entry_gate"],
            "exit_gate": gate_results["exit_criteria"],
            "evidence_ids": refs,
            "evidence_verification_ref": evidence_ref,
            "finished_at": self.clock(),
            "reason": str(result.get("reason", "")),
        }
        if status == "NOT_APPLICABLE" and not stage_result["reason"].strip():
            return self._block(state, "NOT_APPLICABLE_REASON_REQUIRED", phase_id)
        if phase_id == "S12":
            cr = result.get("criterion_results")
            if type(cr) is not dict:
                return self._block(state, "ACCEPTANCE_RESULTS_MISSING", phase_id)
            stage_result["criterion_results"] = cr
        if phase_id == "S13":
            candidate = dict(state)
            candidate["stage_results"] = dict(state["stage_results"])
            candidate["stage_results"][phase_id] = stage_result
            ok, reason = self._validate_closure(candidate, result, context)
            if not ok:
                return self._block(state, "CLOSURE_GATE_FAILED", reason)
            candidate["status"] = "CLOSED_VERIFIED"
            candidate["CURRENT_STATE"] = "S13"
            stage_result["closure_checks"] = result["closure_checks"]
            candidate["stage_results"][phase_id] = stage_result
            candidate["block"] = None
            candidate["NEXT_ACTION"] = "No further action; task is CLOSED_VERIFIED."
            return self._save(candidate)
        updated = dict(state)
        updated["stage_results"] = dict(state["stage_results"])
        updated["stage_results"][phase_id] = stage_result
        index = PHASE_IDS.index(phase_id)
        updated["CURRENT_STATE"] = PHASE_IDS[index + 1]
        updated["NEXT_ACTION"] = "Execute " + updated["CURRENT_STATE"] + " " + PHASE_NAME[updated["CURRENT_STATE"]]
        updated["block"] = None
        return self._save(updated)

    def run_until_blocked(self, task_id: str, *, max_steps: int = len(PHASES)) -> dict[str, Any]:
        if type(max_steps) is not int or not 1 <= max_steps <= len(PHASES):
            raise MaepError("MAEP_INVALID_STEP_LIMIT")
        state = self.load_task(task_id)
        for _ in range(max_steps):
            if state["status"] != "IN_PROGRESS":
                break
            before = (state["CURRENT_STATE"], state["revision"])
            state = self.run_next(task_id)
            if state["status"] != "IN_PROGRESS":
                break
            if state["CURRENT_STATE"] == before[0] and state["revision"] > before[1]:
                break
        return state

    def reconcile_interrupted(
        self, task_id: str, *, side_effect_state: str, reason: str,
        evidence_ids: list[str],
    ) -> dict[str, Any]:
        state = self.load_task(task_id)
        if state["status"] != "BLOCKED":
            raise MaepError("MAEP_TASK_NOT_BLOCKED")
        if side_effect_state != "NOT_PERFORMED":
            raise MaepError("MAEP_RECONCILIATION_REQUIRED",
                            "only NOT_PERFORMED permits retry; completed/unknown side effects need a separate verified resolution")
        _nonempty(reason, "reconciliation reason")
        phase_id = state["CURRENT_STATE"]
        reconciliation_history = list(state.get("reconciliation_history", []))
        if sum(1 for item in reconciliation_history if item.get("phase") == phase_id) >= 3:
            raise MaepError("MAEP_RECONCILIATION_LIMIT", phase_id)
        refs, verification_ref = self._verified_refs(evidence_ids, {
            "task_id": task_id, "phase_id": phase_id, "reconciliation": True
        })
        updated = dict(state)
        updated["status"] = "IN_PROGRESS"
        updated["block"] = None
        updated["stage_results"] = dict(state["stage_results"])
        updated["stage_results"].pop(phase_id, None)
        updated["NEXT_ACTION"] = "Retry " + phase_id + " after verified reconciliation."
        updated["reconciliation_history"] = reconciliation_history + [{
            "phase": phase_id, "side_effect_state": side_effect_state,
            "reason": reason, "evidence_ids": refs,
            "verification_ref": verification_ref, "recorded_at": self.clock(),
        }]
        return self._save(updated)
