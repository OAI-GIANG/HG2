"""HG Unified Harness: fail-closed lifecycle, adapter, and result gates.

This is HG-native orchestration glue. It does not import or execute third-party
harness plugins, load hook scripts from disk, or grant tool permissions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Mapping

from .contracts import canonical_digest

HARNESS_SCHEMA_VERSION = "HG_UNIFIED_HARNESS_V1"
RUNTIME_REGISTRY_SCHEMA_VERSION = "HG_RUNTIME_CAPABILITY_REGISTRY_V1"
PROFILES = frozenset({"minimal", "standard", "strict"})
PHASES = frozenset({"before_request", "before_plan", "before_dispatch", "after_result"})
GUARD_PHASES = frozenset({"before_request", "before_plan", "before_dispatch"})
_HOOK_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,95}$")
_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PLAN_DIGEST_FIELDS = (
    "request_id", "correlation_id", "source_revision", "goal_sha256",
    "constraints_digest", "branches", "capability_gaps", "max_steps",
    "deadline_seconds", "conflict_policy",
)
_RISK = frozenset({
    "LOCAL_READ_ONLY", "LOCAL_WRITE", "OUTBOUND_PROVIDER_CALL",
    "EXTERNAL_WRITE", "DESTRUCTIVE",
})
_RESULT_STATUSES = frozenset({
    "SUCCESS", "FAIL", "BLOCKED", "PARTIAL", "NOT_RUN", "RESPONSE_ONLY",
    "IN_DOUBT", "INCONCLUSIVE", "BLOCKED_CAPABILITY_GAP", "BLOCKED_ROUTE_BUDGET",
})
# Only redacted audit metadata crosses into hooks. Prompts, credentials, arguments,
# absolute paths, and raw provider responses are intentionally not in this allowlist.
_SAFE_CONTEXT_FIELDS = frozenset({
    "request_id", "correlation_id", "source_revision", "plan_digest",
    "registry_digest", "input_sha256", "status", "error_code", "domain_id",
    "attempt_id", "branch_id", "required_capabilities", "domains", "branches",
    "capability_gaps", "side_effect_class", "hard_timeout_enforced",
    "planned_branch_count", "invoked_branch_count", "result_branch_count",
    "output_digest", "evidence_count", "profile", "phase", "reason_code",
})


class HarnessError(ValueError):
    """Stable fail-closed unified-harness error."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class HookDecision:
    allow: bool
    reason_code: str

    def __post_init__(self):
        if type(self.allow) is not bool or not isinstance(self.reason_code, str) or not _CODE.fullmatch(self.reason_code):
            raise HarnessError("HARNESS_HOOK_DECISION_INVALID")

    @classmethod
    def allow_execution(cls) -> "HookDecision":
        return cls(True, "HOOK_ALLOWED")

    @classmethod
    def deny(cls, reason_code: str = "HOOK_DENIED") -> "HookDecision":
        return cls(False, reason_code)


@dataclass(frozen=True)
class HarnessHook:
    hook_id: str
    phase: str
    kind: str
    callback: Callable[[Mapping[str, Any]], Any] = field(repr=False, compare=False)
    priority: int = 100
    enabled: bool = True


def _plan_digest_matches(plan: Mapping[str, Any]) -> bool:
    if not all(field in plan for field in _PLAN_DIGEST_FIELDS):
        return False
    if not isinstance(plan.get("plan_digest"), str) or not _SHA256.fullmatch(plan["plan_digest"]):
        return False
    try:
        core = {field: plan[field] for field in _PLAN_DIGEST_FIELDS}
        return canonical_digest(core) == plan["plan_digest"]
    except Exception:
        return False


