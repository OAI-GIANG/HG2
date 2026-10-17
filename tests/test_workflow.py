"""Tests for HG2's pure task workflow state machine."""
import unittest

from hg.workflow import WorkflowError, create_task, transition_task, validate_task


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
        task = transition_task(task, target_state="SUCCEEDED", actor_id="phone", now=102, result_digest="b" * 64)
        self.assertEqual(task["state"], "SUCCEEDED")
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

    def test_malformed_state_values_fail_closed(self):
        task = self.task()
        task["state"] = ["RUNNING"]
        with self.assertRaisesRegex(WorkflowError, "TASK_STATE_INVALID"):
            validate_task(task)
        with self.assertRaisesRegex(WorkflowError, "TASK_STATE_INVALID"):
            transition_task(self.task(), target_state=["RUNNING"], actor_id="phone", now=101)

    def test_terminal_task_cannot_transition(self):
        task = transition_task(self.task(), target_state="CANCELLED", actor_id="phone", now=101)
        with self.assertRaisesRegex(WorkflowError, "TASK_TERMINAL_STATE"):
            transition_task(task, target_state="PENDING", actor_id="phone", now=102)


if __name__ == "__main__":
    unittest.main()
