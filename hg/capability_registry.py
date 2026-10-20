"""Trusted, versioned runtime registry for HG2 logical-domain adapters.

The registry is a fail-closed binding layer, not an authorization grant. Static
ownership in BrainOrchestrator defines the maximum capabilities a domain may own;
only a concrete, healthy, eligible adapter registered for this request becomes
available to the planner. Undeclared/unbound capabilities stay unavailable.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from .brain_orchestrator import BRANCH_CAPABILITIES, BRANCH_ORDER
from .contracts import BRAIN_WORKER_CONTEXT_V1, CAPABILITY_RESULT_V1, canonical_digest

CAPABILITY_REGISTRY_V1 = "HG_RUNTIME_CAPABILITY_REGISTRY_V1"
_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
_ACTIVE_MATURITY = frozenset({"TESTED", "VERIFIED", "OPERATIONAL"})
_MATURITY = frozenset({
    "PROPOSED", "IMPLEMENTED", "TESTED", "VERIFIED", "OPERATIONAL",
    "BLOCKED", "DEPRECATED",
})
_SIDE_EFFECT_CLASSES = frozenset({
    "LOCAL_READ_ONLY", "LOCAL_WRITE", "OUTBOUND_PROVIDER_CALL",
    "EXTERNAL_WRITE", "DESTRUCTIVE",
})


class CapabilityRegistryError(ValueError):
    """Stable fail-closed runtime capability registry error."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class RuntimeDomainBinding:
    """A real callable adapter bound to one logical domain and its capability set."""

    domain_id: str
    capability_ids: tuple[str, ...]
    implementation_id: str
    adapter_version: str
    input_contract: str
    output_contract: str
    authority_contract: str
    side_effect_class: str
    declared_timeout_seconds: float
    hard_timeout_enforced: bool
    max_invocations_per_request: int
    lifecycle_state: str
    source_revision: str
    evidence_verifier_id: str
    adapter: Callable[[Mapping[str, Any]], Mapping[str, Any]] = field(repr=False, compare=False)
    readiness_check: Callable[[], bool] = field(repr=False, compare=False)


