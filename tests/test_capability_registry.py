"""Tests for HG2's fail-closed runtime capability registry."""
import hashlib
import unittest

from hg.brain_orchestrator import BRANCH_CAPABILITIES, BrainOrchestrator
from hg.capability_registry import (
    CAPABILITY_REGISTRY_V1,
    CapabilityRegistryError,
    RuntimeCapabilityRegistry,
    RuntimeDomainBinding,
)
from hg.contracts import BRAIN_REQUEST_V1, BRAIN_WORKER_CONTEXT_V1, CAPABILITY_RESULT_V1, canonical_digest

SOURCE = hashlib.sha256(b"registry-test-source").hexdigest()


def binding(**overrides):
    values = {
        "domain_id": "memory_knowledge",
        "capability_ids": ("memory.search",),
        "implementation_id": "test.memory.search",
        "adapter_version": "1",
        "input_contract": BRAIN_WORKER_CONTEXT_V1,
        "output_contract": CAPABILITY_RESULT_V1,
        "authority_contract": "test.principal.read.scope",
        "side_effect_class": "LOCAL_READ_ONLY",
        "declared_timeout_seconds": 5.0,
        "hard_timeout_enforced": False,
        "max_invocations_per_request": 1,
        "lifecycle_state": "TESTED",
        "source_revision": SOURCE,
        "evidence_verifier_id": "test.memory.context.v1",
        "adapter": lambda ctx: {
            "schema_version": CAPABILITY_RESULT_V1,
            "request_id": ctx["request_id"],
            "correlation_id": ctx["correlation_id"],
            "status": "SUCCESS",
            "output_digest": "a" * 64,
            "error_code": None,
            "evidence_refs": ["evidence:sha256:" + "b" * 64],
            "source_revision": ctx["source_revision"],
        },
        "readiness_check": lambda: True,
    }
    values.update(overrides)
    return RuntimeDomainBinding(**values)


def request(capabilities):
    return {
        "schema_version": BRAIN_REQUEST_V1,
        "request_id": "registry-request-1",
        "correlation_id": "registry-correlation-1",
        "goal": "verify runtime registry",
        "constraints": {"required_capabilities": list(capabilities)},
        "source_revision": SOURCE,
    }


