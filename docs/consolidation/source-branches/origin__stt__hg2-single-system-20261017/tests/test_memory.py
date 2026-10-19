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
    def test_history_integrity_covers_memory_mutation(self):
        self.mem.remember(self.rec, principal_id="p", grants=self.grants, idempotency_key="k1")
        self.assertTrue(self.state.verify()["ok"])
        self.assertIn("memory.mutated", [e["event_type"] for e in self.state.replay()])

if __name__ == "__main__": unittest.main()
