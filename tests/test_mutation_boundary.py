"""Adversarial tests for state-store policy enforcement and one-shot mutation permits."""
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

from hg.auth import BearerAuthenticator
from hg.history import HistoryError, StateStore
from hg.policy import PolicyError, issue_mutation_permit, consume_mutation_permit, MUTATION_EVENT_ACTIONS
from tests._support import authorized_audit_emit
from hg.sqlite_state import SQLiteStateError, SQLiteStateStore


class MutationBoundaryTests(unittest.TestCase):
    def auth_principal(self, subject="alice", scopes=None):
        chosen = scopes or {"session.create"}
        token = "mutation-test:" + subject
        return BearerAuthenticator(token, chosen, principal_id=subject).authenticate("Bearer " + token)

    def payload(self, session_id="s-1", subject="alice"):
        return {"session_id": session_id, "product": "HG", "principal_id": subject}

    def issue(self, subject="alice", payload=None, correlation="corr-1", event_id=None,
              causation_id=None, evidence_refs=None, sync_required=False):
        chosen_payload = payload if payload is not None else self.payload(subject=subject)
        context = {"principal": subject, "scope": "session.create"}
        permit = issue_mutation_permit(
            "session.create", self.auth_principal(subject), event_type="session.created",
            actor_id=subject, payload=chosen_payload, correlation_id=correlation,
            causation_id=causation_id, event_id=event_id, authority_context=context,
            evidence_refs=evidence_refs, sync_required=sync_required,
        )
        return permit, context, chosen_payload

    def emit_with_permit(self, store, permit, context, payload, *, actor="alice", correlation="corr-1",
                         event_id=None, causation_id=None, evidence_refs=None, sync_required=False):
        kwargs = {
            "correlation_id": correlation, "event_id": event_id, "causation_id": causation_id,
            "actor_id": actor, "authority_context": context, "mutation_permit": permit,
        }
        if callable(getattr(store, "pending_outbox", None)):
            kwargs["evidence_refs"] = evidence_refs
            kwargs["sync_required"] = sync_required
        return store.emit("session.created", payload, **kwargs)

    def event_count(self, store):
        result = store.audit_export()
        return result.get("events", result.get("last_seq", 0))

    def test_raw_session_write_is_denied_by_both_backends(self):
        for store_type, error_type in ((StateStore, HistoryError), (SQLiteStateStore, SQLiteStateError)):
            with self.subTest(store=store_type.__name__), tempfile.TemporaryDirectory() as directory:
                store = store_type(directory)
                before = self.event_count(store)
                with self.assertRaisesRegex(error_type, "MUTATION_AUTHORIZATION_REQUIRED"):
                    store.emit("session.created", self.payload())
                self.assertEqual(self.event_count(store), before)
                self.assertNotIn("s-1", store.audit_export()["state"]["sessions"])
                close = getattr(store, "close", None)
                if callable(close):
                    close()

    def test_arbitrary_history_append_is_gated_and_actor_provenance_is_durable(self):
        for store_type, error_type in ((StateStore, HistoryError), (SQLiteStateStore, SQLiteStateError)):
            with self.subTest(store=store_type.__name__), tempfile.TemporaryDirectory() as directory:
                store = store_type(directory)
                before = self.event_count(store)
                with self.assertRaisesRegex(error_type, "MUTATION_AUTHORIZATION_REQUIRED"):
                    store.emit("unclassified.custom.event", {"value": "untrusted"})
                self.assertEqual(self.event_count(store), before)
                record = authorized_audit_emit(store, "audit.fixture.event", {"value": "bounded"}, subject_id="auditor")
                self.assertEqual(record["event_type"], "audit.fixture.event")
                if store_type is StateStore:
                    self.assertEqual(record["event_schema"], "HG_HISTORY_EVENT_V2")
                    self.assertEqual(record["actor_id"], "auditor")
                    self.assertEqual(record["authorization_action"], "audit.append")
                    self.assertEqual(record["authority_context"], {"principal": "auditor", "scope": "audit.append"})
                else:
                    self.assertEqual(record["actor_id"], "auditor")
                    self.assertEqual(record["authority_context"], {"principal": "auditor", "scope": "audit.append"})
                self.assertTrue(store.verify()["ok"])
                close = getattr(store, "close", None)
                if callable(close):
                    close()

    def test_sqlite_domain_projection_writes_cannot_bypass_policy(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            before = self.event_count(store)
            with self.assertRaisesRegex(SQLiteStateError, "MUTATION_AUTHORIZATION_REQUIRED"):
                store.emit("workflow.task.created", {"task_id": "forged"}, actor_id="alice")
            with self.assertRaisesRegex(SQLiteStateError, "MUTATION_AUTHORIZATION_REQUIRED"):
                store.emit("policy.approval.created", {"approval_id": "forged"}, actor_id="alice")
            self.assertEqual(self.event_count(store), before)
            state = store.audit_export()["state"]
            self.assertNotIn("forged", state["tasks"])
            self.assertNotIn("forged", state["approvals"])

    def test_permit_is_bound_to_actor_payload_and_correlation(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            payload = self.payload()
            before = self.event_count(store)
            permit, context, _ = self.issue(payload=payload)
            with self.assertRaisesRegex(SQLiteStateError, "MUTATION_AUTHORIZATION_REQUIRED"):
                self.emit_with_permit(store, permit, context, self.payload("forged"))
            permit, context, _ = self.issue(payload=payload)
            with self.assertRaisesRegex(SQLiteStateError, "MUTATION_AUTHORIZATION_REQUIRED"):
                self.emit_with_permit(store, permit, context, payload, actor="bob")
            permit, context, _ = self.issue(payload=payload)
            with self.assertRaisesRegex(SQLiteStateError, "MUTATION_AUTHORIZATION_REQUIRED"):
                self.emit_with_permit(store, permit, context, payload, correlation="corr-forged")
            self.assertEqual(self.event_count(store), before)
            permit, context, _ = self.issue(payload=payload)
            event = self.emit_with_permit(store, permit, context, payload)
            self.assertEqual(event["actor_id"], "alice")
            self.assertEqual(self.event_count(store), before + 1)

    def test_permit_binds_causation_evidence_refs_and_sync_policy(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            payload = self.payload()
            before = store.audit_export()["last_seq"]
            permit, context, _ = self.issue(payload=payload)
            with self.assertRaisesRegex(SQLiteStateError, "MUTATION_AUTHORIZATION_REQUIRED"):
                self.emit_with_permit(store, permit, context, payload, causation_id="different-parent")
            permit, context, _ = self.issue(payload=payload)
            with self.assertRaisesRegex(SQLiteStateError, "MUTATION_AUTHORIZATION_REQUIRED"):
                self.emit_with_permit(store, permit, context, payload, evidence_refs=["evidence:sha256:" + "a" * 64])
            permit, context, _ = self.issue(payload=payload)
            with self.assertRaisesRegex(SQLiteStateError, "MUTATION_AUTHORIZATION_REQUIRED"):
                self.emit_with_permit(store, permit, context, payload, sync_required=True)
            self.assertEqual(store.audit_export()["last_seq"], before)
            permit, context, _ = self.issue(payload=payload)
            event = self.emit_with_permit(store, permit, context, payload)
            self.assertEqual(event["evidence_refs"], [])
            self.assertEqual(store.audit_export()["last_seq"], before + 1)
            self.assertEqual(store.pending_outbox(), [])
            self.assertTrue(store.verify()["ok"])

    def test_permit_is_single_use_even_for_identical_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(directory)
            payload = self.payload()
            permit, context, _ = self.issue(payload=payload)
            event = self.emit_with_permit(store, permit, context, payload)
            self.assertEqual(event["event_type"], "session.created")
            before = self.event_count(store)
            with self.assertRaisesRegex(HistoryError, "MUTATION_AUTHORIZATION_REQUIRED"):
                self.emit_with_permit(store, permit, context, payload)
            self.assertEqual(self.event_count(store), before)
            self.assertTrue(store.verify()["ok"])

    def test_session_permit_rejects_payload_subject_spoofing(self):
        principal = self.auth_principal("alice")
        with self.assertRaisesRegex(PolicyError, "SESSION_PAYLOAD_PRINCIPAL_MISMATCH"):
            issue_mutation_permit(
                "session.create", principal, event_type="session.created", actor_id="alice",
                payload=self.payload(subject="bob"), correlation_id="corr-1",
                authority_context={"principal": "alice", "scope": "session.create"},
            )

    def test_permit_cannot_be_issued_for_spoofed_actor_or_wrong_event_action(self):
        principal = self.auth_principal("alice")
        with self.assertRaisesRegex(PolicyError, "MUTATION_ACTOR_PRINCIPAL_MISMATCH"):
            issue_mutation_permit(
                "session.create", principal, event_type="session.created", actor_id="bob",
                payload=self.payload(subject="alice"), correlation_id="corr-1",
                authority_context={"principal": "alice", "scope": "session.create"},
            )
        with self.assertRaisesRegex(PolicyError, "MUTATION_EVENT_ACTION_MISMATCH"):
            issue_mutation_permit(
                "session.create", principal, event_type="policy.approval.decided", actor_id="alice",
                payload=self.payload(), correlation_id="corr-1",
                authority_context={"principal": "alice", "scope": "session.create"},
            )

    def test_cloned_or_expired_permit_cannot_authorize_write(self):
        payload = self.payload()
        context = {"principal": "alice", "scope": "session.create"}
        permit, _context, _ = self.issue(payload=payload)
        clone = replace(permit)
        self.assertFalse(consume_mutation_permit(
            clone, event_type="session.created", actor_id="alice", payload=payload,
            correlation_id="corr-1", authority_context=context,
        ))

        with patch("hg.policy.time.monotonic", side_effect=(100.0, 100.0, 131.0)):
            expired, _context, _ = self.issue(payload=payload)
            self.assertFalse(consume_mutation_permit(
                expired, event_type="session.created", actor_id="alice", payload=payload,
                correlation_id="corr-1", authority_context=context,
            ))

    def test_event_action_map_is_immutable(self):
        with self.assertRaises(TypeError):
            MUTATION_EVENT_ACTIONS["session.created"] = "audit.append"

    def test_wrong_scope_and_missing_subject_cannot_issue_permit(self):
        wrong_scope = self.auth_principal("alice", {"provider.invoke"})
        no_subject = BearerAuthenticator("missing-subject", {"session.create"}).authenticate("Bearer missing-subject")
        for principal in (wrong_scope, no_subject, True, None):
            with self.subTest(principal=type(principal).__name__), self.assertRaises(PolicyError):
                issue_mutation_permit(
                    "session.create", principal, event_type="session.created", actor_id="alice",
                    payload=self.payload(), correlation_id="corr-1",
                    authority_context={"principal": "alice", "scope": "session.create"},
                )


if __name__ == "__main__":
    unittest.main()
