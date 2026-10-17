"""Tests for non-destructive, hash-verified SQLite backup and restore."""
import os
import tempfile
import unittest

from hg.recovery import RecoveryError, backup_state, restore_state


def file_sha256(path):
    import hashlib
    with open(path, "rb") as stream:
        return hashlib.sha256(stream.read()).hexdigest()
from hg.sqlite_state import SQLiteStateStore


class RecoveryTests(unittest.TestCase):
    def make_state(self, directory):
        with SQLiteStateStore(directory, clock=lambda: 100.0) as store:
            store.emit("session.created", {"session_id": "s-1", "product": "HG"})
            store.emit("task.note", {"note": "recovery fixture"}, sync_required=True)
            return store.audit_export()

    def test_backup_restore_round_trip_preserves_chain_and_projections(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as backup, tempfile.TemporaryDirectory() as restored:
            source_audit = self.make_state(source)
            source_db = os.path.join(source, "hg2-state.sqlite3")
            before_hash = file_sha256(source_db)
            backup_report = backup_state(source, backup, clock=lambda: 200.0)
            self.assertEqual(backup_report["status"], "BACKUP_VERIFIED")
            self.assertEqual(backup_report["head_digest"], source_audit["head_digest"])
            self.assertEqual(file_sha256(source_db), before_hash)
            restore_report = restore_state(backup, restored)
            self.assertEqual(restore_report["status"], "RESTORE_VERIFIED")
            self.assertEqual(restore_report["head_digest"], source_audit["head_digest"])
            self.assertEqual(restore_report["events"], source_audit["events"])
            with SQLiteStateStore(restored) as store:
                self.assertTrue(store.verify()["ok"])
                self.assertEqual(store.audit_export()["state"]["sessions"]["s-1"]["session_id"], "s-1")
                self.assertEqual(store.pending_outbox()[0]["event_id"], store.replay()[-1]["event_id"])

    def test_backup_refuses_missing_source_without_creating_it(self):
        with tempfile.TemporaryDirectory() as source_parent, tempfile.TemporaryDirectory() as target:
            source = os.path.join(source_parent, "missing")
            with self.assertRaisesRegex(RecoveryError, "SOURCE_DIRECTORY_INVALID"):
                backup_state(source, target)
            self.assertEqual(os.listdir(target), [])

    def test_nonempty_backup_or_restore_target_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as backup, tempfile.TemporaryDirectory() as target, tempfile.TemporaryDirectory() as restore_target:
            self.make_state(source)
            marker = os.path.join(backup, "keep.txt")
            with open(marker, "w", encoding="utf-8") as stream:
                stream.write("preserve")
            with self.assertRaisesRegex(RecoveryError, "TARGET_MUST_BE_EMPTY_DIRECTORY"):
                backup_state(source, backup)
            with open(marker, encoding="utf-8") as stream:
                self.assertEqual(stream.read(), "preserve")
            backup_state(source, target)
            with open(os.path.join(restore_target, "keep.txt"), "w", encoding="utf-8") as stream:
                stream.write("preserve")
            with self.assertRaisesRegex(RecoveryError, "TARGET_MUST_BE_EMPTY_DIRECTORY"):
                restore_state(target, restore_target)

    def test_backup_database_tampering_is_detected_before_restore(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as backup, tempfile.TemporaryDirectory() as target:
            self.make_state(source)
            backup_state(source, backup)
            db = os.path.join(backup, "hg2-state.sqlite3")
            with open(db, "ab") as stream:
                stream.write(b"tamper")
            with self.assertRaisesRegex(RecoveryError, "BACKUP_DATABASE_HASH_MISMATCH"):
                restore_state(backup, target)
            self.assertEqual(os.listdir(target), [])

    def test_source_and_target_must_be_separate(self):
        with tempfile.TemporaryDirectory() as source:
            self.make_state(source)
            with self.assertRaisesRegex(RecoveryError, "SOURCE_AND_TARGET_MUST_BE_SEPARATE"):
                backup_state(source, source)


if __name__ == "__main__":
    unittest.main()
