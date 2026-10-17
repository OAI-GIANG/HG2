"""Tests for transport-agnostic outbox dispatch."""
import tempfile
import unittest

from hg.sqlite_state import SQLiteStateStore
from hg.sync import SyncDispatcher


class FakeTransport:
    def __init__(self, *, start_cursor=1, failure=None, mutate_ack=None):
        self.cursor = start_cursor
        self.failure = failure
        self.mutate_ack = mutate_ack
        self.sent = []

    def send_event(self, event):
        self.sent.append(event["event_id"])
        if self.failure:
            raise self.failure
        ack = {
            "status": "ACK",
            "event_id": event["event_id"],
            "event_digest": event["record_digest"],
            "remote_cursor": self.cursor,
        }
        self.cursor += 1
        return self.mutate_ack(ack) if self.mutate_ack else ack


class SyncDispatcherTests(unittest.TestCase):
    def test_dispatch_delivers_and_acknowledges_in_order(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            first = store.emit("task.created", {"task_id": "t1"}, sync_required=True)
            second = store.emit("task.created", {"task_id": "t2"}, sync_required=True)
            transport = FakeTransport(start_cursor=10)
            report = SyncDispatcher(store, transport).dispatch_once()
            self.assertEqual(report["status"], "SYNCED")
            self.assertEqual(report["sent"], 2)
            self.assertEqual(transport.sent, [first["event_id"], second["event_id"]])
            self.assertEqual(store.verify()["last_ack_cursor"], 11)

    def test_transport_failure_leaves_event_pending_and_records_attempt(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            event = store.emit("task.created", {"task_id": "t1"}, sync_required=True)
            report = SyncDispatcher(store, FakeTransport(failure=TimeoutError())).dispatch_once()
            self.assertEqual(report["status"], "RETRY_PENDING")
            self.assertEqual(report["pending"], 1)
            self.assertEqual(store.pending_outbox()[0]["attempts"], 1)
            self.assertEqual(store.pending_outbox()[0]["event_id"], event["event_id"])

    def test_invalid_acknowledgement_does_not_advance_cursor(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            store.emit("task.created", {"task_id": "t1"}, sync_required=True)
            def wrong_event(ack):
                ack["event_id"] = "not-the-sent-event"
                return ack
            report = SyncDispatcher(store, FakeTransport(mutate_ack=wrong_event)).dispatch_once()
            self.assertEqual(report["status"], "BLOCKED_ACK_INVALID")
            self.assertEqual(store.verify()["last_ack_cursor"], 0)
            self.assertEqual(len(store.pending_outbox()), 1)

    def test_invalid_cursor_ack_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            store.emit("task.created", {"task_id": "t1"}, sync_required=True)
            def bool_cursor(ack):
                ack["remote_cursor"] = True
                return ack
            report = SyncDispatcher(store, FakeTransport(mutate_ack=bool_cursor)).dispatch_once()
            self.assertEqual(report["status"], "BLOCKED_ACK_INVALID")
            self.assertEqual(store.verify()["last_ack_cursor"], 0)

    def test_batch_limit_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteStateStore(directory) as store:
            store.emit("task.created", {"task_id": "t1"}, sync_required=True)
            report = SyncDispatcher(store, FakeTransport()).dispatch_once(limit=0)
            self.assertEqual(report["status"], "BLOCKED_INVALID_BATCH")
            self.assertEqual(len(store.pending_outbox()), 1)


if __name__ == "__main__":
    unittest.main()
