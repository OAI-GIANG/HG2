import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.legacy_backend_reconcile import reconcile


class LegacyBackendReconciliationTests(unittest.TestCase):
    def test_read_only_source_reconciliation_and_content_redaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.json"
            state.write_text(json.dumps({"memory": [
                {"id": "same", "version": 2, "content": "same claim", "scope": "HG"},
                {"id": "conflict", "version": 1, "content": "json claim", "scope": "global"},
                {"id": "json-only", "version": 1, "content": "unshared", "scope": "HG"},
            ]}), encoding="utf-8")
            database = root / "backend.sqlite"
            con = sqlite3.connect(database)
            con.executescript("""
                CREATE TABLE memory(memory_id TEXT PRIMARY KEY, version INTEGER, claim TEXT, checksum TEXT);
                CREATE TABLE operations(kind TEXT, result_json TEXT);
                CREATE TABLE experience(id TEXT);
            """)
            con.executemany("INSERT INTO memory VALUES(?,?,?,?)", [
                ("same", 2, "same claim", "checksum-a"),
                ("conflict", 4, "different claim", "checksum-b"),
                ("db-only", 1, "quarantine me", "checksum-c"),
            ])
            con.executemany("INSERT INTO operations VALUES(?,?)", [
                ("memory.persist", '{"ok":true,"stored":true}'),
                ("memory.persist", '{"ok":false,"error":{"code":"VERSION_CONFLICT"}}'),
            ])
            con.commit()
            con.close()
            before = database.read_bytes()
            result = reconcile(state, database)
            self.assertEqual(result["memory_reconciliation"]["exact_duplicate_matches"], 1)
            self.assertEqual(result["memory_reconciliation"]["overlap_conflicts"], 1)
            self.assertEqual(result["memory_reconciliation"]["backend_only_count"], 1)
            self.assertEqual(result["memory_reconciliation"]["state_only_count"], 1)
            self.assertEqual(result["operations"]["result_categories"]["SUCCESS"], 1)
            self.assertEqual(result["operations"]["result_categories"]["FAIL_VERSION_CONFLICT"], 1)
            self.assertTrue(result["backend_source"]["stable_during_audit"])
            self.assertEqual(database.read_bytes(), before)
            report = json.dumps(result)
            for private in ("same claim", "json claim", "different claim", "quarantine me", "unshared"):
                self.assertNotIn(private, report)


if __name__ == "__main__":
    unittest.main()
