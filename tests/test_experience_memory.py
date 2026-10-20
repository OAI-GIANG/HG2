import hashlib
import tempfile
import unittest
from pathlib import Path

from hg.experience_memory import (
    ExperienceMemoryError, ExperienceMemoryStore, create_experience,
)
from hg.provenance_memory import SQLiteProvenanceMemoryStore


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_experience(memory_id, statement, **overrides):
    value = {
        "memory_id": memory_id,
        "statement": statement,
        "source_ref": "evidence:source.json",
        "source_digest": sha("source-bytes"),
        "authority_ref": "authority:repo",
        "observed_at": "2026-10-20T01:00:00+00:00",
        "expires_at": "2026-12-20T01:00:00+00:00",
        "memory_key": "workflow.crash-recovery",
        "experience_type": "LESSON",
        "scope": "hg2/workflow",
        "task_id": "task-p1",
        "parent_memory_ids": [],
        "sensitivity": "INTERNAL",
    }
    value.update(overrides)
    return create_experience(**value)


class ExperienceMemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "experience.sqlite3")
        self.backing = SQLiteProvenanceMemoryStore(self.db_path)
        self.store = ExperienceMemoryStore(self.backing)

    def tearDown(self):
        self.tmp.cleanup()

    def test_store_and_restart_preserves_scope_lineage_and_unverified_status(self):
        record = make_experience("lesson-1", "A complete event frame cannot be discarded.")
        result = self.store.put(record)
        self.assertTrue(result["stored"])
        self.assertEqual(result["trust_level"], "UNVERIFIED")
        self.assertEqual(self.store.get("lesson-1"), record)
        self.assertTrue(self.backing.verify_store_integrity()["ok"])
        reopened_backing = SQLiteProvenanceMemoryStore(self.db_path)
        reopened = ExperienceMemoryStore(reopened_backing)
        self.assertEqual(reopened.get("lesson-1"), record)
        self.assertTrue(reopened_backing.verify_store_integrity()["ok"])

    def test_caller_cannot_self_promote_experience(self):
        record = make_experience("lesson-2", "caller should not promote memory")
        record["trust_level"] = "VERIFIED"
        record.pop("record_digest")
        record["record_digest"] = hashlib.sha256(
            __import__("hg.task_contract", fromlist=["canonical_json"]).canonical_json(record).encode()
        ).hexdigest()
        with self.assertRaisesRegex(ExperienceMemoryError, "EXPERIENCE_CANNOT_SELF_PROMOTE_TRUST"):
            self.store.put(record)

    def test_scope_and_time_bound_retrieval(self):
        current = make_experience("active-lesson", "Current bounded lesson")
        other_scope = make_experience("other-scope", "Other scope", scope="hg2/voice")
        expired = make_experience(
            "expired-lesson", "Expired lesson",
            expires_at="2026-10-20T01:30:00+00:00",
        )
        for rec in (current, other_scope, expired):
            self.store.put(rec)
        # The existing freshness checker uses the current system clock; also test the explicit
        # validity window below to ensure expired records cannot be returned.
        results = self.store.eligible_records(scope="hg2/workflow", now="2026-10-20T02:00:00+00:00")
        self.assertNotIn("other-scope", {r["memory_id"] for r in results})
        self.assertNotIn("expired-lesson", {r["memory_id"] for r in results})

    def test_supersession_is_only_a_proposal_until_verifier_and_authority_exist(self):
        old = make_experience("old-lesson", "Use older unsafe retry assumption")
        new = make_experience(
            "new-lesson", "Use IN_DOUBT and reconcile first",
            supersedes="old-lesson",
            parent_memory_ids=["old-lesson"],
        )
        self.store.put(old)
        proposal = self.store.decide_supersession("old-lesson", new)
        self.assertEqual(proposal["status"], "SUPERSESSION_PROPOSED_NOT_APPLIED")
        self.assertEqual(self.store.get("old-lesson"), old)
        self.assertEqual(self.store.get("old-lesson")["status"], "ACTIVE")
        principal = __import__("hg.auth", fromlist=["BearerAuthenticator"]).BearerAuthenticator(
            "experience-test", {"audit.append"}, principal_id="alice"
        ).authenticate("Bearer experience-test")
        with self.assertRaisesRegex(ExperienceMemoryError, "EXPERIENCE_SUPERSESSION_VERIFIER_REQUIRED"):
            self.store.supersede("old-lesson", new, principal=principal)

    def test_supersession_decision_is_recorded_but_never_activates_or_rewrites(self):
        from hg.auth import BearerAuthenticator
        principal = BearerAuthenticator(
            "experience-test-success", {"audit.append"}, principal_id="alice"
        ).authenticate("Bearer experience-test-success")
        old = make_experience("old-supersede", "Older rule")
        new = make_experience(
            "new-supersede", "Proposed replacement",
            supersedes="old-supersede", parent_memory_ids=["old-supersede"],
        )
        self.store.put(old)
        result = self.store.supersede(
            "old-supersede", new, principal=principal, verifier_id="source-verifier-v1",
            verifier=lambda _record: (True, "evidence:source-receipt"),
        )
        self.assertEqual(result["result"], "SUPERSESSION_DECISION_RECORDED_NOT_ACTIVATED")
        self.assertFalse(result["automatic_activation"])
        self.assertEqual(self.store.get("old-supersede"), old)
        self.assertEqual(self.store.get("old-supersede")["status"], "ACTIVE")
        self.assertTrue(self.backing.verify_store_integrity()["ok"])

    def test_lineage_reports_parents_without_mutating_sources(self):
        parent = make_experience("parent-lesson", "Source lesson")
        child = make_experience(
            "child-lesson", "Derived lesson", parent_memory_ids=["parent-lesson"]
        )
        self.store.put(parent)
        self.store.put(child)
        lineage = self.store.lineage("child-lesson")
        self.assertEqual(lineage["root_memory_id"], "child-lesson")
        self.assertIn(
            {"from": "child-lesson", "to": "parent-lesson", "relation": "DERIVED_FROM"},
            lineage["edges"],
        )
        self.assertEqual(self.store.get("parent-lesson"), parent)

    def test_record_digest_mismatch_is_rejected(self):
        record = make_experience("bad-digest", "Evidence-bound item")
        record["scope"] = "different scope"
        with self.assertRaisesRegex(ExperienceMemoryError, "EXPERIENCE_RECORD_DIGEST_MISMATCH"):
            self.store.put(record)

    def test_conflicting_items_remain_unresolved(self):
        one = make_experience("conflict-one", "The recovery is safe")
        two = make_experience("conflict-two", "The recovery is unsafe")
        self.store.put(one)
        result = self.store.put(two)
        self.assertTrue(result["conflict"])
        self.assertEqual(len(self.store.conflicts()), 1)


if __name__ == "__main__":
    unittest.main()
