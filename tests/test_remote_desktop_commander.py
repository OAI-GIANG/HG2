import hashlib
import unittest

from hg.remote_desktop_commander import (
    REMOTE_COMMAND_SCHEMA, RemoteCommandError, RemoteDesktopCommander,
    RemoteOperation, validate_remote_command,
)

SOURCE = hashlib.sha256(b"rdc-source").hexdigest()


def command(**overrides):
    value = {
        "schema_version": REMOTE_COMMAND_SCHEMA,
        "command_id": "cmd-1",
        "request_id": "req-1",
        "target_id": "phone-primary",
        "operation_id": "desktop.status",
        "arguments": {"detail": "basic"},
        "required_capabilities": ["remote.desktop.status"],
        "risk_class": "LOCAL_READ_ONLY",
        "idempotency_key": "idem-1",
        "source_revision": SOURCE,
        "approval_ref": None,
    }
    value.update(overrides)
    return value


def status_operation(**overrides):
    args = {
        "operation_id": "desktop.status",
        "required_capabilities": ("remote.desktop.status",),
        "risk_class": "LOCAL_READ_ONLY",
        "adapter_id": "hg.rdc.status",
        "adapter_version": "1",
    }
    args.update(overrides)
    return RemoteOperation(**args)


class RemoteDesktopCommanderTests(unittest.TestCase):
    def test_read_only_operation_can_be_prepared_as_dry_run(self):
        commander = RemoteDesktopCommander((status_operation(),))
        result = commander.prepare(command(), granted_capabilities={"remote.desktop.status"})
        self.assertTrue(result["ok"])
        self.assertFalse(result["executable"])
        self.assertEqual(result["reason_code"], "REMOTE_DRY_RUN_VALIDATED")
        self.assertEqual(len(result["argument_sha256"]), 64)
        self.assertEqual(len(result["decision_digest"]), 64)
        self.assertEqual(result["adapter_id"], "hg.rdc.status")
        self.assertEqual(result["adapter_version"], "1")
        self.assertNotIn("arguments", result)
        # The decision names the admitted adapter but does not call it.
        self.assertFalse(result["executable"])

    def test_unregistered_operation_fails_closed(self):
        result = RemoteDesktopCommander().prepare(
            command(), granted_capabilities={"remote.desktop.status"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason_code"], "REMOTE_OPERATION_UNREGISTERED")

    def test_capability_not_granted_blocks(self):
        commander = RemoteDesktopCommander((status_operation(),))
        result = commander.prepare(command(), granted_capabilities=set())
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason_code"], "REMOTE_CAPABILITY_NOT_GRANTED")
        self.assertEqual(result["adapter_id"], "hg.rdc.status")

    def test_raw_shell_operations_are_forbidden(self):
        with self.assertRaisesRegex(RemoteCommandError, "REMOTE_RAW_SHELL_OPERATION_FORBIDDEN"):
            validate_remote_command(command(operation_id="shell.exec"))

    def test_argument_keys_that_enable_raw_shell_or_secret_injection_are_forbidden(self):
        with self.assertRaisesRegex(RemoteCommandError, "REMOTE_COMMAND_SECRET_OR_RAW_SHELL_FIELD_FORBIDDEN"):
            validate_remote_command(command(arguments={"shell_command": "anything"}))
        with self.assertRaisesRegex(RemoteCommandError, "REMOTE_COMMAND_SECRET_OR_RAW_SHELL_FIELD_FORBIDDEN"):
            validate_remote_command(command(arguments={"options": {"api_key": "x"}}))

    def test_high_risk_needs_bound_approval_verifier(self):
        op = RemoteOperation(
            operation_id="desktop.write_note",
            required_capabilities=("remote.desktop.write",),
            risk_class="LOCAL_WRITE",
            adapter_id="hg.rdc.write-note",
            adapter_version="1",
        )
        risky = command(
            operation_id=op.operation_id,
            arguments={"note_id": "n-1", "text_digest": "a" * 64},
            required_capabilities=list(op.required_capabilities),
            risk_class=op.risk_class,
            approval_ref="approval-1",
        )
        commander = RemoteDesktopCommander((op,))
        result = commander.prepare(risky, granted_capabilities={"remote.desktop.write"}, dry_run=False)
        self.assertFalse(result["ok"])
        self.assertFalse(result["executable"])
        self.assertEqual(result["reason_code"], "REMOTE_APPROVAL_REQUIRED")

    def test_approval_verifier_receives_exact_command_digest_binding(self):
        op = RemoteOperation(
            operation_id="desktop.write_note",
            required_capabilities=("remote.desktop.write",),
            risk_class="LOCAL_WRITE",
            adapter_id="hg.rdc.write-note",
            adapter_version="1",
        )
        risky = command(
            operation_id=op.operation_id,
            arguments={"note_id": "n-1", "text_digest": "a" * 64},
            required_capabilities=list(op.required_capabilities),
            risk_class=op.risk_class,
            approval_ref="approval-1",
        )
        seen = []
        def verifier(statement):
            seen.append(dict(statement))
            return (
                statement["approval_ref"] == "approval-1"
                and statement["operation_id"] == "desktop.write_note"
                and statement["arguments_sha256"] == __import__("hg.contracts", fromlist=["canonical_digest"]).canonical_digest(risky["arguments"])
            )
        commander = RemoteDesktopCommander((op,))
        result = commander.prepare(
            risky, granted_capabilities={"remote.desktop.write"},
            approval_verifier=verifier, dry_run=False,
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["executable"])
        self.assertEqual(result["reason_code"], "REMOTE_COMMAND_ADMITTED_TO_ADAPTER")
        self.assertEqual(len(seen), 1)
        changed = dict(risky)
        changed["arguments"] = {"note_id": "n-2", "text_digest": "b" * 64}
        result2 = commander.prepare(
            changed, granted_capabilities={"remote.desktop.write"},
            approval_verifier=lambda _statement: False, dry_run=False,
        )
        self.assertFalse(result2["executable"])
        self.assertEqual(result2["reason_code"], "REMOTE_APPROVAL_UNVERIFIED")

    def test_destructive_risk_requires_explicit_feature_switch_and_verifier(self):
        op = RemoteOperation(
            operation_id="desktop.delete_item",
            required_capabilities=("remote.desktop.delete",),
            risk_class="DESTRUCTIVE",
            adapter_id="hg.rdc.delete",
            adapter_version="1",
        )
        risky = command(
            operation_id=op.operation_id,
            arguments={"item_id": "item-1"},
            required_capabilities=list(op.required_capabilities),
            risk_class=op.risk_class,
            approval_ref="approval-1",
        )
        commander = RemoteDesktopCommander((op,))
        result = commander.prepare(
            risky, granted_capabilities={"remote.desktop.delete"},
            approval_verifier=lambda _statement: True, allow_destructive=False, dry_run=False,
        )
        self.assertFalse(result["executable"])
        self.assertEqual(result["reason_code"], "REMOTE_DESTRUCTIVE_ACTION_DISABLED")

    def test_duplicate_operation_registration_fails_closed(self):
        with self.assertRaisesRegex(RemoteCommandError, "REMOTE_OPERATION_DUPLICATE"):
            RemoteDesktopCommander((status_operation(), status_operation()))


if __name__ == "__main__":
    unittest.main()
