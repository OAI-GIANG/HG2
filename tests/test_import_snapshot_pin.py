import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.import_legacy_state import import_snapshot


class ImportSnapshotPinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "product"
        (self.root / "core/runtime/data/library").mkdir(parents=True)
        self.src = self.root / "state.json"
        self.src.write_text(json.dumps({"memory": [{"id": "m1", "title": "T",
            "content": "C", "scope": "HG", "version": 1, "status": "active"}],
            "library": [], "message": [], "conversations": [], "phone_devices": []}),
            encoding="utf-8")
        self.db = self.root / "backend.sqlite"
        con = sqlite3.connect(self.db)
        con.execute("CREATE TABLE memory(memory_id TEXT PRIMARY KEY,version INTEGER,claim TEXT,checksum TEXT)")
        con.execute("CREATE TABLE operations(op_key TEXT PRIMARY KEY,op_id TEXT,kind TEXT,result_json TEXT,created_at TEXT)")
        con.execute("INSERT INTO memory VALUES(?,?,?,?)", ("m1",1,"C","checksum"))
        con.commit()
        con.close()
        self.db_hash = __import__("hashlib").sha256(self.db.read_bytes()).hexdigest()

    def test_dryrun_records_pinned_reconciliation_plan_and_never_creates_target(self):
        target = self.root / "target"
        out = import_snapshot(self.src, self.root, target, False, backend_db=self.db,
                              expected_backend_sha256=self.db_hash)
        self.assertEqual(out["status"], "DRY_RUN_ONLY")
        self.assertEqual(out["backend_import_plan"]["exact_duplicate_events"], 1)
        self.assertEqual(out["backend_import_plan"]["backend_only_quarantine_events"], 0)
        self.assertFalse(out["backend_import_plan"]["database_mutation_performed"])
        self.assertFalse(target.exists())

    def test_wrong_backend_hash_fails_before_target_creation(self):
        target = self.root / "target"
        with self.assertRaisesRegex(ValueError, "does not match"):
            import_snapshot(self.src, self.root, target, True, backend_db=self.db,
                            expected_backend_sha256="0" * 64)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
