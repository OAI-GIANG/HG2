"""Integration checks for the local RDC adapter at the registry/worker boundary.

No HTTP API or provider behavior is changed by these tests. They prove the
registered local operation passes registry dispatch before invoking RDC admission
and the POSIX supervisor, while failures remain fail-closed.
"""
import hashlib
import os
import sys
import unittest

from hg.capability_registry import RuntimeCapabilityRegistry, RuntimeDomainBinding
from hg.contracts import BRAIN_WORKER_CONTEXT_V1, CAPABILITY_RESULT_V1
from hg.local_process_rdc_adapter import LocalProcessOperation, PosixLocalRdcAdapter
from hg.process_supervisor import PosixProcessSupervisor
from hg.remote_desktop_commander import REMOTE_COMMAND_SCHEMA, RemoteOperation
from hg.brain_orchestrator import BRANCH_CAPABILITIES

SOURCE = hashlib.sha256(b"hg2-phone-rdc-integration").hexdigest()
ADAPTER_ID = "hg.rdc.local.posix"
ADAPTER_VERSION = "1"
TARGET = "phone-termux-primary"


@unittest.skipUnless(os.name == "posix" and hasattr(os, "killpg"),
                     "requires POSIX process-group signaling")
class RdcRuntimeWiringTests(unittest.TestCase):
    def _adapter(self, *, argv_builder=None, timeout=2, operation_id="phone.status"):
        operation = RemoteOperation(
            operation_id=operation_id,
            required_capabilities=("remote.desktop.status",),
            risk_class="LOCAL_READ_ONLY",
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
        )
        return PosixLocalRdcAdapter(
            target_id=TARGET,
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            operations=(LocalProcessOperation(
                operation,
                argv_builder or (lambda _args: [sys.executable, "-c", "print('registry-to-supervisor-ok')"]),
                timeout,
            ),),
            supervisor=PosixProcessSupervisor(termination_grace_seconds=0.05),
        ), operation

    def _command(self, operation_id="phone.status", **overrides):
        value = {
            "schema_version": REMOTE_COMMAND_SCHEMA,
            "command_id": "cmd-rdc-int-1",
            "request_id": "req-rdc-int-1",
            "target_id": TARGET,
            "operation_id": operation_id,
            "arguments": {"detail": "basic"},
            "required_capabilities": ["remote.desktop.status"],
            "risk_class": "LOCAL_READ_ONLY",
            "idempotency_key": "idem-rdc-int-1",
            "source_revision": SOURCE,
            "approval_ref": None,
        }
        value.update(overrides)
        return value

    def _registry(self, adapter, *, readiness=lambda: True):
        registry = RuntimeCapabilityRegistry()
        registry.register(RuntimeDomainBinding(
            domain_id="tools_execution",
            capability_ids=("tool.execute",),
            implementation_id="hg.local_process_rdc_adapter.PosixLocalRdcAdapter",
            adapter_version="1",
            input_contract="HG_RDC_LOCAL_COMMAND_V1",
            output_contract=CAPABILITY_RESULT_V1,
            authority_contract="registered_local_operation_plus_rdc_capability_admission",
            side_effect_class="LOCAL_READ_ONLY",
            declared_timeout_seconds=3.0,
            # The worker itself below directly calls the supervisor, and the
            # adapter reports timeout, but the registry contract does not yet
            # universally enforce timeout/cancel for arbitrary bound callables.
            hard_timeout_enforced=False,
            max_invocations_per_request=1,
            lifecycle_state="TESTED",
            source_revision=SOURCE,
            evidence_verifier_id="local-rdc-integration-tests-v1",
            adapter=lambda context: self._dispatch(adapter, context),
            readiness_check=readiness,
        ))
        return registry

    def _dispatch(self, adapter, context):
        command = context.get("rdc_command")
        capabilities = context.get("granted_rdc_capabilities", set())
        result = adapter.execute(command, granted_capabilities=capabilities)
        from hg.contracts import canonical_digest
        digest = canonical_digest({
            "status": result.get("status"),
            "reason_code": result.get("reason_code"),
            "result": result.get("result"),
        })
        return {
            "schema_version": CAPABILITY_RESULT_V1,
            "request_id": context["request_id"],
            "correlation_id": context["correlation_id"],
            "status": "SUCCESS" if result.get("status") == "COMPLETED" else "BLOCKED",
            "output_digest": digest,
            "error_code": None if result.get("status") == "COMPLETED" else result.get("reason_code"),
            "evidence_refs": [],
            "source_revision": context["source_revision"],
        }

    def _context(self, command, grants):
        return {
            "schema_version": BRAIN_WORKER_CONTEXT_V1,
            "request_id": "req-rdc-int-1",
            "correlation_id": "corr-rdc-int-1",
            "source_revision": SOURCE,
            "branch_id": "tools_execution",
            "required_capabilities": ["tool.execute"],
            "rdc_command": command,
            "granted_rdc_capabilities": grants,
        }

    def test_registry_dispatch_reaches_admitted_local_operation(self):
        adapter, _ = self._adapter()
        resolved = self._registry(adapter).resolve()
        self.assertEqual(resolved["available_capabilities"]["tools_execution"], {"tool.execute"})
        worker = resolved["workers"]["tools_execution"]
        result = worker(self._context(
            self._command(), {"remote.desktop.status"}
        ))
        self.assertEqual(result["status"], "SUCCESS")
        self.assertIsNotNone(result["output_digest"])

    def test_registry_worker_blocks_if_rdc_capability_missing(self):
        adapter, _ = self._adapter()
        resolved = self._registry(adapter).resolve()
        result = resolved["workers"]["tools_execution"](
            self._context(self._command(), set())
        )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["error_code"], "REMOTE_CAPABILITY_NOT_GRANTED")

    def test_unhealthy_registry_adapter_is_not_exposed(self):
        adapter, _ = self._adapter()
        resolved = self._registry(adapter, readiness=lambda: False).resolve()
        self.assertNotIn("tools_execution", resolved["workers"])
        item = next(x for x in resolved["snapshot"]["entries"] if x["capability_id"] == "tool.execute")
        self.assertFalse(item["ready"])

    def test_registry_dispatch_reports_local_timeout_as_blocked_outcome(self):
        adapter, _ = self._adapter(
            argv_builder=lambda _args: [sys.executable, "-c", "import time; time.sleep(20)"],
            timeout=0.1,
            operation_id="phone.slow-status",
        )
        resolved = self._registry(adapter).resolve()
        result = resolved["workers"]["tools_execution"](
            self._context(self._command(operation_id="phone.slow-status"), {"remote.desktop.status"})
        )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["error_code"], "LOCAL_RDC_PROCESS_TIMED_OUT")

    def test_registered_operation_that_returns_shell_string_is_blocked(self):
        adapter, _ = self._adapter(
            argv_builder=lambda _args: "echo must-not-execute",
            operation_id="phone.bad-argv",
        )
        resolved = self._registry(adapter).resolve()
        result = resolved["workers"]["tools_execution"](
            self._context(self._command(operation_id="phone.bad-argv"), {"remote.desktop.status"})
        )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["error_code"], "PROCESS_ARGV_SEQUENCE_REQUIRED")


if __name__ == "__main__":
    unittest.main()
