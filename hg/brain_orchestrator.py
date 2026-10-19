"""HG's single-authority, capability-gated logical-branch orchestrator.

This module only coordinates explicit worker adapters. It does not create branch
processes, grant authority, execute arbitrary tools, or persist workflow state.
All workers are injected and treated as untrusted result producers.
"""
from __future__ import annotations

import hashlib
import math
import re
import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .contracts import (
    CAPABILITY_RESULT_V1,
    ContractError,
    canonical_digest,
    validate_brain_request,
    validate_capability_result,
)

# Logical capability ownership, not Git branches or separate command authorities.
BRANCH_CAPABILITIES: dict[str, frozenset[str]] = {
    "memory_knowledge": frozenset({"memory.search", "memory.recall", "provenance.inspect"}),
    "research_synthesis": frozenset({"research.analyze", "synthesis.propose", "source.compare"}),
    "planning_coordination": frozenset({"task.decompose", "dependency.plan"}),
    "tools_execution": frozenset({"tool.execute", "artifact.build"}),
    "security_verification": frozenset({"policy.check", "evidence.verify", "conflict.review"}),
}
BRANCH_ORDER = tuple(BRANCH_CAPABILITIES)
_CAPABILITY_OWNER = {
    capability: branch
    for branch, capabilities in BRANCH_CAPABILITIES.items()
    for capability in capabilities
}
_CAPABILITY_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_MAX_CAPABILITIES = 32
_MAX_BRANCHES = 5
_MAX_STEPS = 100
_MAX_DEADLINE_SECONDS = 3600.0


