"""Risk-adaptive verification budget model with mandatory floors and safe stop."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class BudgetError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}" if detail else code)


_RISK_POINTS = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


@dataclass(frozen=True)
class VerificationPlan:
    risk_score: int
    allocated_units: int
    mandatory_floor: int
    required_checks: tuple[str, ...]
    state: str
    reason: str


def plan_verification(
    *,
    risk_level: str,
    mandatory_checks: tuple[str, ...],
    optional_checks: tuple[str, ...],
    available_units: int,
    base_units: int = 2,
    max_units: int = 20,
) -> VerificationPlan:
    if not isinstance(risk_level, str) or risk_level not in _RISK_POINTS:
        raise BudgetError("VERIFICATION_RISK_INVALID")
    if type(available_units) is not int or available_units < 0:
        raise BudgetError("VERIFICATION_BUDGET_INVALID")
    if type(base_units) is not int or type(max_units) is not int or not 1 <= base_units <= max_units <= 1000:
        raise BudgetError("VERIFICATION_BUDGET_INVALID")
    try:
        mandatory_list = list(mandatory_checks)
        optional_list = list(optional_checks)
    except TypeError as exc:
        raise BudgetError("VERIFICATION_CHECK_INVALID", "check lists must be iterable") from exc
    if len(mandatory_list) > 1024 or len(optional_list) > 1024:
        raise BudgetError("VERIFICATION_RESOURCE_LIMIT", "too many check identifiers")
    # C0 is a hard product floor and cannot be removed by caller-supplied policy.
    if "C0" not in mandatory_list:
        mandatory_list.append("C0")
    checks = mandatory_list + optional_list
    if any(not isinstance(c, str) or not c.strip() for c in checks):
        raise BudgetError("VERIFICATION_CHECK_INVALID")
    if len(checks) != len(set(checks)):
        raise BudgetError("VERIFICATION_CHECK_DUPLICATE")
    required = tuple(sorted(set(mandatory_list)))
    floor = len(required)
    risk_score = _RISK_POINTS[risk_level]
    desired = min(max_units, base_units * risk_score + floor)
    if available_units < floor:
        return VerificationPlan(risk_score, available_units, floor, required, "BLOCKED",
                                "MANDATORY_CHECK_FLOOR_UNFUNDED")
    allocated = min(desired, available_units)
    if allocated < desired:
        # Optional checks may be trimmed, but mandatory checks are never skipped.
        return VerificationPlan(risk_score, allocated, floor, required, "DEGRADED_SAFE",
                                "OPTIONAL_VERIFICATION_REDUCED")
    return VerificationPlan(risk_score, allocated, floor, required, "PLANNED",
                            "RISK_ADJUSTED_BUDGET")


def evaluate_verification_result(
    *,
    plan: VerificationPlan,
    results: dict[str, str],
    critical_checks: tuple[str, ...] = ("C0",),
) -> dict[str, Any]:
    """Aggregate observed check states without letting weighted scores override critical failure."""
    if plan.state == "BLOCKED":
        return {"status": "BLOCKED", "reason": plan.reason, "executable": False}
    allowed = {"PASS", "FAIL", "BLOCKED", "INCONCLUSIVE", "NOT_RUN"}
    if type(results) is not dict or any(not isinstance(k, str) or not isinstance(v, str) or v not in allowed for k, v in results.items()):
        raise BudgetError("VERIFICATION_RESULT_INVALID")
    missing = [c for c in plan.required_checks if c not in results or results[c] != "PASS"]
    try:
        critical_list = list(critical_checks)
    except TypeError as exc:
        raise BudgetError("VERIFICATION_CRITICAL_CHECKS_INVALID") from exc
    if len(critical_list) > 1024 or any(not isinstance(item, str) or not item.strip() for item in critical_list):
        raise BudgetError("VERIFICATION_CRITICAL_CHECKS_INVALID")
    effective_critical = set(critical_list) | {"C0"}
    failed_critical = sorted(c for c in effective_critical if results.get(c) == "FAIL")
    if failed_critical:
        return {"status": "FAIL", "reason": "CRITICAL_CHECK_FAILED",
                "failed_checks": failed_critical, "missing_mandatory": missing, "executable": False}
    missing_critical = sorted(c for c in effective_critical if c not in results)
    if missing_critical:
        return {"status": "BLOCKED", "reason": "CRITICAL_CHECK_NOT_RUN",
                "missing_critical": missing_critical, "missing_mandatory": missing, "executable": False}
    if missing:
        return {"status": "BLOCKED", "reason": "MANDATORY_CHECK_NOT_PASS",
                "missing_mandatory": missing, "executable": False}
    not_run = sorted(k for k, v in results.items() if v == "NOT_RUN")
    if not_run:
        return {"status": "INCONCLUSIVE", "reason": "CHECKS_NOT_RUN",
                "not_run": not_run, "executable": False}
    fail = sorted(k for k, v in results.items() if v == "FAIL")
    if fail:
        return {"status": "FAIL", "reason": "CHECK_FAILED",
                "failed_checks": fail, "executable": False}
    blocked = sorted(k for k, v in results.items() if v == "BLOCKED")
    if blocked:
        return {"status": "BLOCKED", "reason": "CHECK_BLOCKED",
                "blocked_checks": blocked, "executable": False}
    inconclusive = sorted(k for k, v in results.items() if v == "INCONCLUSIVE")
    if inconclusive or plan.state == "DEGRADED_SAFE":
        return {"status": "INCONCLUSIVE", "reason": "VERIFICATION_INCOMPLETE",
                "inconclusive_checks": inconclusive, "executable": False}
    return {"status": "PASS", "reason": "ALL_REQUIRED_CHECKS_PASS", "executable": False}
