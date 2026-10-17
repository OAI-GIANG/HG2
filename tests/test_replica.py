import hashlib
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from hg.history import StateStore, canonical, digest
from hg.memory import MemoryStore
from hg.durable import DurableOutbox
from hg.replica import CONTRACT, ReplicaError, ReplicaHTTPServer, ReplicaStore


class ReplicaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "replica.db")
        self.replica = ReplicaStore(self.db, ["private", "shared"])
        self.addCleanup(self.replica.close)
        self.source = StateStore(os.path.join(self.tmp.name, "source"))
        self.mem = MemoryStore(self.source)
        self.mem.remember({"id": "m1", "type": "fact", "title": "T", "content": "C",
                           "scope_id": "private"}, principal_id="owner", grants={"private"},
                          idempotency_key="remember-m1")
        event = next(e for e in self.source.replay() if e["event_type"] == "memory.mutated")
        entry_id = hashlib.sha256(canonical({
            "event_id": event["event_id"], "record_hash": event["record_hash"]
        }).encode()).hexdigest()
        self.entry = {"batch_id": entry_id, "event": event}
        self.body = {"contract": CONTRACT, "batch_id": "", "events": [self.entry]}
        self.body["batch_id"] = hashlib.sha256(canonical([entry_id]).encode()).hexdigest()

    def test_happy_path_atomic_receipt_and_restart_persistence(self):
        receipt = self.replica.ingest(self.body, self.body["batch_id"])
        self.assertEqual(receipt["accepted_count"], 1)
        self.assertTrue(receipt["replica_only"])
        self.assertEqual(self.replica.status()["event_count"], 1)
        self.assertEqual(self.replica.ingest(self.body, self.body["batch_id"]), receipt)
        reopened = ReplicaStore(self.db, ["private", "shared"])
        try:
            self.assertEqual(reopened.status()["event_count"], 1)
            self.assertEqual(reopened.status()["batch_count"], 1)
        finally:
            reopened.close()

    def test_wrong_scope_rejected_without_writing(self):
        replica = ReplicaStore(os.path.join(self.tmp.name, "denied.db"), ["shared"])
        try:
            with self.assertRaises(ReplicaError) as ctx:
                replica.ingest(self.body, self.body["batch_id"])
            self.assertEqual(ctx.exception.code, "MEMORY_SCOPE_DENIED")
            self.assertEqual(replica.status()["event_count"], 0)
        finally:
            replica.close()

    def test_tampered_event_hash_rejected(self):
        altered = json.loads(json.dumps(self.body))
        altered["events"][0]["event"]["payload"]["record"]["content"] = "tampered"
        with self.assertRaises(ReplicaError) as ctx:
            self.replica.ingest(altered, self.body["batch_id"])
        self.assertIn(ctx.exception.code, {"EVENT_HASH_MISMATCH", "MEMORY_CHECKSUM_MISMATCH"})
        self.assertEqual(self.replica.status()["event_count"], 0)

    def test_record_checksum_is_mandatory(self):
        altered = json.loads(json.dumps(self.body))
        altered_event = altered["events"][0]["event"]
        altered_event["payload"]["record"]["checksum"] = "0" * 64
        altered_event["record_hash"] = digest({k: v for k, v in altered_event.items() if k != "record_hash"})
        altered["events"][0]["batch_id"] = hashlib.sha256(canonical({
            "event_id": altered_event["event_id"], "record_hash": altered_event["record_hash"]
        }).encode()).hexdigest()
        altered["batch_id"] = hashlib.sha256(canonical([altered["events"][0]["batch_id"]]).encode()).hexdigest()
        with self.assertRaises(ReplicaError) as ctx:
            self.replica.ingest(altered, altered["batch_id"])
        self.assertEqual(ctx.exception.code, "MEMORY_CHECKSUM_MISMATCH")
        self.assertEqual(self.replica.status()["event_count"], 0)

    def test_conflicting_batch_id_fails_closed(self):
        self.replica.ingest(self.body, self.body["batch_id"])
        altered = json.loads(json.dumps(self.body))
        altered["events"][0]["event"]["payload"]["record"]["content"] = "changed"
        changed_event = altered["events"][0]["event"]
        changed_event["record_hash"] = digest({k: v for k, v in changed_event.items() if k != "record_hash"})
        altered["events"][0]["batch_id"] = hashlib.sha256(canonical({
            "event_id": changed_event["event_id"], "record_hash": changed_event["record_hash"]
        }).encode()).hexdigest()
        altered["batch_id"] = hashlib.sha256(canonical([altered["events"][0]["batch_id"]]).encode()).hexdigest()
        with self.assertRaises(ReplicaError):
            self.replica.ingest(altered, altered["batch_id"])

    def test_tombstone_is_replicated_as_append_only_event(self):
        self.mem.delete("m1", principal_id="owner", grants={"private"}, expected_version=1,
                        idempotency_key="delete-m1")
        event = next(e for e in reversed(self.source.replay()) if e["event_type"] == "memory.tombstoned")
        entry_id = hashlib.sha256(canonical({
            "event_id": event["event_id"], "record_hash": event["record_hash"]
        }).encode()).hexdigest()
        entry = {"batch_id": entry_id, "event": event}
        body = {"contract": CONTRACT, "batch_id": hashlib.sha256(canonical([entry_id]).encode()).hexdigest(),
                "events": [entry]}
        receipt = self.replica.ingest(body, body["batch_id"])
        self.assertEqual(receipt["accepted_count"], 1)
        row = self.replica._db.execute("SELECT event_json FROM replica_events WHERE source_event_id=?",
                                       (event["event_id"],)).fetchone()
        saved = json.loads(row[0])
        self.assertEqual(saved["event_type"], "memory.tombstoned")
        self.assertEqual(saved["payload"]["record"]["status"], "tombstoned")
        self.assertEqual(saved["payload"]["record"]["content"], "")

    def test_sqlite_backup_restore_preserves_replica_evidence(self):
        self.replica.ingest(self.body, self.body["batch_id"])
        backup = os.path.join(self.tmp.name, "restored.sqlite3")
        source_db = sqlite3.connect(self.db)
        target_db = sqlite3.connect(backup)
        try:
            source_db.backup(target_db)
        finally:
            target_db.close()
            source_db.close()
        restored = ReplicaStore(backup, ["private", "shared"])
        try:
            self.assertEqual(restored.status()["event_count"], 1)
            self.assertEqual(restored.status()["batch_count"], 1)
        finally:
            restored.close()

    def test_real_http_outbox_to_replica_round_trip(self):
        token = "T" * 48
        server = ReplicaHTTPServer(("127.0.0.1", 0), self.replica, token)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = "http://127.0.0.1:%d" % server.server_address[1]
        outbox = DurableOutbox(self.source, base_url=base, token=token, allowed_scopes={"private"}, timeout=2)
        result = outbox.deliver_once()
        self.assertEqual(result["status"], "ACKNOWLEDGED")
        self.assertEqual(outbox.status()["pending_count"], 0)
        self.assertEqual(self.replica.status()["event_count"], 1)
        self.assertEqual(self.replica.status()["batch_count"], 1)
        self.assertEqual(outbox.deliver_once()["status"], "EMPTY")

    def test_http_authentication_and_capability_endpoint(self):
        token = "T" * 48
        server = ReplicaHTTPServer(("127.0.0.1", 0), self.replica, token)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = "http://127.0.0.1:%d/backend/hg2/capabilities" % server.server_address[1]
        with self.assertRaises(HTTPError) as ctx:
            urlopen(url, timeout=2)
        with ctx.exception:
            self.assertEqual(ctx.exception.code, 401)
        request = Request(url, headers={"Authorization": "Bearer " + token})
        with urlopen(request, timeout=2) as response:
            caps = json.loads(response.read().decode())
        self.assertEqual(caps["contract"], CONTRACT)
        self.assertTrue(caps["supports_scopes"])
        self.assertTrue(caps["supports_tombstones"])


if __name__ == "__main__":
    unittest.main()
