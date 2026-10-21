"""Conformance checks for the read-only RuntimeStateBoundary contract.

All storage is temporary and synthetic. These tests do not open runtime state.
"""
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from hg.auth import BearerAuthenticator
from hg.durable_transactions import DurableTransactionStore
from hg.history import StateStore
from hg.runtime_state_boundary import (
    CONTRACT_VERSION,
    RuntimeStateBoundary,
    inspect_runtime_state_boundary,
)
from hg.sqlite_state import SQLiteStateStore
from hg.sync import SyncContext
from hg.sync_dispatcher import SyncDispatcher
from hg.workflow_store_adapter import CanonicalWorkflowAdapter
from tests._support import authorized_domain_emit


class NoopTransport:
    def send_event(self, event):
        return {
            "status": "ACK",
            "event_id": event["event_id"],
            "event_digest": event["record_digest"],
            "remote_cursor": 1,
        }


class RuntimeStateBoundaryTests(unittest.TestCase):
    def principal(self, scopes, name="boundary-test"):
        token = "token-" + name
        return BearerAuthenticator(token, set(scopes), principal_id=name).authenticate("Bearer " + token)

    def test_file_store_satisfies_read_only_contract_and_identity_survives_reopen(self):
        with tempfile.TemporaryDirectory() as td:
            path = str(Path(td) / "file-state")
            store = StateStore(path)
            store.emit("boundary.fixture", {"value": "synthetic"}, event_id="boundary-event")
            before = inspect_runtime_state_boundary(store)
            self.assertIsInstance(store, RuntimeStateBoundary)
            self.assertTrue(before["ok"])
            self.assertEqual(before["schema_version"], CONTRACT_VERSION)
            self.assertTrue(before["read_only"])
            self.assertFalse(before["migration_performed"])
            runtime_id = store.runtime_id
            reopened = StateStore(path)
            after = inspect_runtime_state_boundary(reopened)
            self.assertEqual(after["runtime_id"], runtime_id)
            self.assertEqual(after["events"], before["events"])
            self.assertEqual(sum(e["event_id"] == "boundary-event" for e in reopened.replay()), 1)

    def test_sqlite_store_satisfies_read_only_contract_and_identity_survives_reopen(self):
        with tempfile.TemporaryDirectory() as td:
            store = SQLiteStateStore(str(Path(td) / "sqlite-state"))
            authorized_domain_emit(
                store, "session.created", {"session_id": "synthetic-session"},
                subject_id="fixture", action="session.create", idempotency_key="boundary-idem",
            )
            before = inspect_runtime_state_boundary(store)
            self.assertIsInstance(store, RuntimeStateBoundary)
            self.assertTrue(before["ok"])
            runtime_id = store.runtime_id
            store.close()
            reopened = SQLiteStateStore(str(Path(td) / "sqlite-state"))
            after = inspect_runtime_state_boundary(reopened)
            self.assertEqual(after["runtime_id"], runtime_id)
            self.assertEqual(after["events"], before["events"])
            self.assertTrue(reopened.verify()["ok"])
            reopened.close()

    def test_sync_context_and_runtime_share_one_file_store(self):
        with tempfile.TemporaryDirectory() as td:
            state = str(Path(td) / "state")
            spool = str(Path(td) / "spool")
            store = StateStore(state)
            context = SyncContext("synthetic-context", state, spool, store=store)
            self.assertIs(context.store, store)
            self.assertEqual(inspect_runtime_state_boundary(context.store)["runtime_id"], store.runtime_id)
            with self.assertRaisesRegex(ValueError, "directory mismatch"):
                SyncContext("wrong-context", str(Path(td) / "other-state"), spool, store=store)

    def test_sqlite_consumers_share_identity_but_keep_distinct_roles(self):
        with tempfile.TemporaryDirectory() as td:
            store = SQLiteStateStore(str(Path(td) / "state"))
            principal = self.principal(
                {"workflow.task.create", "workflow.task.transition", "sync.outbox.attempt", "sync.outbox.acknowledge"}
            )
            workflow = CanonicalWorkflowAdapter(
                store, principal=principal, actor_id=principal.principal_id, clock=lambda: 100.0
            )
            dispatcher = SyncDispatcher(store, NoopTransport(), principal=principal)
            self.assertIs(workflow.store, dispatcher.store)
            self.assertEqual(workflow.runtime_id, dispatcher.store.runtime_id)
            self.assertTrue(workflow.verify_contract()["ok"])
            self.assertTrue(inspect_runtime_state_boundary(store)["ok"])
            store.close()

    def test_durable_transaction_ledger_is_not_misclassified_as_runtime_state(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = DurableTransactionStore(str(Path(td) / "transactions.sqlite3"))
            self.assertFalse(isinstance(ledger, RuntimeStateBoundary))
            integrity = ledger.verify_state_integrity()
            self.assertIsInstance(integrity, dict)
            self.assertTrue(integrity.get("ok"))

    def test_synthetic_file_store_backup_restore_preserves_hashes_and_replay(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "source"
            backup = Path(td) / "isolated-backup"
            source.mkdir()
            store = StateStore(str(source))
            store.emit("backup.fixture", {"payload": "synthetic-only"}, event_id="backup-fixture-1")
            before = inspect_runtime_state_boundary(store)
            store_files = [p for p in source.iterdir() if p.is_file()]
            hashes_before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in store_files}
            shutil.copytree(source, backup)
            hashes_copy = {p.name: hashlib.sha256((backup / p.name).read_bytes()).hexdigest() for p in store_files}
            self.assertEqual(hashes_copy, hashes_before)
            restored = StateStore(str(backup))
            after = inspect_runtime_state_boundary(restored)
            self.assertEqual(after["runtime_id"], before["runtime_id"])
            self.assertEqual(after["events"], before["events"])
            self.assertTrue(restored.verify()["ok"])
            self.assertEqual(sum(e["event_id"] == "backup-fixture-1" for e in restored.replay()), 1)
            self.assertEqual({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in store_files}, hashes_before)

    def test_contract_fails_closed_on_unverified_or_mismatched_identity(self):
        class BadStore:
            runtime_id = "runtime-a"
            def replay(self): return []
            def verify(self): return {"ok": False, "events": 0}
            def audit_export(self): return {"runtime_id": "runtime-a", "events": 0}
        with self.assertRaisesRegex(ValueError, "INTEGRITY_NOT_VERIFIED"):
            inspect_runtime_state_boundary(BadStore())

        class MismatchedStore(BadStore):
            def verify(self): return {"ok": True, "events": 0}
            def audit_export(self): return {"runtime_id": "runtime-b", "events": 0}
        with self.assertRaisesRegex(ValueError, "EXPORT_IDENTITY_MISMATCH"):
            inspect_runtime_state_boundary(MismatchedStore())


if __name__ == "__main__":
    unittest.main()
