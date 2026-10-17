"""Transactional SQLite state backend tests."""
import sqlite3
import tempfile
import unittest

from hg.sqlite_state import IdempotencyConflict, SQLiteStateError, SQLiteStateStore


class SQLiteStateStoreTests(unittest.TestCase):
    def test_genesis_append_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStateStore(directory, clock=lambda: 100.0)
            self.assertEqual(store.verify()["events"], 1)
            event = store.emit("session.created", {"session_id": "s-1"}, idempotency_key="idem-1")
            self.assertEqual(event["sequence"], 2)
            self.assertTrue(store.verify()["ok"])
            store.close()

            with SQLiteStateStore(directory, clock=lambda: 101.0) as reopened:
                self.assertTrue(reopened.verify()["ok"])
                self.assertEqual(reopened.audit_export()["state"]["sessions"]["s-1"]["session_id"], "s-1")
                self.assertEqual(reopened.audit_export()["events"], 2)

    def test_idempotency_key_returns_same_event_for_same_operation(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            first = store.emit("task.created", {"task_id": "t1"}, idempotency_key="same")
            second = store.emit("task.created", {"task_id": "t1"}, idempotency_key="same")
            self.assertEqual(first["event_id"], second["event_id"])
            self.assertEqual(store.verify()["events"], 2)

    def test_idempotency_key_conflict_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            store.emit("task.created", {"task_id": "t1"}, idempotency_key="same")
            with self.assertRaises(IdempotencyConflict):
                store.emit("task.created", {"task_id": "t2"}, idempotency_key="same")
            self.assertEqual(store.verify()["events"], 2)

    def test_event_id_retry_is_idempotent_for_same_operation(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            first = store.emit("task.created", {"task_id": "t1"}, event_id="fixed-id")
            second = store.emit("task.created", {"task_id": "t1"}, event_id="fixed-id")
            self.assertEqual(first["record_digest"], second["record_digest"])
            self.assertEqual(store.verify()["events"], 2)

    def test_event_id_reuse_for_different_operation_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            store.emit("task.created", {"task_id": "t1"}, event_id="fixed-id")
            with self.assertRaises(IdempotencyConflict):
                store.emit("task.created", {"task_id": "t2"}, event_id="fixed-id")
            self.assertEqual(store.verify()["events"], 2)

    def test_idempotency_cannot_cross_actor_boundary(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            store.emit("task.created", {"task_id": "t1"}, idempotency_key="same", actor_id="alice")
            with self.assertRaises(IdempotencyConflict):
                store.emit("task.created", {"task_id": "t1"}, idempotency_key="same", actor_id="bob")
            self.assertEqual(store.verify()["events"], 2)

    def test_failed_projection_rolls_back_event_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            before = store.audit_export()
            original = store._apply_projection
            def fail(_event):
                raise RuntimeError("simulated projection failure")
            store._apply_projection = fail
            with self.assertRaisesRegex(RuntimeError, "simulated projection failure"):
                store.emit("task.created", {"task_id": "t1"}, sync_required=True)
            store._apply_projection = original
            after = store.audit_export()
            self.assertEqual(after["events"], before["events"])
            self.assertEqual(after["head_digest"], before["head_digest"])
            self.assertEqual(after["pending_outbox"], 0)
            self.assertTrue(after["verify"]["ok"])

    def test_corrupt_event_fails_closed_on_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStateStore(directory)
            store.emit("task.created", {"task_id": "t1"})
            store.close()
            db = sqlite3.connect(directory + "/hg2-state.sqlite3")
            db.execute("UPDATE events SET event_json=? WHERE sequence=2", ('{"broken":true}',))
            db.commit()
            db.close()
            with self.assertRaisesRegex(SQLiteStateError, "state integrity failed"):
                SQLiteStateStore(directory)

    def test_checkpoint_mismatch_fails_closed_on_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStateStore(directory)
            store.close()
            db = sqlite3.connect(directory + "/hg2-state.sqlite3")
            db.execute("UPDATE metadata SET value=? WHERE key='head_digest'", ("f" * 64,))
            db.commit()
            db.close()
            with self.assertRaisesRegex(SQLiteStateError, "state integrity failed"):
                SQLiteStateStore(directory)

    def test_outbox_event_and_acknowledgement(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory, clock=lambda: 200.0) as store:
            event = store.emit("task.created", {"task_id": "t1"}, sync_required=True)
            pending = store.pending_outbox()
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["event_id"], event["event_id"])
            self.assertEqual(store.record_outbox_attempt(event["event_id"]), 1)
            self.assertEqual(store.pending_outbox()[0]["attempts"], 1)
            self.assertTrue(store.acknowledge_outbox(event["event_id"], 1))
            self.assertEqual(store.pending_outbox(), [])
            self.assertTrue(store.acknowledge_outbox(event["event_id"], 1))
            self.assertEqual(store.verify()["last_ack_cursor"], 1)
            self.assertTrue(store.verify()["ok"])

    def test_outbox_acknowledgements_are_ordered_and_monotonic(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            first = store.emit("task.created", {"task_id": "t1"}, sync_required=True)
            second = store.emit("task.created", {"task_id": "t2"}, sync_required=True)
            with self.assertRaisesRegex(SQLiteStateError, "OUTBOX_ACK_OUT_OF_ORDER"):
                store.acknowledge_outbox(second["event_id"], 2)
            self.assertTrue(store.acknowledge_outbox(first["event_id"], 2))
            with self.assertRaisesRegex(SQLiteStateError, "REMOTE_CURSOR_NOT_MONOTONIC"):
                store.acknowledge_outbox(second["event_id"], 1)
            self.assertTrue(store.acknowledge_outbox(second["event_id"], 3))
            self.assertTrue(store.verify()["ok"])

    def test_outbox_retry_cannot_change_delivery_policy(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            store.emit("task.created", {"task_id": "t1"}, event_id="fixed-id")
            with self.assertRaisesRegex(IdempotencyConflict, "EVENT_DELIVERY_POLICY_CONFLICT"):
                store.emit("task.created", {"task_id": "t1"}, event_id="fixed-id", sync_required=True)
            self.assertEqual(store.pending_outbox(), [])

    def test_outbox_invalid_cursor_and_missing_event_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            event = store.emit("task.created", {"task_id": "t1"}, sync_required=True)
            with self.assertRaisesRegex(SQLiteStateError, "INVALID_REMOTE_CURSOR"):
                store.acknowledge_outbox(event["event_id"], True)
            with self.assertRaisesRegex(SQLiteStateError, "OUTBOX_EVENT_NOT_FOUND"):
                store.acknowledge_outbox("unknown-event", 1)

    def test_outbox_digest_corruption_is_detected(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            event = store.emit("task.created", {"task_id": "t1"}, sync_required=True)
            store._conn.execute("UPDATE outbox SET event_digest=? WHERE event_id=?", ("f" * 64, event["event_id"]))
            self.assertEqual(store.verify()["reason"], "outbox_event_mismatch")

    def test_backend_schema_upgrade_requires_explicit_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStateStore(directory)
            store.close()
            db = sqlite3.connect(directory + "/hg2-state.sqlite3")
            db.execute("UPDATE metadata SET value='2' WHERE key='backend_schema'")
            db.commit()
            db.close()
            with self.assertRaisesRegex(SQLiteStateError, "state integrity failed"):
                SQLiteStateStore(directory)

    def test_projection_corruption_is_detected(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            store.emit("session.created", {"session_id": "s-1"})
            store._conn.execute("UPDATE counters SET count=99 WHERE event_type='session.created'")
            self.assertEqual(store.verify()["reason"], "counter_projection_mismatch")


if __name__ == "__main__":
    unittest.main()
