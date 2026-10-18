"""Tests for persisted, scoped approval requests and decisions."""
import tempfile
import unittest

from hg.policy import ApprovalService, PolicyError, authorize_with_approvals
from hg.sqlite_state import SQLiteStateError, SQLiteStateStore
from hg.auth import BearerAuthenticator


class ApprovalServiceTests(unittest.TestCase):
    def principal(self, subject_id="alice", scopes=None):
        selected = scopes if scopes is not None else {"policy.approval.request", "policy.approval.vote", "session.create"}
        token = "approval-test:" + subject_id
        return BearerAuthenticator(token, selected, principal_id=subject_id).authenticate("Bearer " + token)

    def test_approval_mutations_fail_closed_without_sealed_principal(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            before = store.audit_export()["last_seq"]
            service = ApprovalService(store, clock=lambda: 100.0)
            with self.assertRaisesRegex(PolicyError, "AUTHENTICATION_REQUIRED"):
                service.request(principal_id="alice", action="session.create", resource_id="session-A", request_digest="a" * 64, idempotency_key="denied-request")
            self.assertEqual(store.audit_export()["last_seq"], before)
            principal = self.principal()
            service = ApprovalService(store, clock=lambda: 100.0, principal=principal)
            request = service.request(principal_id="alice", action="session.create", resource_id="session-A", request_digest="b" * 64, idempotency_key="allowed-request")
            wrong = self.principal("reviewer", {"policy.approval.request"})
            voter = ApprovalService(store, clock=lambda: 101.0, principal=wrong)
            before_decision = store.audit_export()["last_seq"]
            with self.assertRaisesRegex(PolicyError, "ACTION_NOT_AUTHORIZED"):
                voter.decide(request["approval_id"], decision="APPROVED", approver_id="reviewer", expected_version=1)
            impersonator = ApprovalService(store, clock=lambda: 101.0, principal=self.principal("alice", {"policy.approval.vote"}))
            with self.assertRaisesRegex(PolicyError, "APPROVER_PRINCIPAL_MISMATCH"):
                impersonator.decide(request["approval_id"], decision="APPROVED", approver_id="reviewer", expected_version=1)
            self.assertEqual(store.audit_export()["last_seq"], before_decision)
            self.assertEqual(store.get_approval(request["approval_id"])["status"], "PENDING")

    def test_request_approve_and_authorize_exact_scope(self):
        times = iter((100.0, 101.0))
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            service = ApprovalService(store, clock=lambda: next(times), principal=self.principal())
            request = service.request(
                principal_id="alice", action="session.create", resource_id="session-A",
                request_digest="a" * 64, idempotency_key="request-1",
            )
            self.assertEqual(store.get_approval(request["approval_id"]), request)
            reviewer = ApprovalService(store, clock=lambda: next(times), principal=self.principal("reviewer", {"policy.approval.vote"}))
            approved = reviewer.decide(
                request["approval_id"], decision="APPROVED", approver_id="reviewer",
                expected_version=1, reason="checked",
            )
            self.assertEqual(approved["status"], "APPROVED")
            self.assertEqual(approved["version"], 2)
            approvals = store.audit_export()["state"]["approvals"].values()
            self.assertTrue(authorize_with_approvals("alice", "session.create", approvals, now=102, resource="session-A", request_digest="a" * 64).allowed)
            self.assertEqual(authorize_with_approvals("alice", "session.create", [approved], now=102, resource="session-B", request_digest="a" * 64).reason, "APPROVAL_REQUIRED")
            self.assertEqual(authorize_with_approvals("alice", "session.create", [approved], now=102, resource="session-A", request_digest="f" * 64).reason, "APPROVAL_REQUIRED")
            self.assertTrue(store.verify()["ok"])

    def test_request_and_decision_retries_are_idempotent(self):
        times = iter((100.0, 101.0))
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            service = ApprovalService(store, clock=lambda: next(times), principal=self.principal())
            args = dict(
                principal_id="alice", action="session.create", resource_id="session-A",
                request_digest="b" * 64, idempotency_key="request-2",
            )
            first = service.request(**args)
            second = service.request(**args)
            self.assertEqual(first, second)
            reviewer = ApprovalService(store, clock=lambda: next(times), principal=self.principal("reviewer", {"policy.approval.vote"}))
            approved = reviewer.decide(
                first["approval_id"], decision="APPROVED", approver_id="reviewer",
                expected_version=1, reason="checked", idempotency_key="approve-2",
            )
            retried = reviewer.decide(
                first["approval_id"], decision="APPROVED", approver_id="reviewer",
                expected_version=1, reason="checked", idempotency_key="approve-2",
            )
            self.assertEqual(approved, retried)
            self.assertEqual(store.audit_export()["events"], 3)
            self.assertTrue(store.verify()["ok"])

    def test_self_approval_and_stale_version_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            times = iter((100.0, 101.0, 102.0))
            service = ApprovalService(store, clock=lambda: next(times), principal=self.principal())
            request = service.request(
                principal_id="alice", action="session.create", resource_id="session-A",
                request_digest="c" * 64, idempotency_key="request-3",
            )
            with self.assertRaisesRegex(PolicyError, "SELF_APPROVAL_FORBIDDEN"):
                service.decide(request["approval_id"], decision="APPROVED", approver_id="alice", expected_version=1)
            reviewer = ApprovalService(store, clock=lambda: next(times), principal=self.principal("reviewer", {"policy.approval.vote"}))
            approved = reviewer.decide(request["approval_id"], decision="APPROVED", approver_id="reviewer", expected_version=1)
            with self.assertRaisesRegex(PolicyError, "APPROVAL_VERSION_CONFLICT"):
                reviewer.decide(request["approval_id"], decision="DENIED", approver_id="reviewer", expected_version=1)
            self.assertEqual(store.get_approval(request["approval_id"]), approved)

    def test_expired_request_is_persisted_as_expired(self):
        times = iter((100.0, 110.0))
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            service = ApprovalService(store, clock=lambda: next(times), principal=self.principal())
            request = service.request(
                principal_id="alice", action="session.create", resource_id="session-A",
                request_digest="d" * 64, idempotency_key="request-4", ttl_seconds=10,
            )
            reviewer = ApprovalService(store, clock=lambda: next(times), principal=self.principal("reviewer", {"policy.approval.vote"}))
            expired = reviewer.decide(request["approval_id"], decision="APPROVED", approver_id="reviewer", expected_version=1)
            self.assertEqual(expired["status"], "EXPIRED")
            self.assertFalse(authorize_with_approvals("alice", "session.create", [expired], now=111, resource="session-A", request_digest="d" * 64).allowed)
            self.assertTrue(store.verify()["ok"])

    def test_invalid_approval_transition_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            service = ApprovalService(store, clock=lambda: 100.0, principal=self.principal())
            request = service.request(
                principal_id="alice", action="session.create", resource_id="session-A",
                request_digest="e" * 64, idempotency_key="request-5",
            )
            before = store.audit_export()["events"]
            bad = dict(request)
            bad.update(status="APPROVED", version=99, decided_by="reviewer", decided_at=101.0, decision_reason="forged")
            payload = {
                "approval": bad,
                "transition": {"decision": "APPROVED", "approver_id": "reviewer", "reason": "forged"},
            }
            with self.assertRaises((PolicyError, SQLiteStateError)):
                store.emit(
                    "policy.approval.decided", payload, actor_id="reviewer",
                    authority_context={"principal": "reviewer", "role": "approver"},
                    idempotency_key="bad-approval",
                )
            self.assertEqual(store.audit_export()["events"], before)
            self.assertEqual(store.get_approval(request["approval_id"]), request)
            self.assertTrue(store.verify()["ok"])

    def test_approval_projection_corruption_is_detected(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            request = ApprovalService(store, clock=lambda: 100.0, principal=self.principal()).request(
                principal_id="alice", action="session.create", resource_id="session-A",
                request_digest="f" * 64, idempotency_key="request-6",
            )
            store._conn.execute(
                "UPDATE approvals SET approval_json=? WHERE approval_id=?",
                ('{"broken":true}', request["approval_id"]),
            )
            self.assertEqual(store.verify()["reason"], "approval_projection_mismatch")


if __name__ == "__main__":
    unittest.main()
