"""Tests for HG2's pure and persisted task workflow state machine."""
import tempfile
import unittest

from hg.sqlite_state import SQLiteStateError, SQLiteStateStore
from hg.workflow import WorkflowError, WorkflowService, create_task, transition_task, validate_task


class WorkflowTests(unittest.TestCase):
    def task(self, **overrides):
        args = {
            "task_type": "text.generate",
            "input_digest": "a" * 64,
            "idempotency_key": "task-key-1",
            "now": 100.0,
            "deadline_at": 200.0,
            "max_attempts": 2,
            "task_id": "task-1",
            "correlation_id": "corr-1",
        }
        args.update(overrides)
        return create_task(**args)

    def test_task_lifecycle_success(self):
        task = self.task()
        task = transition_task(task, target_state="RUNNING", actor_id="phone", now=101)
        self.assertEqual(task["attempt"], 1)
        self.assertEqual(task["version"], 2)
        task = transition_task(task, target_state="SUCCEEDED", actor_id="phone", now=102, result_digest="b" * 64)
        self.assertEqual(task["state"], "SUCCEEDED")
        self.assertEqual(task["version"], 3)
        self.assertTrue(validate_task(task))

    def test_retry_is_bounded(self):
        task = self.task(max_attempts=1)
        task = transition_task(task, target_state="RUNNING", actor_id="phone", now=101)
        task = transition_task(task, target_state="FAILED", actor_id="phone", now=102, error_code="PROVIDER_TIMEOUT")
        with self.assertRaisesRegex(WorkflowError, "TASK_ATTEMPT_LIMIT_EXCEEDED"):
            transition_task(task, target_state="PENDING", actor_id="phone", now=103)
        task = self.task()
        task = transition_task(task, target_state="RUNNING", actor_id="phone", now=101)
        task = transition_task(task, target_state="FAILED", actor_id="phone", now=102, error_code="PROVIDER_TIMEOUT")
        task = transition_task(task, target_state="PENDING", actor_id="phone", now=103)
        task = transition_task(task, target_state="RUNNING", actor_id="phone", now=104)
        self.assertEqual(task["attempt"], 2)

    def test_approval_gate_cannot_be_bypassed(self):
        task = self.task()
        task = transition_task(task, target_state="WAITING_APPROVAL", actor_id="phone", now=101, approval_id="approval-1")
        with self.assertRaisesRegex(WorkflowError, "TASK_APPROVAL_NOT_GRANTED"):
            transition_task(task, target_state="PENDING", actor_id="phone", now=102, approval_id="approval-1")
        task = transition_task(task, target_state="PENDING", actor_id="phone", now=102, approval_id="approval-1", approval_status="APPROVED")
        self.assertEqual(task["state"], "PENDING")
        self.assertIsNone(task["approval_id"])

    def test_denial_and_approval_id_mismatch_fail_closed(self):
        task = transition_task(self.task(), target_state="WAITING_APPROVAL", actor_id="phone", now=101, approval_id="approval-1")
        with self.assertRaisesRegex(WorkflowError, "TASK_APPROVAL_ID_MISMATCH"):
            transition_task(task, target_state="PENDING", actor_id="phone", now=102, approval_id="other", approval_status="APPROVED")
        denied = transition_task(task, target_state="FAILED", actor_id="reviewer", now=102, approval_id="approval-1", approval_status="DENIED", error_code="APPROVAL_DENIED")
        self.assertEqual(denied["state"], "FAILED")

    def test_deadline_expiry_and_time_regression(self):
        task = self.task(deadline_at=105)
        expired = transition_task(task, target_state="RUNNING", actor_id="phone", now=105)
        self.assertEqual(expired["state"], "EXPIRED")
        with self.assertRaisesRegex(WorkflowError, "TASK_TIME_REGRESSION"):
            transition_task(self.task(), target_state="RUNNING", actor_id="phone", now=99)

    def test_terminal_task_cannot_transition(self):
        task = transition_task(self.task(), target_state="CANCELLED", actor_id="phone", now=101)
        with self.assertRaisesRegex(WorkflowError, "TASK_TERMINAL_STATE"):
            transition_task(task, target_state="PENDING", actor_id="phone", now=102)

    def test_malformed_state_values_fail_closed(self):
        task = self.task()
        task["state"] = ["RUNNING"]
        with self.assertRaisesRegex(WorkflowError, "TASK_STATE_INVALID"):
            validate_task(task)
        with self.assertRaisesRegex(WorkflowError, "TASK_STATE_INVALID"):
            transition_task(self.task(), target_state=["RUNNING"], actor_id="phone", now=101)

    def test_persisted_workflow_lifecycle(self):
        times = iter((100.0, 101.0, 102.0))
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            service = WorkflowService(store, actor_id="alice", clock=lambda: next(times))
            created = service.create(task_type="text.generate", input_digest="a" * 64, idempotency_key="create-1")
            self.assertEqual(store.get_task(created["task_id"]), created)
            running = service.transition(created["task_id"], target_state="RUNNING", expected_version=1)
            self.assertEqual(running["version"], 2)
            succeeded = service.transition(created["task_id"], target_state="SUCCEEDED", expected_version=2, result_digest="b" * 64)
            self.assertEqual(succeeded["state"], "SUCCEEDED")
            self.assertEqual(store.audit_export()["state"]["tasks"][created["task_id"]], succeeded)
            self.assertTrue(store.verify()["ok"])

    def test_stale_workflow_version_is_rejected(self):
        times = iter((100.0, 101.0))
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            service = WorkflowService(store, actor_id="alice", clock=lambda: next(times))
            task = service.create(task_type="text.generate", input_digest="a" * 64, idempotency_key="create-2")
            service.transition(task["task_id"], target_state="RUNNING", expected_version=1)
            before = store.audit_export()["events"]
            with self.assertRaisesRegex(WorkflowError, "TASK_VERSION_CONFLICT"):
                service.transition(task["task_id"], target_state="CANCELLED", expected_version=1)
            self.assertEqual(store.audit_export()["events"], before)
            self.assertTrue(store.verify()["ok"])

    def test_persisted_transition_retry_is_idempotent(self):
        times = iter((100.0, 101.0))
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            service = WorkflowService(store, actor_id="alice", clock=lambda: next(times))
            task = service.create(task_type="text.generate", input_digest="a" * 64, idempotency_key="create-3")
            first = service.transition(task["task_id"], target_state="RUNNING", expected_version=1, idempotency_key="run-1")
            second = service.transition(task["task_id"], target_state="RUNNING", expected_version=1, idempotency_key="run-1")
            self.assertEqual(first, second)
            self.assertEqual(store.audit_export()["events"], 3)
            self.assertTrue(store.verify()["ok"])

    def test_direct_invalid_transition_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            service = WorkflowService(store, actor_id="alice", clock=lambda: 100.0)
            task = service.create(task_type="text.generate", input_digest="a" * 64, idempotency_key="create-4")
            before = store.audit_export()["events"]
            bad_task = dict(task)
            bad_task.update(state="RUNNING", version=9, attempt=1, updated_at=101.0)
            payload = {
                "task": bad_task,
                "transition": {
                    "from_state": "PENDING", "requested_state": "RUNNING",
                    "approval_id": None, "approval_status": None, "reason": "",
                },
            }
            with self.assertRaises((WorkflowError, SQLiteStateError)):
                store.emit("workflow.task.transitioned", payload, actor_id="alice", idempotency_key="bad-transition")
            self.assertEqual(store.audit_export()["events"], before)
            self.assertEqual(store.get_task(task["task_id"]), task)
            self.assertTrue(store.verify()["ok"])


if __name__ == "__main__":
    unittest.main()
