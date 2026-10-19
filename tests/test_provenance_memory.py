import hashlib
import os
import tempfile
import unittest

from hg.provenance_memory import (
    MemoryError,
    SQLiteProvenanceMemoryStore,
    assess_memory,
    create_memory_record,
    detect_memory_conflicts,
    memory_freshness,
)


def make_record(memory_id, statement, *, source_ref="source:contract", memory_key="project.status",
                sensitivity="INTERNAL", trust="VERIFIED", expires="2026-12-01T00:00:00+00:00",
                observed="2026-10-19T00:00:00+00:00"):
    return create_memory_record(
        memory_id=memory_id,
        statement=statement,
        source_ref=source_ref,
        source_digest=hashlib.sha256(b"synthetic source").hexdigest(),
        authority_ref="authority:test",
        observed_at=observed,
        expires_at=expires,
        memory_key=memory_key,
        sensitivity=sensitivity,
        supplied_trust_level=trust,
    )


class ProvenanceMemoryAcceptanceTests(unittest.TestCase):
    def test_caller_cannot_promote_memory_to_verified(self):
        record = make_record("trusted-claim", "synthetic claim")
        self.assertEqual(record["trust_level"], "UNVERIFIED")
        result = assess_memory(
            record,
            known_authority_refs={"authority:test"},
            provenance_verifier=lambda value: (True, "self-asserted-approval"),
        )
        self.assertFalse(result["trusted"])
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertIn("PROVENANCE_ADAPTER_NOT_BOUND_TO_TRUST_ROOT", result["reasons"])

    def test_revoked_memory_stays_revoked(self):
        from hg.provenance_memory import effective_memory_trust
        record = make_record("revoked-claim", "synthetic claim", trust="REVOKED")
        result = assess_memory(record, known_authority_refs={"authority:test"})
        self.assertFalse(result["trusted"])
        self.assertEqual(result["status"], "REVOKED")
        self.assertEqual(memory_freshness(record)["status"], "REVOKED")
        self.assertEqual(effective_memory_trust(record), "REVOKED")

    def test_caller_verified_label_stays_effectively_unverified(self):
        from hg.provenance_memory import effective_memory_trust
        record = make_record("fake-verified", "synthetic claim", trust="UNVERIFIED")
        record["trust_level"] = "VERIFIED"
        unsigned = dict(record)
        unsigned.pop("record_digest", None)
        from hg.task_contract import canonical_json
        record["record_digest"] = hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()
        self.assertEqual(record["trust_level"], "VERIFIED")
        self.assertEqual(effective_memory_trust(record), "UNVERIFIED")
        assessed = assess_memory(
            record,
            known_authority_refs={"authority:test"},
            provenance_verifier=lambda value: (True, "untrusted-approval"),
        )
        self.assertFalse(assessed["trusted"])
        self.assertEqual(assessed["status"], "UNVERIFIED")

    def test_modified_record_digest_fails_closed(self):
        record = make_record("tampered-claim", "original claim")
        record["statement"] = "tampered claim"
        result = assess_memory(
            record,
            known_authority_refs={"authority:test"},
            provenance_verifier=lambda value: (True, "untrusted-ref"),
        )
        self.assertFalse(result["trusted"])
        self.assertIn("MEMORY_RECORD_DIGEST_MISMATCH", result["reasons"])

    def test_expiry_is_explicit_and_never_promoted(self):
        from datetime import datetime, timezone
        fresh = make_record("fresh-claim", "current status", expires="2026-12-01T00:00:00+00:00")
        expired = make_record("expired-claim", "old status", expires="2026-06-01T00:00:00+00:00", observed="2026-01-01T00:00:00+00:00")
        missing = make_record("missing-expiry", "unknown status", expires=None)
        now = datetime(2026, 10, 19, tzinfo=timezone.utc)
        self.assertEqual(memory_freshness(fresh, now=now)["status"], "WITHIN_EXPIRY")
        self.assertTrue(memory_freshness(fresh, now=now)["usable"])
        old_status = memory_freshness(expired, now=now)
        self.assertEqual(old_status["status"], "EXPIRED")
        self.assertFalse(old_status["usable"])
        self.assertIn("MEMORY_EXPIRED", old_status["reasons"])
        unknown = memory_freshness(missing, now=now)
        self.assertEqual(unknown["status"], "FRESHNESS_UNKNOWN")
        self.assertFalse(unknown["usable"])

    def test_conflicts_are_unresolved_not_silently_selected(self):
        one = make_record("claim-one", "status is ready")
        two = make_record("claim-two", "status is blocked")
        conflicts = detect_memory_conflicts([one, two])
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["status"], "CONFLICT_UNRESOLVED")
        self.assertEqual(conflicts[0]["memory_key"], "project.status")
        self.assertEqual(len(conflicts[0]["value_digests"]), 2)

    def test_store_restart_integrity_and_conflict_are_durable(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "provenance-memory.sqlite3")
            first = SQLiteProvenanceMemoryStore(path)
            one = make_record("persist-one", "status is ready")
            two = make_record("persist-two", "status is blocked")
            put_one = first.put(one)
            put_again = first.put(one)
            put_two = first.put(two)
            self.assertTrue(put_one["stored"])
            self.assertTrue(put_again["idempotent"])
            self.assertTrue(put_two["conflict"])
            self.assertEqual(first.verify_store_integrity()["ok"], True)
            self.assertEqual(len(first.list_conflicts()), 1)
            del first

            reopened = SQLiteProvenanceMemoryStore(path)
            self.assertEqual(reopened.get("persist-one"), one)
            self.assertEqual(reopened.verify_store_integrity()["ok"], True)
            self.assertEqual(reopened.verify_event_chain()["verified_events"], 2)
            db_stat = os.stat(path)
            self.assertEqual(db_stat.st_mode & 0o777, 0o600)

    def test_sensitive_memories_are_not_written_without_encryption_adapter(self):
        with tempfile.TemporaryDirectory() as td:
            store = SQLiteProvenanceMemoryStore(os.path.join(td, "memory.sqlite3"))
            record = make_record("sensitive-blocked", "synthetic sensitive", sensitivity="SECRET")
            with self.assertRaisesRegex(MemoryError, "MEMORY_SENSITIVITY_BLOCKED"):
                store.put(record)
            self.assertEqual(store.events(), [])
            self.assertTrue(store.verify_store_integrity()["ok"])

    def test_database_refuses_symlink_path(self):
        with tempfile.TemporaryDirectory() as td:
            actual = os.path.join(td, "actual.sqlite3")
            link = os.path.join(td, "linked.sqlite3")
            store = SQLiteProvenanceMemoryStore(actual)
            self.assertEqual(os.stat(actual).st_mode & 0o777, 0o600)
            os.symlink(actual, link)
            with self.assertRaisesRegex(MemoryError, "MEMORY_STORAGE_INVALID"):
                SQLiteProvenanceMemoryStore(link)
            self.assertTrue(store.verify_store_integrity()["ok"])


if __name__ == "__main__":
    unittest.main()
