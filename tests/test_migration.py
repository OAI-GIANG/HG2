"""Tests for read-only legacy verification and atomic SQLite migration."""
import hashlib
import json
import os
import tempfile
import unittest

from hg.contracts import canonical_json
from hg.history import StateStore
from hg.migration import MigrationError, inspect_legacy_state, migrate_legacy_state, _prepare_import_events
from hg.sqlite_state import SQLiteStateStore, SQLiteStateError
from hg.auth import BearerAuthenticator
from tests._support import authorized_domain_emit, authorized_audit_emit


def source_hashes(directory):
    result = {}
    for name in ("history.jsonl", "head.json", "state.json", "runtime_id"):
        with open(os.path.join(directory, name), "rb") as stream:
            result[name] = hashlib.sha256(stream.read()).hexdigest()
    return result


def make_legacy(directory):
    store = StateStore(directory, clock=lambda: 100.0)
    authorized_domain_emit(store, "session.created", {"session_id": "s-1", "product": "HG"}, subject_id="fixture", action="session.create", correlation_id="session-corr")
    authorized_audit_emit(store, "note.recorded", {"note": "migration fixture"}, correlation_id="note-corr")
    return store


class LegacyMigrationTests(unittest.TestCase):
    def principal(self):
        token = "migration-fixture-token"
        return BearerAuthenticator(token, {"state.migration.import"}, principal_id="migration-fixture").authenticate("Bearer " + token)

    def test_verified_migration_preserves_source_and_projects_state(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as target:
            make_legacy(source)
            before = source_hashes(source)
            inspected = inspect_legacy_state(source)
            self.assertEqual(inspected["source_event_count"], 3)
            report = migrate_legacy_state(source, target, principal=self.principal(), clock=lambda: 200.0)
            self.assertEqual(report["status"], "MIGRATED_VERIFIED")
            self.assertEqual(report["source_event_count"], 3)
            self.assertEqual(report["target_event_count"], 3)
            self.assertTrue(report["verification"]["ok"])
            self.assertEqual(source_hashes(source), before)

            with SQLiteStateStore(target) as store:
                self.assertTrue(store.verify()["ok"])
                exported = store.audit_export()
                self.assertEqual(exported["migration"]["migration_status"], "VERIFIED_IMPORT")
                self.assertEqual(exported["state"]["sessions"]["s-1"]["session_id"], "s-1")
                events = store.replay()
                self.assertEqual(events[1]["authority_context"]["migration"], "HG_STATE_V1")
                self.assertEqual(events[1]["authority_context"]["source_event_schema"], "HG_HISTORY_EVENT_V2")
                self.assertEqual(events[1]["authority_context"]["source_actor_id"], "fixture")
                self.assertEqual(events[1]["authority_context"]["source_authorization_action"], "session.create")
                self.assertEqual(events[1]["evidence_refs"], [inspected["events"][1]["record_hash"]])
                authorized_audit_emit(store, "post.migration", {"note": "new event"})
                self.assertTrue(store.verify()["ok"])
                self.assertEqual(store.verify()["events"], 4)
            self.assertEqual(source_hashes(source), before)

    def test_migration_requires_explicit_policy_principal_before_target_creation(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as target:
            make_legacy(source)
            with self.assertRaisesRegex(MigrationError, "MIGRATION_AUTHORIZATION"):
                migrate_legacy_state(source, target)
            self.assertEqual(os.listdir(target), [])

    def test_store_import_api_cannot_bypass_policy_even_with_prevalidated_events(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as target:
            make_legacy(source)
            report = inspect_legacy_state(source)
            with SQLiteStateStore(target) as store:
                imported = _prepare_import_events(report["events"], store.runtime_id)
                metadata = {
                    "source_runtime_id": report["source_runtime_id"],
                    "source_head_hash": report["source_head_hash"],
                    "source_event_count": report["source_event_count"],
                    "source_log_sha256": report["source_log_sha256"],
                    "source_head_sha256": report["source_head_sha256"],
                    "source_state_sha256": report["source_state_sha256"],
                    "source_runtime_id_sha256": report["source_runtime_id_sha256"],
                }
                before = store.audit_export()
                with self.assertRaisesRegex(SQLiteStateError, "MUTATION_AUTHORIZATION_REQUIRED"):
                    store.import_verified_events(imported, metadata)
                after = store.audit_export()
                self.assertEqual(after["events"], before["events"])
                self.assertEqual(after["head_digest"], before["head_digest"])
                self.assertTrue(after["verify"]["ok"])

    def test_corrupt_source_log_is_rejected_without_creating_target(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as target:
            make_legacy(source)
            log = os.path.join(source, "history.jsonl")
            with open(log, encoding="utf-8") as stream:
                lines = stream.readlines()
            lines[-1] = lines[-1].replace('"note":', '"note_corrupt":', 1)
            with open(log, "w", encoding="utf-8") as stream:
                stream.writelines(lines)
            with self.assertRaises(MigrationError):
                migrate_legacy_state(source, target, principal=self.principal())
            self.assertEqual(os.listdir(target), [])

    def test_sensitive_legacy_payload_is_rejected_before_target_creation(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as target:
            store = StateStore(source, clock=lambda: 100.0)
            authorized_audit_emit(store, "config.imported", {"api_key": "redacted-test-value"})
            with self.assertRaisesRegex(MigrationError, "LEGACY_EVENT_NOT_COMPATIBLE"):
                migrate_legacy_state(source, target, principal=self.principal())
            self.assertEqual(os.listdir(target), [])

    def test_state_projection_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as target:
            make_legacy(source)
            path = os.path.join(source, "state.json")
            with open(path, encoding="utf-8") as stream:
                state = json.load(stream)
            state["counters"]["session.created"] = 999
            with open(path, "w", encoding="utf-8") as stream:
                stream.write(canonical_json(state))
            with self.assertRaisesRegex(MigrationError, "SOURCE_STATE_PROJECTION_MISMATCH"):
                migrate_legacy_state(source, target, principal=self.principal())
            self.assertEqual(os.listdir(target), [])

    def test_nonempty_target_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as target:
            make_legacy(source)
            marker = os.path.join(target, "keep.txt")
            with open(marker, "w", encoding="utf-8") as stream:
                stream.write("preserve")
            with self.assertRaisesRegex(MigrationError, "TARGET_MUST_BE_EMPTY_DIRECTORY"):
                migrate_legacy_state(source, target, principal=self.principal())
            with open(marker, encoding="utf-8") as stream:
                self.assertEqual(stream.read(), "preserve")

    def test_source_and_target_must_be_separate(self):
        with tempfile.TemporaryDirectory() as source:
            make_legacy(source)
            with self.assertRaisesRegex(MigrationError, "SOURCE_AND_TARGET_MUST_BE_SEPARATE"):
                migrate_legacy_state(source, source, principal=self.principal())


if __name__ == "__main__":
    unittest.main()
