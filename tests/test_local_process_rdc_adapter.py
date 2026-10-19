import hashlib
import os
import sys
import unittest

from hg.local_process_rdc_adapter import LocalProcessOperation, PosixLocalRdcAdapter
from hg.process_supervisor import PosixProcessSupervisor
from hg.remote_desktop_commander import REMOTE_COMMAND_SCHEMA, RemoteOperation


SOURCE = hashlib.sha256(b"local-rdc-adapter-test").hexdigest()
ADAPTER_ID = "hg.rdc.local.posix"
ADAPTER_VERSION = "1"


def command(**overrides):
    value = {
        "schema_version": REMOTE_COMMAND_SCHEMA,
        "command_id": "cmd-local-1",
        "request_id": "req-local-1",
        "target_id": "phone-termux-primary",
        "operation_id": "device.status",
        "arguments": {"detail": "basic"},
        "required_capabilities": ["remote.desktop.status"],
        "risk_class": "LOCAL_READ_ONLY",
        "idempotency_key": "idem-local-1",
        "source_revision": SOURCE,
        "approval_ref": None,
    }
    value.update(overrides)
    return value


@unittest.skipUnless(os.name == "posix" and hasattr(os, "killpg"),
                     "requires POSIX process-group signaling")
class LocalProcessRdcAdapterTests(unittest.TestCase):
    def setUp(self):
        op = RemoteOperation(
            operation_id="device.status",
            required_capabilities=("remote.desktop.status",),
            risk_class="LOCAL_READ_ONLY",
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
        )
        self.adapter = PosixLocalRdcAdapter(
            target_id="phone-termux-primary",
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            operations=(LocalProcessOperation(
                operation=op,
                argv_builder=lambda _args: [sys.executable, "-c", "print('phone-runtime-ok')"],
                timeout_seconds=2,
            ),),
        )

    def test_admitted_registered_operation_executes_locally(self):
        result = self.adapter.execute(
            command(), granted_capabilities={"remote.desktop.status"}
        )
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["result"]["stdout"].strip(), "phone-runtime-ok")
        self.assertEqual(result["decision"]["adapter_id"], ADAPTER_ID)

    def test_target_mismatch_fails_closed_without_execution(self):
        result = self.adapter.execute(
            command(target_id="unrecognized-target"),
            granted_capabilities={"remote.desktop.status"},
        )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason_code"], "LOCAL_RDC_TARGET_MISMATCH")
        self.assertIsNone(result["result"])

    def test_missing_capability_fails_closed_without_execution(self):
        result = self.adapter.execute(command(), granted_capabilities=set())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason_code"], "REMOTE_CAPABILITY_NOT_GRANTED")
        self.assertIsNone(result["result"])

    def test_unregistered_operation_fails_closed(self):
        result = self.adapter.execute(
            command(operation_id="device.unregistered"),
            granted_capabilities={"remote.desktop.status"},
        )
        self.assertEqual(result["reason_code"], "LOCAL_RDC_OPERATION_UNREGISTERED")

    def test_argv_builder_cannot_inject_raw_shell_string(self):
        # Build a second adapter whose trusted operation accidentally returns a
        # shell string. The supervisor rejects it rather than interpreting it.
        op = RemoteOperation(
            operation_id="device.bad-builder",
            required_capabilities=("remote.desktop.status",),
            risk_class="LOCAL_READ_ONLY",
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
        )
        adapter = PosixLocalRdcAdapter(
            target_id="phone-termux-primary", adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            operations=(LocalProcessOperation(op, lambda _args: "echo unsafe", 1),),
        )
        result = adapter.execute(
            command(operation_id=op.operation_id),
            granted_capabilities={"remote.desktop.status"},
        )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason_code"], "PROCESS_ARGV_SEQUENCE_REQUIRED")

    def test_high_risk_operation_requires_verified_approval(self):
        op = RemoteOperation(
            operation_id="device.write",
            required_capabilities=("remote.desktop.write",),
            risk_class="LOCAL_WRITE",
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
        )
        adapter = PosixLocalRdcAdapter(
            target_id="phone-termux-primary", adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            operations=(LocalProcessOperation(
                op, lambda _args: [sys.executable, "-c", "print('should-not-run')"], 1
            ),),
        )
        value = command(
            operation_id="device.write",
            required_capabilities=["remote.desktop.write"],
            risk_class="LOCAL_WRITE",
            approval_ref="approval-1",
        )
        result = adapter.execute(value, granted_capabilities={"remote.desktop.write"})
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason_code"], "REMOTE_APPROVAL_REQUIRED")
        self.assertIsNone(result["result"])

    def test_local_timeout_is_reported_as_timed_out(self):
        op = RemoteOperation(
            operation_id="device.slow-status",
            required_capabilities=("remote.desktop.status",),
            risk_class="LOCAL_READ_ONLY",
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
        )
        adapter = PosixLocalRdcAdapter(
            target_id="phone-termux-primary", adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            operations=(LocalProcessOperation(
                op, lambda _args: [sys.executable, "-c", "import time; time.sleep(20)"], 0.1
            ),),
            supervisor=PosixProcessSupervisor(termination_grace_seconds=0.05),
        )
        result = adapter.execute(
            command(operation_id="device.slow-status"),
            granted_capabilities={"remote.desktop.status"},
        )
        self.assertEqual(result["status"], "TIMED_OUT")
        self.assertEqual(result["reason_code"], "LOCAL_RDC_PROCESS_TIMED_OUT")
        self.assertNotEqual(result["result"]["returncode"], 0)


if __name__ == "__main__":
    unittest.main()