class RuntimeCapabilityRegistry:
    """Request-scoped capability admission and dispatcher projection.

    One adapter owns a domain in this first serial slice. Composition of several
    adapters inside one domain needs a versioned composition/DAG contract and is
    deliberately not inferred from the static capability list.
    """

    def __init__(self) -> None:
        self._by_domain: dict[str, RuntimeDomainBinding] = {}
        self._by_capability: dict[str, RuntimeDomainBinding] = {}

    def register(self, binding: RuntimeDomainBinding) -> None:
        if not isinstance(binding, RuntimeDomainBinding):
            raise CapabilityRegistryError("REGISTRY_BINDING_INVALID")
        if not isinstance(binding.domain_id, str) or binding.domain_id not in BRANCH_CAPABILITIES:
            raise CapabilityRegistryError("REGISTRY_DOMAIN_UNKNOWN")
        if not isinstance(binding.capability_ids, tuple) or not binding.capability_ids:
            raise CapabilityRegistryError("REGISTRY_CAPABILITIES_INVALID")
        if any(not isinstance(item, str) for item in binding.capability_ids):
            raise CapabilityRegistryError("REGISTRY_CAPABILITY_ID_INVALID")
        if len(set(binding.capability_ids)) != len(binding.capability_ids):
            raise CapabilityRegistryError("REGISTRY_CAPABILITY_DUPLICATE")
        if binding.domain_id in self._by_domain:
            raise CapabilityRegistryError("REGISTRY_DOMAIN_ALREADY_BOUND")
        for capability_id in binding.capability_ids:
            if not isinstance(capability_id, str) or not _ID_RE.fullmatch(capability_id):
                raise CapabilityRegistryError("REGISTRY_CAPABILITY_ID_INVALID")
            if capability_id not in BRANCH_CAPABILITIES[binding.domain_id]:
                raise CapabilityRegistryError("REGISTRY_CAPABILITY_OWNER_MISMATCH")
            if capability_id in self._by_capability:
                raise CapabilityRegistryError("REGISTRY_CAPABILITY_ALREADY_BOUND")
        for field_name in ("implementation_id", "adapter_version", "input_contract",
                           "output_contract", "authority_contract", "evidence_verifier_id"):
            value = getattr(binding, field_name)
            if not isinstance(value, str) or not value.strip() or len(value) > 256:
                raise CapabilityRegistryError("REGISTRY_METADATA_INVALID")
        if not isinstance(binding.lifecycle_state, str) or binding.lifecycle_state not in _MATURITY:
            raise CapabilityRegistryError("REGISTRY_LIFECYCLE_STATE_INVALID")
        if not isinstance(binding.side_effect_class, str) or binding.side_effect_class not in _SIDE_EFFECT_CLASSES:
            raise CapabilityRegistryError("REGISTRY_SIDE_EFFECT_CLASS_INVALID")
        timeout = binding.declared_timeout_seconds
        if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
                or not math.isfinite(timeout) or not 0 < timeout <= 3600):
            raise CapabilityRegistryError("REGISTRY_TIMEOUT_INVALID")
        if type(binding.hard_timeout_enforced) is not bool:
            raise CapabilityRegistryError("REGISTRY_TIMEOUT_ENFORCEMENT_INVALID")
        calls = binding.max_invocations_per_request
        if type(calls) is not int or not 1 <= calls <= 100:
            raise CapabilityRegistryError("REGISTRY_INVOCATION_BUDGET_INVALID")
        if not isinstance(binding.source_revision, str) or not _SHA_RE.fullmatch(binding.source_revision):
            raise CapabilityRegistryError("REGISTRY_SOURCE_REVISION_INVALID")
        if not callable(binding.adapter) or not callable(binding.readiness_check):
            raise CapabilityRegistryError("REGISTRY_ADAPTER_NOT_CALLABLE")
        self._by_domain[binding.domain_id] = binding
        for capability_id in binding.capability_ids:
            self._by_capability[capability_id] = binding

    @staticmethod
    def _ready(binding: RuntimeDomainBinding) -> bool:
        try:
            return binding.readiness_check() is True
        except Exception:
            return False

    def resolve(self) -> dict[str, Any]:
        """Return only healthy, bound adapters as BrainOrchestrator maps."""
        inventory: dict[str, set[str]] = {}
        workers: dict[str, Callable[..., Mapping[str, Any]]] = {}
        entries = []
        readiness: dict[str, bool] = {}

        for domain_id in BRANCH_ORDER:
            binding = self._by_domain.get(domain_id)
            domain_ready = (
                binding is not None
                and binding.lifecycle_state in _ACTIVE_MATURITY
                and self._ready(binding)
            )
            if binding is not None:
                readiness[domain_id] = domain_ready
            for capability_id in sorted(BRANCH_CAPABILITIES[domain_id]):
                current = self._by_capability.get(capability_id)
                if current is None:
                    entry = {
                        "capability_id": capability_id,
                        "domain_id": domain_id,
                        "implementation_id": None,
                        "adapter_version": None,
                        "input_contract": None,
                        "output_contract": None,
                        "authority_contract": None,
                        "side_effect_class": None,
                        "declared_timeout_seconds": None,
                        "hard_timeout_enforced": False,
                        "max_invocations_per_request": None,
                        "lifecycle_state": "UNBOUND",
                        "ready": False,
                        "reason": "ADAPTER_NOT_REGISTERED",
                        "source_revision": None,
                        "evidence_verifier_id": None,
                    }
                else:
                    active = readiness[domain_id]
                    entry = {
                        "capability_id": capability_id,
                        "domain_id": domain_id,
                        "implementation_id": current.implementation_id,
                        "adapter_version": current.adapter_version,
                        "input_contract": current.input_contract,
                        "output_contract": current.output_contract,
                        "authority_contract": current.authority_contract,
                        "side_effect_class": current.side_effect_class,
                        "declared_timeout_seconds": float(current.declared_timeout_seconds),
                        "hard_timeout_enforced": current.hard_timeout_enforced,
                        "max_invocations_per_request": current.max_invocations_per_request,
                        "lifecycle_state": current.lifecycle_state if active else "BLOCKED",
                        "ready": active,
                        "reason": None if active else (
                            "LIFECYCLE_NOT_DISPATCHABLE"
                            if current.lifecycle_state not in _ACTIVE_MATURITY
                            else "ADAPTER_NOT_READY"
                        ),
                        "source_revision": current.source_revision,
                        "evidence_verifier_id": current.evidence_verifier_id,
                    }
                entries.append(entry)
            if binding is None or not domain_ready:
                continue
            inventory[domain_id] = set(binding.capability_ids)
            counts = {capability_id: 0 for capability_id in binding.capability_ids}

            def invoke(context, bound=binding, invocation_counts=counts):
                required = context.get("required_capabilities")
                request_id = context.get("request_id")
                correlation_id = context.get("correlation_id")
                source_revision = context.get("source_revision")
                if (context.get("schema_version") != BRAIN_WORKER_CONTEXT_V1
                        or not isinstance(required, list) or not required
                        or any(not isinstance(item, str) for item in required)
                        or not set(required).issubset(bound.capability_ids)):
                    return {
                        "schema_version": CAPABILITY_RESULT_V1,
                        "request_id": request_id,
                        "correlation_id": correlation_id,
                        "status": "BLOCKED",
                        "output_digest": None,
                        "error_code": "REGISTRY_REQUIRED_CAPABILITY_NOT_BOUND",
                        "evidence_refs": [],
                        "source_revision": source_revision,
                    }
                if not self._ready(bound):
                    return {
                        "schema_version": CAPABILITY_RESULT_V1,
                        "request_id": request_id,
                        "correlation_id": correlation_id,
                        "status": "BLOCKED",
                        "output_digest": None,
                        "error_code": "REGISTRY_ADAPTER_NOT_READY",
                        "evidence_refs": [],
                        "source_revision": source_revision,
                    }
                if any(invocation_counts[capability_id] >= bound.max_invocations_per_request
                       for capability_id in required):
                    return {
                        "schema_version": CAPABILITY_RESULT_V1,
                        "request_id": request_id,
                        "correlation_id": correlation_id,
                        "status": "BLOCKED",
                        "output_digest": None,
                        "error_code": "REGISTRY_INVOCATION_BUDGET_EXCEEDED",
                        "evidence_refs": [],
                        "source_revision": source_revision,
                    }
                for capability_id in required:
                    invocation_counts[capability_id] += 1
                result = bound.adapter(context)
                if not isinstance(result, Mapping):
                    # The adapter has run; a malformed response may follow a side effect,
                    # so do not pretend the outcome is known.
                    raise CapabilityRegistryError("REGISTRY_ADAPTER_RESULT_INVALID")
                return result

            workers[domain_id] = invoke

        snapshot_core = {
            "schema_version": CAPABILITY_REGISTRY_V1,
            "source_revision_set_sha256": self._registry_source_revision(),
            "entries": entries,
        }
        return {
            "available_capabilities": inventory,
            "workers": workers,
            "snapshot": {
                **snapshot_core,
                "registry_digest": canonical_digest(snapshot_core),
            },
        }

    def _registry_source_revision(self) -> str:
        revisions = sorted({binding.source_revision for binding in self._by_domain.values()})
        if not revisions:
            return "0" * 64
        # Different adapters may have originated from different source revisions;
        # bind the set instead of assuming they share one commit identity.
        return canonical_digest({"adapter_source_revisions": revisions})