class RuntimeCapabilityRegistryTests(unittest.TestCase):
    def test_unbound_registry_exposes_no_capability(self):
        resolved = RuntimeCapabilityRegistry().resolve()
        self.assertEqual(resolved["available_capabilities"], {})
        self.assertEqual(resolved["workers"], {})
        self.assertEqual(resolved["snapshot"]["schema_version"], CAPABILITY_REGISTRY_V1)
        self.assertEqual(len(resolved["snapshot"]["registry_digest"]), 64)
        total = sum(len(capabilities) for capabilities in BRANCH_CAPABILITIES.values())
        self.assertEqual(len(resolved["snapshot"]["entries"]), total)
        self.assertTrue(all(entry["lifecycle_state"] == "UNBOUND"
                            for entry in resolved["snapshot"]["entries"]))
        core = {k: v for k, v in resolved["snapshot"].items() if k != "registry_digest"}
        self.assertEqual(resolved["snapshot"]["registry_digest"], canonical_digest(core))

    def test_bound_healthy_adapter_projects_only_its_capability(self):
        registry = RuntimeCapabilityRegistry()
        registry.register(binding())
        resolved = registry.resolve()
        self.assertEqual(resolved["available_capabilities"], {"memory_knowledge": {"memory.search"}})
        self.assertEqual(set(resolved["workers"]), {"memory_knowledge"})
        entries = {entry["capability_id"]: entry for entry in resolved["snapshot"]["entries"]}
        self.assertEqual(entries["memory.search"]["lifecycle_state"], "TESTED")
        self.assertTrue(entries["memory.search"]["ready"])
        self.assertFalse(entries["memory.search"]["hard_timeout_enforced"])
        self.assertEqual(entries["memory.recall"]["lifecycle_state"], "UNBOUND")

    def test_request_dispatch_calls_adapter_once_and_enforces_budget(self):
        calls = []
        def adapter(ctx):
            calls.append(ctx["request_id"])
            return {
                "schema_version": CAPABILITY_RESULT_V1,
                "request_id": ctx["request_id"],
                "correlation_id": ctx["correlation_id"],
                "status": "SUCCESS",
                "output_digest": "a" * 64,
                "error_code": None,
                "evidence_refs": ["evidence:sha256:" + "b" * 64],
                "source_revision": ctx["source_revision"],
            }
        registry = RuntimeCapabilityRegistry()
        registry.register(binding(adapter=adapter))
        worker = registry.resolve()["workers"]["memory_knowledge"]
        context = {
            "schema_version": BRAIN_WORKER_CONTEXT_V1,
            "request_id": "req-1",
            "correlation_id": "corr-1",
            "source_revision": SOURCE,
            "required_capabilities": ["memory.search"],
        }
        first = worker(context)
        second = worker(context)
        self.assertEqual(first["status"], "SUCCESS")
        self.assertEqual(second["status"], "BLOCKED")
        self.assertEqual(second["error_code"], "REGISTRY_INVOCATION_BUDGET_EXCEEDED")
        self.assertEqual(calls, ["req-1"])

    def test_unhealthy_adapter_is_blocked_before_dispatch(self):
        calls = []
        registry = RuntimeCapabilityRegistry()
        registry.register(binding(adapter=lambda ctx: calls.append(ctx) or {}, readiness_check=lambda: False))
        resolved = registry.resolve()
        self.assertEqual(resolved["available_capabilities"], {})
        self.assertEqual(resolved["workers"], {})
        entry = next(e for e in resolved["snapshot"]["entries"] if e["capability_id"] == "memory.search")
        self.assertEqual(entry["lifecycle_state"], "BLOCKED")
        self.assertEqual(entry["reason"], "ADAPTER_NOT_READY")
        result = BrainOrchestrator().execute(
            request(["memory.search"]),
            available_capabilities=resolved["available_capabilities"],
            workers=resolved["workers"],
            evidence_verifier=lambda _ref: True,
        )
        self.assertEqual(result["status"], "BLOCKED_CAPABILITY_GAP")
        self.assertEqual(calls, [])

    def test_unknown_domain_and_capability_owner_mismatch_fail_closed(self):
        registry = RuntimeCapabilityRegistry()
        with self.assertRaisesRegex(CapabilityRegistryError, "REGISTRY_DOMAIN_UNKNOWN"):
            registry.register(binding(domain_id="unknown_domain"))
        with self.assertRaisesRegex(CapabilityRegistryError, "REGISTRY_CAPABILITY_OWNER_MISMATCH"):
            registry.register(binding(capability_ids=("tool.execute",)))

    def test_unhashable_or_nontext_capability_ids_fail_closed(self):
        with self.assertRaisesRegex(CapabilityRegistryError, "REGISTRY_CAPABILITY_ID_INVALID"):
            RuntimeCapabilityRegistry().register(binding(capability_ids=(["memory.search"],)))
        with self.assertRaisesRegex(CapabilityRegistryError, "REGISTRY_CAPABILITY_ID_INVALID"):
            RuntimeCapabilityRegistry().register(binding(capability_ids=(None,)))

    def test_only_one_adapter_may_own_a_domain_in_v1(self):
        registry = RuntimeCapabilityRegistry()
        registry.register(binding())
        with self.assertRaisesRegex(CapabilityRegistryError, "REGISTRY_DOMAIN_ALREADY_BOUND"):
            registry.register(binding(capability_ids=("memory.recall",), implementation_id="another.adapter"))

    def test_invalid_timeout_or_revision_rejected(self):
        with self.assertRaisesRegex(CapabilityRegistryError, "REGISTRY_TIMEOUT_INVALID"):
            RuntimeCapabilityRegistry().register(binding(declared_timeout_seconds=float("nan")))
        with self.assertRaisesRegex(CapabilityRegistryError, "REGISTRY_SOURCE_REVISION_INVALID"):
            RuntimeCapabilityRegistry().register(binding(source_revision="not-a-digest"))

    def test_registry_digest_binds_implementation_version_and_side_effect_class(self):
        first = RuntimeCapabilityRegistry()
        first.register(binding(adapter_version="1"))
        second = RuntimeCapabilityRegistry()
        second.register(binding(adapter_version="2"))
        third = RuntimeCapabilityRegistry()
        third.register(binding(side_effect_class="OUTBOUND_PROVIDER_CALL"))
        self.assertNotEqual(first.resolve()["snapshot"]["registry_digest"],
                            second.resolve()["snapshot"]["registry_digest"])
        self.assertNotEqual(first.resolve()["snapshot"]["registry_digest"],
                            third.resolve()["snapshot"]["registry_digest"])

    def test_invalid_worker_context_returns_blocked_without_calling_adapter(self):
        calls = []
        registry = RuntimeCapabilityRegistry()
        registry.register(binding(adapter=lambda ctx: calls.append(ctx) or {}))
        worker = registry.resolve()["workers"]["memory_knowledge"]
        result = worker({
            "schema_version": "WRONG_VERSION",
            "request_id": "req-2",
            "correlation_id": "corr-2",
            "source_revision": SOURCE,
            "required_capabilities": ["memory.search"],
        })
        self.assertEqual(result["schema_version"], CAPABILITY_RESULT_V1)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["error_code"], "REGISTRY_REQUIRED_CAPABILITY_NOT_BOUND")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
