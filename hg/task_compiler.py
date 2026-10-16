"""Pure Task Compiler for HG Contract v1.

Compilation is declaration validation and dependency analysis only. It never invokes
providers, performs I/O, resolves capabilities, grants authority, or runs tasks.
"""
from __future__ import annotations

import hashlib
import heapq
from itertools import islice
from typing import Any, Callable, Iterable

from .task_contract import (
    ContractError, MAX_CONTRACT_BYTES, MAX_DEPENDENCIES_PER_TASK, MAX_TASKS, TERMINAL_STATUSES,
    canonical_json, contract_digest, parse_json_strict, validate_contract,
)


class CompileError(ValueError):
    def __init__(self, code: str, path: str = "$", detail: str = "") -> None:
        self.code, self.path, self.detail = code, path, detail
        message = f"{code} at {path}"
        if detail:
            message += f": {detail}"
        super().__init__(message)


def compile_contract(raw: str | bytes | dict[str, Any]) -> dict[str, Any]:
    """Parse/validate one contract and return a deterministic declaration plan.

    AUTHORIZED/RUNNING/PASS is never returned. Missing external capability proof is
    exposed as an unresolved prerequisite, not treated as an allow decision.
    """
    try:
        if isinstance(raw, (str, bytes)):
            contract = parse_json_strict(raw)
        elif type(raw) is dict:
            contract = raw
        else:
            raise ContractError("CONTRACT_SCHEMA_INVALID", "$", "expected JSON string, bytes, or object")
        validate_contract(contract)
    except ContractError as exc:
        raise CompileError(exc.code, exc.path, exc.detail) from exc

    # Capability inventory and approval verification deliberately do not exist in G1.
    unresolved: list[str] = []
    if contract["required_capabilities"]:
        unresolved.append("capability_registry")
    if contract["authorization_requirement"]["authenticated_actor_required"]:
        unresolved.append("actor_authenticator")
    if contract["authorization_requirement"]["approval_required"]:
        unresolved.append("approval_verifier")
    plan_core = {
        "schema_version": "hg.compiled-task-plan.v1",
        "task_id": contract["task_id"],
        "contract_digest": contract_digest(contract),
        "state": "VALIDATED",
        "executable": False,
        "unresolved_prerequisites": unresolved,
        "required_capabilities": sorted(
            (item["capability_id"], item["contract_version"])
            for item in contract["required_capabilities"]
        ),
        "dependency_task_ids": sorted(
            item["dependency_task_id"] for item in contract["dependencies"]
        ),
        "acceptance_criterion_ids": sorted(
            item["criterion_id"] for item in contract["acceptance_criteria"]
        ),
        "evidence_requirement_ids": sorted(
            item["requirement_id"] for item in contract["evidence_requirements"]
        ),
    }
    plan_core["plan_digest"] = hashlib.sha256(canonical_json(plan_core).encode("utf-8")).hexdigest()
    return plan_core