def _safe_context(context: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(context, Mapping):
        raise HarnessError("HARNESS_HOOK_CONTEXT_INVALID")
    safe: dict[str, Any] = {}
    for key in sorted(_SAFE_CONTEXT_FIELDS.intersection(context.keys())):
        value = context[key]
        if value is None or isinstance(value, (str, bool, int)):
            if isinstance(value, str) and len(value) > 256:
                raise HarnessError("HARNESS_HOOK_CONTEXT_VALUE_TOO_LONG")
            safe[key] = value
        elif isinstance(value, float):
            # Floats are not needed by current hook contracts; omit rather than
            # leaking timing or accepting NaN/Infinity into policy callbacks.
            continue
        elif isinstance(value, (tuple, list)):
            if len(value) > 100:
                raise HarnessError("HARNESS_HOOK_CONTEXT_LIST_TOO_LONG")
            if any(not isinstance(item, (str, int, bool)) for item in value):
                raise HarnessError("HARNESS_HOOK_CONTEXT_LIST_INVALID")
            if any(isinstance(item, str) and len(item) > 256 for item in value):
                raise HarnessError("HARNESS_HOOK_CONTEXT_VALUE_TOO_LONG")
            safe[key] = tuple(value)
    return MappingProxyType(safe)


class HarnessHookRunner:
    """Run only explicitly injected Python hooks; never load hook code dynamically.

    Guard hooks may only run before execution. Observers can inspect redacted
    metadata but cannot authorize execution or modify the provided context.
    """

    def __init__(self, hooks=()):
        if not isinstance(hooks, (tuple, list)):
            raise HarnessError("HARNESS_HOOKS_INVALID")
        seen: set[str] = set()
        validated = []
        for hook in hooks:
            if not isinstance(hook, HarnessHook):
                raise HarnessError("HARNESS_HOOK_INVALID")
            if not isinstance(hook.hook_id, str) or not _HOOK_ID.fullmatch(hook.hook_id):
                raise HarnessError("HARNESS_HOOK_ID_INVALID")
            if hook.hook_id in seen:
                raise HarnessError("HARNESS_HOOK_ID_DUPLICATE")
            seen.add(hook.hook_id)
            if (not isinstance(hook.phase, str) or hook.phase not in PHASES
                    or not isinstance(hook.kind, str) or hook.kind not in {"GUARD", "OBSERVER"}):
                raise HarnessError("HARNESS_HOOK_PHASE_OR_KIND_INVALID")
            if hook.kind == "GUARD" and hook.phase not in GUARD_PHASES:
                raise HarnessError("HARNESS_POST_EXECUTION_GUARD_FORBIDDEN")
            if type(hook.priority) is not int or not -10000 <= hook.priority <= 10000:
                raise HarnessError("HARNESS_HOOK_PRIORITY_INVALID")
            if type(hook.enabled) is not bool or not callable(hook.callback):
                raise HarnessError("HARNESS_HOOK_CALLBACK_INVALID")
            validated.append(hook)
        self._hooks = tuple(sorted(validated, key=lambda item: (item.priority, item.hook_id)))

    def run(self, phase: str, context: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(phase, str) or phase not in PHASES:
            raise HarnessError("HARNESS_PHASE_INVALID")
        redacted = _safe_context(context)
        ran: list[str] = []
        observer_errors: list[str] = []
        for hook in self._hooks:
            if not hook.enabled or hook.phase != phase:
                continue
            ran.append(hook.hook_id)
            if hook.kind == "OBSERVER":
                try:
                    hook.callback(redacted)
                except Exception:
                    observer_errors.append(hook.hook_id)
                continue
            try:
                decision = hook.callback(redacted)
            except Exception:
                return {
                    "ok": False, "reason_code": "HARNESS_GUARD_EXCEPTION",
                    "hook_id": hook.hook_id, "hooks_run": ran,
                    "observer_errors": observer_errors,
                }
            if not isinstance(decision, HookDecision):
                return {
                    "ok": False, "reason_code": "HARNESS_GUARD_RESULT_INVALID",
                    "hook_id": hook.hook_id, "hooks_run": ran,
                    "observer_errors": observer_errors,
                }
            if not decision.allow:
                return {
                    "ok": False, "reason_code": decision.reason_code,
                    "hook_id": hook.hook_id, "hooks_run": ran,
                    "observer_errors": observer_errors,
                }
        return {
            "ok": True, "reason_code": "HARNESS_HOOKS_ALLOWED",
            "hooks_run": ran, "observer_errors": observer_errors,
        }


class UnifiedHarness:
    """Quality gate around HG's existing Brain + capability-registry dispatch.

    The gate never invents capabilities. A planned capability must be bound to a
    ready adapter at the same source revision. Strict mode additionally refuses
    external/destructive dispatch when the registry cannot prove required safety.
    """

    def __init__(self, profile: str = "standard", hooks=()):
        if not isinstance(profile, str) or profile not in PROFILES:
            raise HarnessError("HARNESS_PROFILE_INVALID")
        self.profile = profile
        self.hooks = HarnessHookRunner(hooks)

    def _receipt(self, *, ok: bool, reason_code: str, request_id: str = "",
                 correlation_id: str = "", source_revision: str = "",
                 plan_digest: str = "", registry_digest: str = "",
                 warnings=(), checks=()) -> dict[str, Any]:
        safe_text = lambda value, limit=256: value if isinstance(value, str) and len(value) <= limit else ""
        core = {
            "schema_version": HARNESS_SCHEMA_VERSION,
            "profile": self.profile,
            "ok": bool(ok),
            "reason_code": reason_code,
            "request_id": safe_text(request_id),
            "correlation_id": safe_text(correlation_id),
            "source_revision": source_revision if isinstance(source_revision, str) and _SHA.fullmatch(source_revision) else "",
            "plan_digest": plan_digest if isinstance(plan_digest, str) and _SHA256.fullmatch(plan_digest) else "",
            "registry_digest": registry_digest if isinstance(registry_digest, str) and _SHA256.fullmatch(registry_digest) else "",
            "warnings": [safe_text(item) for item in warnings if isinstance(item, str)][:256],
            "checks": [safe_text(item) for item in checks if isinstance(item, str)][:256],
        }
        core["receipt_digest"] = canonical_digest(core)
        return core

    def before_dispatch(self, *, plan: Mapping[str, Any],
                        registry_snapshot: Mapping[str, Any],
                        source_revision: str) -> dict[str, Any]:
        """Verify that the actual dispatch plan is bound to ready reviewed adapters."""
        request_id = plan.get("request_id", "") if isinstance(plan, Mapping) else ""
        correlation_id = plan.get("correlation_id", "") if isinstance(plan, Mapping) else ""
        plan_digest = plan.get("plan_digest", "") if isinstance(plan, Mapping) else ""
        registry_digest = registry_snapshot.get("registry_digest", "") if isinstance(registry_snapshot, Mapping) else ""
        checks: list[str] = []

        def fail(code: str):
            return self._receipt(
                ok=False, reason_code=code, request_id=request_id,
                correlation_id=correlation_id, source_revision=source_revision,
                plan_digest=plan_digest, registry_digest=registry_digest,
                checks=checks,
            )

        if not isinstance(plan, Mapping) or plan.get("status") != "ROUTABLE":
            return fail("HARNESS_PLAN_NOT_ROUTABLE")
        for field_name in ("request_id", "correlation_id"):
            if not isinstance(plan.get(field_name), str) or not plan[field_name].strip():
                return fail("HARNESS_PLAN_IDENTITY_INVALID")
        if not isinstance(source_revision, str) or not _SHA.fullmatch(source_revision):
            return fail("HARNESS_SOURCE_REVISION_INVALID")
        if plan.get("source_revision") != source_revision:
            return fail("HARNESS_PLAN_SOURCE_REVISION_MISMATCH")
        if not isinstance(plan_digest, str) or not _SHA256.fullmatch(plan_digest):
            return fail("HARNESS_PLAN_DIGEST_INVALID")
        if not _plan_digest_matches(plan):
            return fail("HARNESS_PLAN_DIGEST_MISMATCH")
        if (not isinstance(registry_snapshot, Mapping)
                or set(registry_snapshot) != {
                    "schema_version", "source_revision_set_sha256", "entries", "registry_digest"
                }
                or registry_snapshot.get("schema_version") != RUNTIME_REGISTRY_SCHEMA_VERSION):
            return fail("HARNESS_REGISTRY_SCHEMA_INVALID")
        if (not isinstance(registry_digest, str) or not _SHA256.fullmatch(registry_digest)
                or not isinstance(registry_snapshot.get("source_revision_set_sha256"), str)
                or not _SHA256.fullmatch(registry_snapshot["source_revision_set_sha256"])):
            return fail("HARNESS_REGISTRY_DIGEST_INVALID")
        snapshot_core = {key: value for key, value in registry_snapshot.items() if key != "registry_digest"}
        try:
            recomputed_registry_digest = canonical_digest(snapshot_core)
        except Exception:
            return fail("HARNESS_REGISTRY_CONTENT_INVALID")
        if recomputed_registry_digest != registry_digest:
            return fail("HARNESS_REGISTRY_DIGEST_MISMATCH")
        entries = registry_snapshot.get("entries")
        branches = plan.get("branches")
        if not isinstance(entries, list) or not isinstance(branches, list) or not branches:
            return fail("HARNESS_DISPATCH_INVENTORY_INVALID")
        try:
            revisions = sorted({
                entry.get("source_revision") for entry in entries
                if isinstance(entry, Mapping) and isinstance(entry.get("source_revision"), str)
            })
            expected_revision_set = (
                canonical_digest({"adapter_source_revisions": revisions})
                if revisions else "0" * 64
            )
        except Exception:
            return fail("HARNESS_REGISTRY_SOURCE_REVISION_SET_INVALID")
        if expected_revision_set != registry_snapshot["source_revision_set_sha256"]:
            return fail("HARNESS_REGISTRY_SOURCE_REVISION_SET_MISMATCH")
        by_capability: dict[str, Mapping[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, Mapping):
                return fail("HARNESS_REGISTRY_ENTRY_INVALID")
            capability_id = entry.get("capability_id")
            if not isinstance(capability_id, str) or not capability_id or capability_id in by_capability:
                return fail("HARNESS_REGISTRY_CAPABILITY_DUPLICATE_OR_INVALID")
            by_capability[capability_id] = entry
        branch_ids: set[str] = set()
        warnings: list[str] = []
        for branch in branches:
            if not isinstance(branch, Mapping):
                return fail("HARNESS_PLAN_BRANCH_INVALID")
            branch_id = branch.get("branch_id")
            capabilities = branch.get("required_capabilities")
            if (not isinstance(branch_id, str) or not branch_id or branch_id in branch_ids
                    or not isinstance(capabilities, list) or not capabilities
                    or any(not isinstance(cap, str) or not cap for cap in capabilities)
                    or len(capabilities) != len(set(capabilities))):
                return fail("HARNESS_PLAN_BRANCH_INVALID")
            branch_ids.add(branch_id)
            for capability in capabilities:
                entry = by_capability.get(capability)
                if entry is None:
                    return fail("HARNESS_PLANNED_CAPABILITY_UNREGISTERED")
                if entry.get("domain_id") != branch_id:
                    return fail("HARNESS_CAPABILITY_OWNER_MISMATCH")
                if entry.get("ready") is not True or entry.get("lifecycle_state") not in {"TESTED", "VERIFIED", "OPERATIONAL"}:
                    return fail("HARNESS_CAPABILITY_NOT_READY")
                if entry.get("source_revision") != source_revision:
                    return fail("HARNESS_CAPABILITY_SOURCE_REVISION_MISMATCH")
                risk = entry.get("side_effect_class")
                if not isinstance(risk, str) or risk not in _RISK:
                    return fail("HARNESS_CAPABILITY_RISK_CLASS_INVALID")
                if entry.get("hard_timeout_enforced") is not True:
                    if self.profile == "strict" and risk in {"OUTBOUND_PROVIDER_CALL", "EXTERNAL_WRITE", "DESTRUCTIVE"}:
                        return fail("HARNESS_STRICT_TIMEOUT_GATE_BLOCKED")
                    warnings.append("HARNESS_HARD_TIMEOUT_NOT_PROVEN:" + capability)
                if self.profile == "strict" and risk in {"EXTERNAL_WRITE", "DESTRUCTIVE"}:
                    return fail("HARNESS_STRICT_APPROVAL_GATE_REQUIRED")
            checks.append("CAPABILITIES_BOUND:" + branch_id)
        hook_result = self.hooks.run("before_dispatch", {
            "request_id": request_id, "correlation_id": correlation_id,
            "source_revision": source_revision, "plan_digest": plan_digest,
            "registry_digest": registry_digest, "domains": sorted(branch_ids),
            "planned_branch_count": len(branches), "profile": self.profile,
        })
        if not hook_result["ok"]:
            return self._receipt(
                ok=False, reason_code=hook_result["reason_code"],
                request_id=request_id, correlation_id=correlation_id,
                source_revision=source_revision, plan_digest=plan_digest,
                registry_digest=registry_digest, warnings=warnings,
                checks=checks + ["HOOK_GATE_BLOCKED"],
            )
        warnings.extend("HARNESS_OBSERVER_FAILED:" + hook_id for hook_id in hook_result["observer_errors"])
        checks.append("HOOKS_ALLOWED")
        return self._receipt(
            ok=True, reason_code="HARNESS_DISPATCH_ALLOWED",
            request_id=request_id, correlation_id=correlation_id,
            source_revision=source_revision, plan_digest=plan_digest,
            registry_digest=registry_digest, warnings=warnings, checks=checks,
        )

    def verify_outcome(self, *, plan: Mapping[str, Any], result: Mapping[str, Any],
                       source_revision: str) -> dict[str, Any]:
        """Cross-check the returned execution trace independently of branch aggregation."""
        request_id = plan.get("request_id", "") if isinstance(plan, Mapping) else ""
        correlation_id = plan.get("correlation_id", "") if isinstance(plan, Mapping) else ""
        plan_digest = plan.get("plan_digest", "") if isinstance(plan, Mapping) else ""
        checks: list[str] = []

        def fail(code: str):
            return self._receipt(
                ok=False, reason_code=code, request_id=request_id,
                correlation_id=correlation_id, source_revision=source_revision,
                plan_digest=plan_digest, checks=checks,
            )

        if not isinstance(plan, Mapping) or not isinstance(result, Mapping):
            return fail("HARNESS_OUTCOME_MAPPING_INVALID")
        if result.get("request_id") != request_id or result.get("correlation_id") != correlation_id:
            return fail("HARNESS_OUTCOME_IDENTITY_MISMATCH")
        if result.get("source_revision") != source_revision or plan.get("source_revision") != source_revision:
            return fail("HARNESS_OUTCOME_SOURCE_REVISION_MISMATCH")
        if plan.get("status") == "ROUTABLE" and not _plan_digest_matches(plan):
            return fail("HARNESS_PLAN_DIGEST_MISMATCH")
        if plan.get("status") == "ROUTABLE" and result.get("plan_digest") != plan_digest:
            return fail("HARNESS_OUTCOME_PLAN_DIGEST_MISMATCH")
        if not isinstance(source_revision, str) or not _SHA.fullmatch(source_revision):
            return fail("HARNESS_SOURCE_REVISION_INVALID")

        plan_status = plan.get("status")
        result_status = result.get("status")
        if not isinstance(result_status, str) or result_status not in _RESULT_STATUSES:
            return fail("HARNESS_OUTCOME_STATUS_INVALID")
        if plan_status != "ROUTABLE":
            if result_status != plan_status:
                return fail("HARNESS_BLOCKED_PLAN_RESULT_MISMATCH")
            if result.get("branch_results") != [] or result.get("invoked_branches") != []:
                return fail("HARNESS_BLOCKED_PLAN_HAS_DISPATCH_TRACE")
            checks.append("BLOCKED_PLAN_NO_DISPATCH")
        else:
            branches = plan.get("branches")
            branch_results = result.get("branch_results")
            invoked = result.get("invoked_branches")
            if not isinstance(branches, list) or not isinstance(branch_results, list) or not isinstance(invoked, list):
                return fail("HARNESS_OUTCOME_TRACE_INVALID")
            planned_ids = [item.get("branch_id") for item in branches if isinstance(item, Mapping)]
            if (not planned_ids or len(planned_ids) != len(branches)
                    or any(not isinstance(item, str) or not item for item in planned_ids)
                    or len(set(planned_ids)) != len(planned_ids)):
                return fail("HARNESS_PLAN_BRANCH_IDS_INVALID")
            if (any(not isinstance(item, str) for item in invoked)
                    or len(set(invoked)) != len(invoked)
                    or any(item not in planned_ids for item in invoked)):
                return fail("HARNESS_INVOKED_BRANCH_INVALID")
            if [item for item in planned_ids if item in set(invoked)] != invoked:
                return fail("HARNESS_INVOKED_BRANCH_ORDER_INVALID")
            result_by_branch: dict[str, Mapping[str, Any]] = {}
            for item in branch_results:
                if not isinstance(item, Mapping):
                    return fail("HARNESS_BRANCH_RESULT_INVALID")
                branch_id = item.get("branch_id")
                status = item.get("status")
                if (not isinstance(branch_id, str) or branch_id not in planned_ids
                        or branch_id in result_by_branch
                        or not isinstance(status, str)
                        or status not in _RESULT_STATUSES):
                    return fail("HARNESS_BRANCH_RESULT_INVALID")
                result_by_branch[branch_id] = item
            for branch_id in invoked:
                if branch_id not in result_by_branch:
                    return fail("HARNESS_INVOKED_BRANCH_RESULT_MISSING")
            for branch_id, item in result_by_branch.items():
                if branch_id not in invoked and not (
                    item.get("status") == "BLOCKED"
                    and item.get("error_code") == "ORCHESTRATION_DEADLINE_EXCEEDED"
                ):
                    return fail("HARNESS_UNINVOKED_BRANCH_HAS_RESULT")
            statuses = [item.get("status") for item in result_by_branch.values()]
            if result_status == "SUCCESS":
                if (set(result_by_branch) != set(planned_ids) or invoked != planned_ids
                        or any(status != "SUCCESS" for status in statuses)):
                    return fail("HARNESS_SUCCESS_NOT_PROVEN")
                checks.append("SUCCESS_TRACE_COMPLETE")
            elif result_status == "PARTIAL":
                if (set(result_by_branch) != set(planned_ids) or invoked != planned_ids
                        or not any(status in {"PARTIAL", "RESPONSE_ONLY"} for status in statuses)
                        or any(status == "IN_DOUBT" for status in statuses)):
                    return fail("HARNESS_PARTIAL_TRACE_INVALID")
                checks.append("PARTIAL_TRACE_EXPLICIT")
            elif result_status == "IN_DOUBT":
                if not any(status == "IN_DOUBT" for status in statuses):
                    return fail("HARNESS_IN_DOUBT_WITHOUT_UNCERTAIN_BRANCH")
                checks.append("IN_DOUBT_EXPLICIT")
            elif result_status == "FAIL":
                if "FAIL" not in statuses:
                    return fail("HARNESS_FAIL_WITHOUT_FAILED_BRANCH")
                checks.append("FAILURE_EXPLICIT")
            elif result_status in {"BLOCKED", "BLOCKED_CAPABILITY_GAP", "BLOCKED_ROUTE_BUDGET"}:
                if "BLOCKED" not in statuses and set(result_by_branch) == set(planned_ids):
                    return fail("HARNESS_BLOCKED_WITHOUT_BLOCKED_BRANCH")
                checks.append("BLOCKED_EXPLICIT")
            else:
                checks.append("NON_SUCCESS_STATUS_NOT_UPGRADED")
        hook_result = self.hooks.run("after_result", {
            "request_id": request_id, "correlation_id": correlation_id,
            "source_revision": source_revision, "plan_digest": plan_digest,
            "status": result_status, "result_branch_count": len(result.get("branch_results", [])),
            "invoked_branch_count": len(result.get("invoked_branches", [])),
            "profile": self.profile,
        })
        warnings = ["HARNESS_OBSERVER_FAILED:" + hook_id for hook_id in hook_result["observer_errors"]]
        receipt = self._receipt(
            ok=True, reason_code="HARNESS_OUTCOME_VERIFIED",
            request_id=request_id, correlation_id=correlation_id,
            source_revision=source_revision, plan_digest=plan_digest,
            warnings=warnings, checks=checks + ["OUTCOME_HOOKS_OBSERVED"],
        )
        receipt["result_status"] = result_status
        receipt["receipt_digest"] = canonical_digest({
            key: value for key, value in receipt.items() if key != "receipt_digest"
        })
        return receipt