class BrainRoutingError(ValueError):
    """Stable fail-closed orchestration error."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _capability_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > _MAX_CAPABILITIES:
        raise BrainRoutingError("REQUIRED_CAPABILITIES_INVALID")
    if any(not isinstance(item, str) or not _CAPABILITY_ID.fullmatch(item) for item in value):
        raise BrainRoutingError("REQUIRED_CAPABILITIES_INVALID")
    if len(set(value)) != len(value):
        raise BrainRoutingError("REQUIRED_CAPABILITIES_DUPLICATE")
    unknown = sorted(set(value) - set(_CAPABILITY_OWNER))
    if unknown:
        raise BrainRoutingError("UNKNOWN_CAPABILITY")
    return tuple(value)


def _constraints(request: Mapping[str, Any]) -> dict[str, Any]:
    value = request["constraints"]
    allowed = {"required_capabilities", "max_branches", "max_steps", "deadline_seconds",
               "conflict_policy"}
    if set(value) - allowed:
        raise BrainRoutingError("UNKNOWN_ROUTING_CONSTRAINT")
    required = _capability_list(value.get("required_capabilities"))
    max_branches = value.get("max_branches", _MAX_BRANCHES)
    if type(max_branches) is not int or not 1 <= max_branches <= _MAX_BRANCHES:
        raise BrainRoutingError("MAX_BRANCHES_INVALID")
    max_steps = value.get("max_steps", _MAX_STEPS)
    if type(max_steps) is not int or not 1 <= max_steps <= _MAX_STEPS:
        raise BrainRoutingError("MAX_STEPS_INVALID")
    deadline = value.get("deadline_seconds", 60.0)
    if isinstance(deadline, bool) or not isinstance(deadline, (int, float)):
        raise BrainRoutingError("DEADLINE_INVALID")
    if not math.isfinite(deadline) or not 0 < deadline <= _MAX_DEADLINE_SECONDS:
        raise BrainRoutingError("DEADLINE_INVALID")
    policy = value.get("conflict_policy", "INDEPENDENT_OUTPUTS")
    if not isinstance(policy, str) or policy not in {"INDEPENDENT_OUTPUTS", "REQUIRE_IDENTICAL_DIGEST"}:
        raise BrainRoutingError("CONFLICT_POLICY_INVALID")
    return {"required_capabilities": required, "max_branches": max_branches,
            "max_steps": max_steps, "deadline_seconds": float(deadline),
            "conflict_policy": policy}


def _inventory(
    available_capabilities: Mapping[str, Iterable[str]] | None,
    workers: Mapping[str, Callable[..., Mapping[str, Any]]],
) -> dict[str, frozenset[str]]:
    if available_capabilities is None:
        available_capabilities = {}
    if not isinstance(available_capabilities, Mapping) or not isinstance(workers, Mapping):
        raise BrainRoutingError("WORKER_REGISTRY_INVALID")
    result: dict[str, frozenset[str]] = {}
    for branch in set(available_capabilities) | set(workers):
        if branch not in BRANCH_CAPABILITIES:
            raise BrainRoutingError("UNKNOWN_BRANCH")
        if branch in workers and not callable(workers[branch]):
            raise BrainRoutingError("WORKER_ADAPTER_INVALID")
        declared = available_capabilities.get(branch, ())
        if isinstance(declared, (str, bytes)):
            raise BrainRoutingError("CAPABILITY_INVENTORY_INVALID")
        try:
            caps = frozenset(declared)
        except TypeError as exc:
            raise BrainRoutingError("CAPABILITY_INVENTORY_INVALID") from exc
        if any(not isinstance(item, str) for item in caps):
            raise BrainRoutingError("CAPABILITY_INVENTORY_INVALID")
        if not caps.issubset(BRANCH_CAPABILITIES[branch]):
            raise BrainRoutingError("CAPABILITY_INVENTORY_ESCALATION")
        # A capability declaration without a bound adapter is not available.
        result[branch] = caps if branch in workers else frozenset()
    return result


class BrainOrchestrator:
    """One deterministic coordinator; capabilities never confer cross-branch authority.

    Request constraints must explicitly name required capabilities. No worker is
    invoked if any required capability is unavailable. A worker result is accepted
    only through HG_CAPABILITY_RESULT_V1 and the supplied trusted evidence verifier.
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic):
        self._clock = clock

    def plan(
        self,
        request: Mapping[str, Any],
        *,
        available_capabilities: Mapping[str, Iterable[str]] | None = None,
        workers: Mapping[str, Callable[..., Mapping[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        try:
            normalized = validate_brain_request(request)
        except ContractError as exc:
            raise BrainRoutingError("BRAIN_REQUEST_INVALID") from exc
        if not _SHA.fullmatch(normalized["source_revision"]):
            raise BrainRoutingError("SOURCE_REVISION_INVALID")
        constraints = _constraints(normalized)
        goal_sha256 = hashlib.sha256(normalized["goal"].encode("utf-8")).hexdigest()
        constraints_digest = canonical_digest(normalized["constraints"])
        worker_map = {} if workers is None else workers
        inventory = _inventory(available_capabilities, worker_map)
        selected: dict[str, list[str]] = {}
        gaps: list[str] = []
        for capability in constraints["required_capabilities"]:
            owner = _CAPABILITY_OWNER[capability]
            if capability not in inventory.get(owner, frozenset()):
                gaps.append(capability)
            else:
                selected.setdefault(owner, []).append(capability)
        selected_branches = [branch for branch in BRANCH_ORDER if branch in selected]
        if (len(selected_branches) > constraints["max_branches"]
                or len(selected_branches) > constraints["max_steps"]):
            reason = ("MAX_BRANCHES_EXCEEDED" if len(selected_branches) > constraints["max_branches"]
                      else "MAX_STEPS_EXCEEDED")
            return {
                "schema_version": "HG_BRAIN_PLAN_V1",
                "request_id": normalized["request_id"],
                "correlation_id": normalized["correlation_id"],
                "source_revision": normalized["source_revision"],
                "status": "BLOCKED_ROUTE_BUDGET",
                "branches": [],
                "capability_gaps": [],
                "reason": reason,
            }
        return {
            "schema_version": "HG_BRAIN_PLAN_V1",
            "request_id": normalized["request_id"],
            "correlation_id": normalized["correlation_id"],
            "source_revision": normalized["source_revision"],
            "goal_sha256": goal_sha256,
            "constraints_digest": constraints_digest,
            "status": "BLOCKED_CAPABILITY_GAP" if gaps else "ROUTABLE",
            "branches": [
                {"branch_id": branch, "required_capabilities": sorted(selected[branch])}
                for branch in selected_branches
            ],
            "capability_gaps": sorted(gaps),
            "max_steps": constraints["max_steps"],
            "deadline_seconds": constraints["deadline_seconds"],
            "conflict_policy": constraints["conflict_policy"],
            "plan_digest": canonical_digest({
                "request_id": normalized["request_id"],
                "correlation_id": normalized["correlation_id"],
                "source_revision": normalized["source_revision"],
                "goal_sha256": goal_sha256,
                "constraints_digest": constraints_digest,
                "branches": [
                    {"branch_id": branch, "required_capabilities": sorted(selected[branch])}
                    for branch in selected_branches
                ],
                "capability_gaps": sorted(gaps),
                "max_steps": constraints["max_steps"],
                "deadline_seconds": constraints["deadline_seconds"],
                "conflict_policy": constraints["conflict_policy"],
            }),
        }

    def execute(
        self,
        request: Mapping[str, Any],
        *,
        available_capabilities: Mapping[str, Iterable[str]] | None,
        workers: Mapping[str, Callable[..., Mapping[str, Any]]],
        evidence_verifier: Callable[[str], bool] | None,
    ) -> dict[str, Any]:
        """Dispatch in fixed order and return a typed aggregate; never guess winners."""
        start = self._clock()
        plan = self.plan(request, available_capabilities=available_capabilities, workers=workers)
        base = {key: plan.get(key) for key in ("request_id", "correlation_id", "source_revision")}
        if plan["status"] != "ROUTABLE":
            return {**base, "status": plan["status"], "reason": (
                "REQUIRED_CAPABILITY_UNAVAILABLE" if plan["status"] == "BLOCKED_CAPABILITY_GAP"
                else plan["reason"]), "branch_results": [], "invoked_branches": []}

        norm = validate_brain_request(request)
        constraints = _constraints(norm)
        results: list[dict[str, Any]] = []
        invoked: list[str] = []
        in_doubt = False
        for branch_entry in plan["branches"]:
            # Deadlines can be checked between synchronous adapters. Python cannot safely
            # cancel an arbitrary injected synchronous call, so adapter-level timeouts remain required.
            if self._clock() - start >= constraints["deadline_seconds"]:
                results.append({"branch_id": branch_entry["branch_id"], "status": "BLOCKED",
                                "error_code": "ORCHESTRATION_DEADLINE_EXCEEDED"})
                break
            branch = branch_entry["branch_id"]
            invoked.append(branch)
            try:
                raw = workers[branch]({
                    "request_id": norm["request_id"],
                    "correlation_id": norm["correlation_id"],
                    "goal": norm["goal"],
                    "source_revision": norm["source_revision"],
                    "branch_id": branch,
                    "required_capabilities": branch_entry["required_capabilities"],
                    "plan_digest": plan["plan_digest"],
                    "max_steps": constraints["max_steps"],
                })
                verified = validate_capability_result(
                    raw,
                    expected_request_id=norm["request_id"],
                    expected_correlation_id=norm["correlation_id"],
                    expected_source_revision=norm["source_revision"],
                    evidence_verifier=evidence_verifier,
                )
                results.append({"branch_id": branch, **verified})
            except Exception as exc:
                # Any adapter exception could occur after an external side effect.
                in_doubt = True
                code = getattr(exc, "code", None)
                if not isinstance(code, str) or not code.strip():
                    # ContractError codes are stable; never serialize arbitrary exception text.
                    code = str(exc) if isinstance(exc, ContractError) else "WORKER_OUTCOME_UNKNOWN"
                results.append({"branch_id": branch, "status": "IN_DOUBT",
                                "error_code": code})
                break

        overall = aggregate_results(results, conflict_policy=constraints["conflict_policy"],
                                    expected_branches=[e["branch_id"] for e in plan["branches"]],
                                    in_doubt=in_doubt)
        return {**base, "status": overall, "plan_digest": plan["plan_digest"],
                "branch_results": results, "invoked_branches": invoked}


def aggregate_results(
    results: list[Mapping[str, Any]],
    *,
    conflict_policy: str = "INDEPENDENT_OUTPUTS",
    expected_branches: Iterable[str] = (),
    in_doubt: bool = False,
) -> str:
    """Strict status aggregation. Conflicts never resolve by arrival order."""
    if in_doubt or any(item.get("status") == "IN_DOUBT" for item in results):
        return "IN_DOUBT"
    expected = tuple(expected_branches)
    if (not expected or len(expected) != len(set(expected))
            or any(not isinstance(branch, str) or not branch for branch in expected)):
        return "INCONCLUSIVE"
    if any(not isinstance(item, Mapping) for item in results):
        return "INCONCLUSIVE"
    observed = [item.get("branch_id") for item in results]
    if len(observed) != len(set(observed)) or any(branch not in expected for branch in observed):
        return "INCONCLUSIVE"
    if set(observed) != set(expected):
        return "BLOCKED"
    statuses = [item.get("status") for item in results]
    if any(status == "FAIL" for status in statuses):
        return "FAIL"
    if any(status in {"BLOCKED", "NOT_RUN"} for status in statuses):
        return "BLOCKED"
    if any(status in {"PARTIAL", "RESPONSE_ONLY"} for status in statuses):
        return "PARTIAL"
    if any(status != "SUCCESS" for status in statuses):
        return "INCONCLUSIVE"
    if conflict_policy == "REQUIRE_IDENTICAL_DIGEST":
        digests = {item.get("output_digest") for item in results}
        if None in digests or len(digests) != 1:
            return "INCONCLUSIVE"
    elif conflict_policy != "INDEPENDENT_OUTPUTS":
        return "INCONCLUSIVE"
    return "SUCCESS"