def compile_natural_language(
    request: str,
    *,
    draft_provider: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compile an NL request via an injected, untrusted draft provider.

    The provider must be configured outside the task payload. Its output is treated as
    untrusted data and must pass full Task Contract v1 validation. This function performs
    no network/model call itself and never authorizes or executes the resulting plan.
    """
    if not isinstance(request, str) or not request.strip():
        raise CompileError("TASK_REQUEST_INVALID", "$.request", "request must be nonempty text")
    try:
        encoded = request.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise CompileError("TASK_REQUEST_INVALID", "$.request", "request is not valid Unicode") from exc
    if len(encoded) > MAX_CONTRACT_BYTES:
        raise CompileError("CONTRACT_RESOURCE_LIMIT", "$.request", "request exceeds byte limit")
    if draft_provider is None:
        raise CompileError("TASK_DRAFT_PROVIDER_UNAVAILABLE", "$.draft_provider")
    try:
        proposed_contract = draft_provider(request)
    except Exception as exc:
        safe_code = getattr(exc, "code", type(exc).__name__)
        if not isinstance(safe_code, str) or not safe_code.isascii() or len(safe_code) > 96:
            safe_code = "PROVIDER_ERROR"
        raise CompileError("TASK_DRAFT_PROVIDER_ERROR", "$.draft_provider", safe_code) from None
    try:
        if isinstance(proposed_contract, (str, bytes)):
            validated_contract = parse_json_strict(proposed_contract)
        elif type(proposed_contract) is dict:
            validated_contract = proposed_contract
        else:
            raise CompileError("TASK_DRAFT_INVALID", "$.draft_provider", "expected JSON object")
        validate_contract(validated_contract)
        plan = compile_contract(validated_contract)
    except CompileError:
        raise
    except ContractError as exc:
        raise CompileError(exc.code, exc.path, exc.detail) from None
    except Exception as exc:
        raise CompileError("TASK_DRAFT_INVALID", "$.draft_provider", type(exc).__name__) from None
    plan.pop("plan_digest", None)
    plan["task_contract"] = validated_contract
    plan["source_request_digest"] = hashlib.sha256(encoded).hexdigest()
    plan["draft_provider_state"] = "UNTRUSTED_PROPOSAL_VALIDATED"
    plan["executable"] = False
    plan["plan_digest"] = hashlib.sha256(canonical_json(plan).encode("utf-8")).hexdigest()
    return plan


def compile_task_graph(tasks: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Validate a graph of Task Contract v1 objects and emit stable topological order.

    Every referenced dependency must occur in this input set. Edges are dependency ->
    dependent. This function checks graph structure only; it does not schedule work.
    """
    try:
        iterator = iter(tasks)
        task_list = list(islice(iterator, MAX_TASKS + 1))
    except (TypeError, RuntimeError) as exc:
        raise CompileError("CONTRACT_SCHEMA_INVALID", "$", "tasks must be an iterable") from exc
    if len(task_list) > MAX_TASKS:
        raise CompileError("CONTRACT_RESOURCE_LIMIT", "$", "too many tasks")
    nodes: dict[str, dict[str, Any]] = {}
    for index, contract in enumerate(task_list):
        try:
            validate_contract(contract)
        except ContractError as exc:
            raise CompileError(exc.code, f"$[{index}].{exc.path[2:]}" if exc.path.startswith("$.") else f"$[{index}]", exc.detail) from exc
        task_id = contract["task_id"]
        if task_id in nodes:
            raise CompileError("CONTRACT_DUPLICATE_ID", f"$[{index}].task_id", task_id)
        nodes[task_id] = contract

    if any(len(c["dependencies"]) > MAX_DEPENDENCIES_PER_TASK for c in nodes.values()):
        raise CompileError("CONTRACT_RESOURCE_LIMIT", "$.dependencies", "too many dependency edges for one task")
    max_graph_edges = min(100_000, MAX_TASKS * 10)
    if sum(len(c["dependencies"]) for c in nodes.values()) > max_graph_edges:
        raise CompileError("CONTRACT_RESOURCE_LIMIT", "$.dependencies", "total graph edge limit exceeded")

    predecessors: dict[str, set[str]] = {task_id: set() for task_id in nodes}
    successors: dict[str, set[str]] = {task_id: set() for task_id in nodes}
    for task_id, contract in nodes.items():
        for index, dependency in enumerate(contract["dependencies"]):
            dep_id = dependency["dependency_task_id"]
            path = f"$.tasks[{task_id}].dependencies[{index}]"
            if dep_id not in nodes:
                raise CompileError("DEPENDENCY_UNRESOLVED", path, dep_id)
            if dep_id == task_id:
                raise CompileError("DEPENDENCY_CYCLE", path, f"self-cycle {task_id}")
            predecessors[task_id].add(dep_id)
            successors[dep_id].add(task_id)

    # Kahn with a min-heap establishes a total, stable tie-break independent of input order.
    indegree = {task_id: len(preds) for task_id, preds in predecessors.items()}
    ready = [task_id for task_id, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    ordered: list[str] = []
    while ready:
        current = heapq.heappop(ready)
        ordered.append(current)
        for nxt in sorted(successors[current]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                heapq.heappush(ready, nxt)
    if len(ordered) != len(nodes):
        remaining = sorted(task_id for task_id, degree in indegree.items() if degree > 0)
        raise CompileError("DEPENDENCY_CYCLE", "$.dependencies", f"cycle blocks nodes: {remaining}")

    graph_core = {
        "schema_version": "hg.compiled-task-graph.v1",
        "state": "VALIDATED",
        "executable": False,
        "task_ids": sorted(nodes),
        "topological_order": ordered,
        "edges": sorted([[dep, task_id] for task_id, deps in predecessors.items() for dep in deps]),
    }
    graph_core["graph_digest"] = hashlib.sha256(canonical_json(graph_core).encode("utf-8")).hexdigest()
    return graph_core


def dependency_gate(
    contract: dict[str, Any],
    observed_statuses: dict[str, str],
) -> dict[str, Any]:
    """Pure check against already-observed task statuses; never advances state."""
    validate_contract(contract)
    reasons: list[dict[str, str]] = []
    for dependency in contract["dependencies"]:
        dep_id = dependency["dependency_task_id"]
        expected = dependency["required_terminal_status"]
        actual = observed_statuses.get(dep_id)
        if actual not in TERMINAL_STATUSES:
            reasons.append({"code": "DEPENDENCY_STATUS_NOT_SATISFIED", "dependency_task_id": dep_id,
                            "expected": expected, "actual": actual or "NOT_RUN"})
        elif actual != expected:
            reasons.append({"code": "DEPENDENCY_STATUS_NOT_SATISFIED", "dependency_task_id": dep_id,
                            "expected": expected, "actual": actual})
    return {
        "task_id": contract["task_id"],
        "ready": not reasons,
        "executable": False,
        "state": "VALIDATED" if not reasons else "BLOCKED",
        "reasons": reasons,
    }
