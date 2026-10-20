import tempfile
import unittest
from pathlib import Path

from hg.auth import BearerAuthenticator
from hg.sqlite_state import SQLiteStateError, SQLiteStateStore
from hg.workflow import WorkflowService, WorkflowError
from hg.workflow_store_adapter import CanonicalWorkflowAdapter, WorkflowStoreContractError
from hg.history import StateStore


class CanonicalWorkflowAdapterTests(unittest.TestCase):
    def principal(self):
        return BearerAuthenticator(
            "workflow-adapter-test",
            {"workflow.task.create", "workflow.task.transition"},
            principal_id="alice",
        ).authenticate("Bearer workflow-adapter-test")

    def make_adapter(self, directory, clock=lambda: 100.0):
        # The store and service share the same deterministic test clock without exhausting
        # an iterator after repeated event creation/commit timestamps.
        store = SQLiteStateStore(directory, clock=clock)
        return store, CanonicalWorkflowAdapter(
            store, principal=self.principal(), actor_id="alice", clock=clock
        )

    def test_requires_one_canonical_transactional_store(self):
        with tempfile.TemporaryDirectory() as td:
            legacy = StateStore(str(Path(td) / "legacy"))
            with self.assertRaisesRegex(
                WorkflowStoreContractError, "WORKFLOW_STORE_MUST_BE_SQLITE_STATE_STORE"
            ):
                CanonicalWorkflowAdapter(
                    legacy, principal=self.principal(), actor_id="alice", clock=lambda: 100
                )

    def test_task_lifecycle_and_replay_projection_are_consistent(self):
        tick = [100.0]
        def clock():
            tick[0] += 1.0
            return tick[0]
        with tempfile.TemporaryDirectory() as td:
            store, adapter = self.make_adapter(td, clock=clock)
            created = adapter.create(
                task_type="evolution.evaluate", input_digest="a" * 64,
                idempotency_key="create-1", task_id="task-1",
                correlation_id="corr-1",
            )
            self.assertEqual(created["state"], "PENDING")
            running = adapter.transition(
                created["task_id"], target_state="RUNNING", expected_version=1,
                idempotency_key="run-1",
            )
            result = adapter.transition(
                created["task_id"], target_state="SUCCEEDED", expected_version=2,
                result_digest="b" * 64, idempotency_key="finish-1",
            )
            self.assertEqual(result["state"], "SUCCEEDED")
            self.assertEqual(adapter.get("task-1"), result)
            contract = adapter.verify_contract()
            self.assertTrue(contract["ok"])
            self.assertEqual(contract["tasks"], 1)
            self.assertEqual(contract["events"], store.verify()["events"])
            self.assertFalse(contract["runtime_cutover_performed"])
            store.close()

    def test_restart_keeps_one_canonical_projection(self):
        with tempfile.TemporaryDirectory() as td:
            store, adapter = self.make_adapter(td)
            created = adapter.create(
                task_type="evolution.evaluate", input_digest="a" * 64,
                idempotency_key="create-restart", task_id="task-restart",
                correlation_id="corr-restart",
            )
            store.close()
            reopened = SQLiteStateStore(td)
            restarted = CanonicalWorkflowAdapter(
                reopened, principal=self.principal(), actor_id="alice", clock=lambda: 101
            )
            self.assertEqual(restarted.get(created["task_id"]), created)
            self.assertTrue(restarted.verify_contract()["ok"])
            reopened.close()

    def test_idempotency_retry_does_not_duplicate_task_event(self):
        with tempfile.TemporaryDirectory() as td:
            store, adapter = self.make_adapter(td)
            args = dict(
                task_type="evolution.evaluate", input_digest="a" * 64,
                idempotency_key="one-create", task_id="task-idem",
                correlation_id="corr-idem",
            )
            first = adapter.create(**args)
            second = adapter.create(**args)
            self.assertEqual(first, second)
            self.assertEqual(store.audit_export()["events"], 2)
            store.close()

    def test_missing_scope_fails_without_state_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            store = SQLiteStateStore(td)
            principal = BearerAuthenticator(
                "create-only", {"workflow.task.create"}, principal_id="alice"
            ).authenticate("Bearer create-only")
            adapter = CanonicalWorkflowAdapter(
                store, principal=principal, actor_id="alice", clock=lambda: 100
            )
            task = adapter.create(
                task_type="evolution.evaluate", input_digest="a" * 64,
                idempotency_key="create-only",
            )
            before = store.audit_export()["events"]
            with self.assertRaisesRegex(WorkflowError, "ACTION_NOT_AUTHORIZED"):
                adapter.transition(task["task_id"], target_state="RUNNING", expected_version=1)
            self.assertEqual(store.audit_export()["events"], before)
            store.close()

    def test_corrupt_state_cannot_open_adapter(self):
        with tempfile.TemporaryDirectory() as td:
            store = SQLiteStateStore(td)
            store.close()
            import sqlite3
            db = sqlite3.connect(str(Path(td) / "hg2-state.sqlite3"))
            db.execute("UPDATE metadata SET value=? WHERE key='head_digest'", ("f" * 64,))
            db.commit()
            db.close()
            with self.assertRaises(SQLiteStateError):
                SQLiteStateStore(td)

    def test_replay_checker_rejects_corrupted_projection(self):
        with tempfile.TemporaryDirectory() as td:
            store, adapter = self.make_adapter(td)
            task = adapter.create(
                task_type="evolution.evaluate", input_digest="a" * 64,
                idempotency_key="create-corrupt", task_id="task-corrupt",
                correlation_id="corr-corrupt",
            )
            store._conn.execute(
                "UPDATE tasks SET task_json=? WHERE task_id=?",
                ('{"broken":true}', task["task_id"]),
            )
            with self.assertRaises((WorkflowStoreContractError, SQLiteStateError)):
                adapter.verify_contract()
            store.close()


if __name__ == "__main__":
    unittest.main()
