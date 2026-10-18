"""Tests for HG2's fail-closed policy and approval state machine."""
import unittest

from hg.auth import BearerAuthenticator, CONFIGURABLE_SCOPES
from hg.policy import (
    ALLOWED,
    APPROVABLE_ACTIONS,
    FORBIDDEN,
    NEEDS_AUTH,
    CapabilityGrant,
    PolicyError,
    authorize,
    authorize_principal,
    authorize_with_grants,
    create_approval_request,
    decide_approval,
    authorize_with_approvals,
)


class PolicyTests(unittest.TestCase):
    def test_compatibility_authorizer_remains_deny_by_default(self):
        self.assertFalse(authorize("session.create", authenticated=True).allowed)
        self.assertFalse(authorize("session.create").allowed)
        self.assertFalse(authorize("shell.exec", authenticated=True).allowed)
        self.assertFalse(ALLOWED & FORBIDDEN)

    def test_provider_invocation_requires_sealed_principal_not_boolean_or_approval(self):
        self.assertFalse(authorize("provider.invoke", authenticated=True).allowed)
        self.assertEqual(authorize("provider.invoke", authenticated=True).reason, "SEALED_PRINCIPAL_REQUIRED")
        self.assertNotIn("provider.invoke", APPROVABLE_ACTIONS)
        with self.assertRaisesRegex(PolicyError, "ACTION_NOT_APPROVABLE"):
            create_approval_request(
                principal_id="alice", action="provider.invoke", resource_id="provider",
                request_digest="a" * 64, now=10,
            )
        grant = CapabilityGrant("g-provider", "alice", "provider.invoke", 1)
        self.assertEqual(
            authorize_with_grants("alice", "provider.invoke", [grant], now=2).reason,
            "SEALED_PRINCIPAL_REQUIRED",
        )

    def test_service_mutations_require_the_exact_sealed_scope(self):
        from hg.policy import authorize_service_mutation
        scoped = BearerAuthenticator("task-create", {"workflow.task.create"}, principal_id="alice").authenticate("Bearer task-create")
        self.assertTrue(authorize_service_mutation("workflow.task.create", scoped).allowed)
        self.assertEqual(authorize_service_mutation("workflow.task.transition", scoped).reason, "ACTION_NOT_AUTHORIZED")
        self.assertEqual(authorize_service_mutation("workflow.task.create", True).reason, "AUTHENTICATION_REQUIRED")
        self.assertEqual(authorize_service_mutation("shell.exec", scoped).reason, "NOT_ALLOWLISTED")
        self.assertFalse(authorize("workflow.task.create", authenticated=True).allowed)

    def test_configurable_auth_scopes_are_single_sourced_through_policy(self):
        self.assertLessEqual(CONFIGURABLE_SCOPES, ALLOWED)
        self.assertLessEqual(CONFIGURABLE_SCOPES, NEEDS_AUTH)
        auth = BearerAuthenticator("policy-test-token", CONFIGURABLE_SCOPES, principal_id="policy-test")
        principal = auth.authenticate("Bearer policy-test-token")
        for action in CONFIGURABLE_SCOPES:
            self.assertTrue(authorize_principal(action, principal).allowed)
            self.assertFalse(authorize_principal(action, object()).allowed)

    def test_explicit_grant_is_required_and_scoped(self):
        grant = CapabilityGrant(
            grant_id="g1", principal_id="alice", capability="session.create",
            issued_at=10.0, expires_at=20.0, resource_scope="session-A",
        )
        self.assertTrue(authorize_with_grants("alice", "session.create", [grant], now=15, resource="session-A").allowed)
        self.assertEqual(authorize_with_grants("alice", "session.create", [grant], now=15, resource="session-B").reason, "GRANT_REQUIRED")
        self.assertEqual(authorize_with_grants("bob", "session.create", [grant], now=15, resource="session-A").reason, "GRANT_REQUIRED")

    def test_expired_future_and_revoked_grants_are_denied(self):
        expired = CapabilityGrant("g1", "alice", "session.create", 1, expires_at=5)
        future = CapabilityGrant("g2", "alice", "session.create", 30)
        revoked = CapabilityGrant("g3", "alice", "session.create", 1, revoked_at=5)
        for grant in (expired, future, revoked):
            self.assertFalse(authorize_with_grants("alice", "session.create", [grant], now=10).allowed)

    def test_self_approved_record_never_authorizes(self):
        approval = create_approval_request(
            principal_id="alice", action="session.create", resource_id="session-A",
            request_digest="9" * 64, now=100,
        )
        approval.update(status="APPROVED", version=2, decided_by="alice", decided_at=101)
        result = authorize_with_approvals(
            "alice", "session.create", [approval], now=102,
            resource="session-A", request_digest="9" * 64,
        )
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "APPROVAL_REQUIRED")

    def test_malformed_grant_and_approval_state_fail_closed(self):
        malformed = CapabilityGrant("g1", "alice", "session.create", "bad-time")
        self.assertFalse(authorize_with_grants("alice", "session.create", [malformed], now=2).allowed)
        request = create_approval_request(
            principal_id="alice", action="session.create", resource_id="session-A",
            request_digest="c" * 64, now=100,
        )
        request["status"] = ["PENDING"]
        with self.assertRaisesRegex(PolicyError, "APPROVAL_STATUS_INVALID"):
            decide_approval(request, decision="APPROVED", approver_id="reviewer", now=101)

    def test_forbidden_action_cannot_be_granted(self):
        grant = CapabilityGrant("g1", "alice", "shell.exec", 1)
        result = authorize_with_grants("alice", "shell.exec", [grant], now=2)
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "EXPLICITLY_FORBIDDEN")

    def test_approval_requires_independent_approver(self):
        request = create_approval_request(
            principal_id="alice", action="session.create", resource_id="session-A",
            request_digest="a" * 64, now=100,
        )
        with self.assertRaisesRegex(PolicyError, "SELF_APPROVAL_FORBIDDEN"):
            decide_approval(request, decision="APPROVED", approver_id="alice", now=101)
        approved = decide_approval(request, decision="APPROVED", approver_id="reviewer", now=101, reason="verified")
        self.assertEqual(approved["status"], "APPROVED")
        self.assertEqual(approved["decided_by"], "reviewer")

    def test_approval_expiry_and_conflicting_transition_fail_closed(self):
        request = create_approval_request(
            principal_id="alice", action="session.create", resource_id="session-A",
            request_digest="b" * 64, now=100, ttl_seconds=10,
        )
        expired = decide_approval(request, decision="APPROVED", approver_id="reviewer", now=110)
        self.assertEqual(expired["status"], "EXPIRED")
        approved = decide_approval(request, decision="APPROVED", approver_id="reviewer", now=101)
        self.assertEqual(decide_approval(approved, decision="APPROVED", approver_id="reviewer", now=102), approved)
        with self.assertRaisesRegex(PolicyError, "APPROVAL_ALREADY_DECIDED"):
            decide_approval(approved, decision="DENIED", approver_id="reviewer", now=102)


if __name__ == "__main__":
    unittest.main()
