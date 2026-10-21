import os, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path: sys.path.insert(0, ROOT)
from hg.history import StateStore
from hg.memory import MemoryConflict, MemoryDenied, MemoryIdempotencyConflict, MemoryStore

class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.state = StateStore(self.tmp.name); self.mem = MemoryStore(self.state)
        self.grants = frozenset({"owner"})
        self.rec = {"id":"fact-1", "type":"fact", "title":"Canonical", "content":"HG2 owns HG", "scope_id":"owner"}
    def test_create_read_and_replay(self):
        r = self.mem.remember(self.rec, principal_id="p", grants=self.grants, idempotency_key="k1")
        self.assertEqual(r["version"], 1)
        self.assertEqual(self.mem.get("fact-1", grants=self.grants), r)
        reopened = MemoryStore(StateStore(self.tmp.name))
        self.assertEqual(reopened.get("fact-1", grants=self.grants), r)
    def test_idempotency_and_conflict(self):
        a = self.mem.remember(self.rec, principal_id="p", grants=self.grants, idempotency_key="k1")
        self.assertEqual(self.mem.remember(self.rec, principal_id="p", grants=self.grants, idempotency_key="k1"), a)
        changed = dict(self.rec, content="different")
        with self.assertRaises(MemoryIdempotencyConflict): self.mem.remember(changed, principal_id="p", grants=self.grants, idempotency_key="k1")
        with self.assertRaises(MemoryConflict): self.mem.remember(dict(self.rec, content="updated"), principal_id="p", grants=self.grants, idempotency_key="k2")
    def test_update_requires_exact_version(self):
        self.mem.remember(self.rec, principal_id="p", grants=self.grants, idempotency_key="k1")
        updated = dict(self.rec, content="v2")
        r = self.mem.remember(updated, principal_id="p", grants=self.grants, idempotency_key="k2", expected_version=1)
        self.assertEqual(r["version"], 2)
    def test_scope_denied(self):
        self.mem.remember(self.rec, principal_id="p", grants=self.grants, idempotency_key="k1")
        with self.assertRaises(MemoryDenied): self.mem.get("fact-1", grants={"other"})
        self.assertEqual(self.mem.list_active(grants={"other"}), [])
    def test_tombstone_not_resurrected(self):
        self.mem.remember(self.rec, principal_id="p", grants=self.grants, idempotency_key="k1")
        result = self.mem.delete("fact-1", principal_id="p", grants=self.grants, expected_version=1, idempotency_key="k2")
        self.assertEqual(result["status"], "tombstoned")
        self.assertIsNone(self.mem.get("fact-1", grants=self.grants))
        self.assertEqual(self.mem.list_active(grants=self.grants), [])
        reopened = MemoryStore(StateStore(self.tmp.name))
        self.assertIsNone(reopened.get("fact-1", grants=self.grants))
        with self.assertRaises(MemoryConflict):
            reopened.remember(self.rec, principal_id="p", grants=self.grants, idempotency_key="k3")
    def test_retrieve_and_context_manifest(self):
        self.mem.remember(self.rec, principal_id="p", grants=self.grants, idempotency_key="k1")
        result = self.mem.retrieve("HG2 owns", grants=self.grants)
        self.assertEqual([x["id"] for x in result["matches"]], ["fact-1"])
        self.assertFalse(result["manifest"]["model_called"])
        context = self.mem.build_context("HG2 owns", grants=self.grants)
        self.assertEqual(context["context"][0]["source_id"], "fact-1")
        self.assertTrue(context["context"][0]["content_is_untrusted_data"])
        self.assertFalse(context["manifest"]["model_called"])
        self.assertEqual(len(context["manifest"]["manifest_sha256"]), 64)
    def test_retrieval_matches_composed_and_decomposed_vietnamese(self):
        import unicodedata
        rec = {"id":"vn-memory", "type":"fact", "title":"Dữ liệu tiếng Việt",
               "content":"Cơ chế ghi nhớ phải truy hồi thông tin", "scope_id":"owner"}
        self.mem.remember(rec, principal_id="p", grants=self.grants, idempotency_key="vn-k1")
        composed = self.mem.retrieve("Cơ chế ghi nhớ phải truy hồi thông tin", grants=self.grants)
        decomposed = self.mem.retrieve(unicodedata.normalize("NFD", "Cơ chế ghi nhớ phải truy hồi thông tin"), grants=self.grants)
        self.assertEqual([x["id"] for x in composed["matches"]], [x["id"] for x in decomposed["matches"]])
        self.assertEqual(composed["matches"][0]["retrieval_method"], "unicode_normalized_lexical_overlap")

    def test_curated_aliases_recall_paraphrased_memory(self):
        rec = {"id":"favorite-color", "type":"fact", "title":"Favorite color",
               "content":"Cerulean", "scope_id":"owner",
               "aliases":["hue liked", "preferred shade", "favorite hue"]}
        self.mem.remember(rec, principal_id="p", grants=self.grants, idempotency_key="aliases-k1")
        result = self.mem.retrieve("Which hue is liked?", grants=self.grants)
        self.assertEqual([item["id"] for item in result["matches"]], ["favorite-color"])
        self.assertEqual(result["matches"][0]["retrieval_method"], "unicode_normalized_lexical_overlap")
        reopened = MemoryStore(StateStore(self.tmp.name))
        self.assertEqual(reopened.get("favorite-color", grants=self.grants)["aliases"],
                         ["favorite hue", "hue liked", "preferred shade"])

    def test_aliases_are_bounded_and_validated(self):
        from hg.memory import MemoryValidationError
        bad = dict(self.rec, aliases=[" "])
        with self.assertRaises(MemoryValidationError):
            self.mem.remember(bad, principal_id="p", grants=self.grants, idempotency_key="bad-alias")
        too_many = dict(self.rec, aliases=[f"alias-{i}" for i in range(33)])
        with self.assertRaises(MemoryValidationError):
            self.mem.remember(too_many, principal_id="p", grants=self.grants, idempotency_key="too-many-aliases")

    def test_retrieval_empty_or_punctuation_only_query_fails_closed(self):
        from hg.memory import MemoryValidationError
        for query in ("", "   ", "?!—..."):
            with self.subTest(query=query), self.assertRaises(MemoryValidationError):
                self.mem.retrieve(query, grants=self.grants)

    def test_claimed_verified_provenance_is_presented_as_unverified_context(self):
        import hashlib
        from hg.provenance_memory import create_memory_record
        from hg.task_contract import canonical_json
        provenance = create_memory_record(
            memory_id="fake-trust-meta", statement="project status is current",
            source_ref="source:test", source_digest="d" * 64,
            authority_ref="authority:test",
            observed_at="2026-01-01T00:00:00+00:00",
            expires_at="2027-01-01T00:00:00+00:00",
            memory_key="project.status")
        provenance["trust_level"] = "VERIFIED"
        unsigned = dict(provenance)
        unsigned.pop("record_digest", None)
        provenance["record_digest"] = hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()
        rec = {"id":"fake-trust", "type":"fact", "title":"Project status",
               "content":"project status is current", "scope_id":"owner",
               "provenance_metadata":provenance}
        self.mem.remember(rec, principal_id="p", grants=self.grants, idempotency_key="fake-trust-k1")
        ctx = self.mem.build_context("project status current", grants=self.grants)
        self.assertEqual(ctx["context"][0]["trust_status"], "UNVERIFIED")

    def test_expired_provenance_memory_is_suppressed_from_retrieval(self):
        from datetime import datetime, timezone
        from hg.provenance_memory import create_memory_record
        from unittest.mock import patch
        expired = create_memory_record(
            memory_id="expired-meta", statement="old project status",
            source_ref="source:test", source_digest="a" * 64,
            authority_ref="authority:test",
            observed_at="2026-01-01T00:00:00+00:00",
            expires_at="2026-06-01T00:00:00+00:00",
            memory_key="project.status",
        )
        rec = {"id":"expired-meta", "type":"fact", "title":"Project status",
               "content":"old project status", "scope_id":"owner",
               "provenance_metadata":expired}
        self.mem.remember(rec, principal_id="p", grants=self.grants, idempotency_key="expired-meta-k1")
        with patch("hg.provenance_memory.datetime") as dt:
            dt.fromisoformat.side_effect = datetime.fromisoformat
            dt.now.return_value = datetime(2026, 10, 19, tzinfo=timezone.utc)
            result = self.mem.retrieve("project status", grants=self.grants)
        self.assertNotIn("expired-meta", [item["id"] for item in result["matches"]])

    def test_missing_expiry_provenance_is_suppressed_from_retrieval(self):
        from hg.provenance_memory import create_memory_record
        provenance = create_memory_record(
            memory_id="missing-expiry-meta", statement="undated project status",
            source_ref="source:test", source_digest="a" * 64,
            authority_ref="authority:test",
            observed_at="2026-01-01T00:00:00+00:00",
            expires_at=None,
            memory_key="project.status",
        )
        self.assertIn("EXPIRY_POLICY_MISSING", provenance["blockers"])
        rec = {"id":"missing-expiry-meta", "type":"fact", "title":"Project status",
               "content":"undated project status", "scope_id":"owner",
               "provenance_metadata":provenance}
        self.mem.remember(rec, principal_id="p", grants=self.grants, idempotency_key="missing-expiry-meta-k1")
        result = self.mem.retrieve("project status", grants=self.grants)
        self.assertNotIn("missing-expiry-meta", [item["id"] for item in result["matches"]])

    def test_expiry_metadata_digest_tampering_is_rejected(self):
        from hg.provenance_memory import create_memory_record
        from hg.memory import MemoryValidationError
        provenance = create_memory_record(
            memory_id="tampered-meta", statement="current status",
            source_ref="source:test", source_digest="a" * 64,
            authority_ref="authority:test",
            observed_at="2026-01-01T00:00:00+00:00",
            expires_at="2026-12-01T00:00:00+00:00",
            memory_key="project.status",
        )
        provenance["expires_at"] = "2030-01-01T00:00:00+00:00"
        rec = {"id":"tampered-meta", "type":"fact", "title":"Project status",
               "content":"current status", "scope_id":"owner",
               "provenance_metadata":provenance}
        with self.assertRaises(MemoryValidationError):
            self.mem.remember(rec, principal_id="p", grants=self.grants, idempotency_key="tampered-meta-k1")

    def test_expired_provenance_is_blocked_by_api_context_evidence_gate(self):
        from datetime import datetime, timezone
        from hg.provenance_memory import create_memory_record
        from unittest.mock import patch
        provenance = create_memory_record(
            memory_id="expired-api-meta", statement="old project status",
            source_ref="source:test", source_digest="b" * 64,
            authority_ref="authority:test",
            observed_at="2026-01-01T00:00:00+00:00",
            expires_at="2026-06-01T00:00:00+00:00",
            memory_key="project.status")
        rec = {"id":"expired-api-meta", "type":"fact", "title":"Project status",
               "content":"old project status", "scope_id":"owner",
               "provenance_metadata":provenance}
        self.mem.remember(rec, principal_id="p", grants=self.grants, idempotency_key="expired-api-meta-k1")
        with patch("hg.provenance_memory.datetime") as dt:
            dt.fromisoformat.side_effect = datetime.fromisoformat
            dt.now.return_value = datetime(2026, 10, 19, tzinfo=timezone.utc)
            ctx = self.mem.build_context("project status", grants=self.grants)
        self.assertEqual(ctx["context"], [])
        self.assertEqual(ctx["manifest"]["selected"], [])

    def test_conflicting_provenance_memories_are_labeled_not_auto_resolved(self):
        from hg.provenance_memory import create_memory_record
        def metadata(memory_id, statement):
            return create_memory_record(
                memory_id=memory_id, statement=statement,
                source_ref="source:project", source_digest="c" * 64,
                authority_ref="authority:test",
                observed_at="2026-01-01T00:00:00+00:00",
                expires_at="2027-01-01T00:00:00+00:00",
                memory_key="project.status")
        ready = {"id":"project-ready", "type":"fact", "title":"Project status ready",
                 "content":"The project status is ready", "scope_id":"owner",
                 "provenance_metadata":metadata("project-ready-meta", "status is ready")}
        blocked = {"id":"project-blocked", "type":"fact", "title":"Project status blocked",
                   "content":"The project status is blocked", "scope_id":"owner",
                   "provenance_metadata":metadata("project-blocked-meta", "status is blocked")}
        self.mem.remember(ready, principal_id="p", grants=self.grants, idempotency_key="project-ready-k1")
        self.mem.remember(blocked, principal_id="p", grants=self.grants, idempotency_key="project-blocked-k1")
        result = self.mem.build_context("project status", grants=self.grants)
        self.assertEqual({b["memory_conflict_status"] for b in result["context"]}, {"CONFLICT_UNRESOLVED"})
        self.assertEqual({b["trust_status"] for b in result["context"]}, {"UNVERIFIED"})
        self.assertEqual({b["freshness_status"] for b in result["context"]}, {"WITHIN_EXPIRY"})

    def test_history_integrity_covers_memory_mutation(self):
        self.mem.remember(self.rec, principal_id="p", grants=self.grants, idempotency_key="k1")
        self.assertTrue(self.state.verify()["ok"])
        self.assertIn("memory.mutated", [e["event_type"] for e in self.state.replay()])

if __name__ == "__main__": unittest.main()
