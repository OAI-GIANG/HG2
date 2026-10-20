"""Crash-boundary regression for the canonical workflow task store.

This is an isolated temporary-database test. It does not point at live runtime state.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hg.sqlite_state import SQLiteStateStore


class WorkflowCrashRecoveryTests(unittest.TestCase):
    def test_process_exit_mid_transaction_leaves_no_partial_event_or_projection(self):
        with tempfile.TemporaryDirectory() as td:
            store = SQLiteStateStore(td)
            before = store.verify()
            self.assertTrue(before["ok"])
            self.assertEqual(before["events"], 1)
            store.close()

            # Simulate abrupt process death after partial event/projection writes but
            # before COMMIT. os._exit deliberately bypasses Python cleanup handlers.
            code = r"""
import os, sys
from hg.sqlite_state import SQLiteStateStore
store = SQLiteStateStore(sys.argv[1])
db = store._conn
db.execute("BEGIN IMMEDIATE")
db.execute(
    "INSERT INTO events(sequence,event_id,idempotency_key,event_type,event_json,previous_digest,record_digest) "
    "VALUES(2,'crash-partial-event',NULL,'workflow.task.created','{}','" + ('0' * 64) + "','" + ('1' * 64) + "')"
)
db.execute("INSERT INTO tasks(task_id,task_json) VALUES('crash-partial-task','{}')")
os._exit(17)
"""
            env = dict(os.environ)
            repo_root = str(Path(__file__).resolve().parents[1])
            env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")
            result = subprocess.run(
                [sys.executable, "-c", code, td],
                cwd=repo_root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=10,
            )
            self.assertEqual(result.returncode, 17, result.stderr.decode("utf-8", "replace"))

            reopened = SQLiteStateStore(td)
            try:
                verification = reopened.verify()
                self.assertTrue(verification["ok"], verification)
                self.assertEqual(verification["events"], 1)
                self.assertIsNone(reopened.get_task("crash-partial-task"))
                replayed = reopened.replay()
                self.assertEqual(len(replayed), 1)
                self.assertEqual(replayed[0]["event_type"], "hg.genesis")
                self.assertEqual(reopened._conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
