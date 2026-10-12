"""Counter-tests for HG2 history/checkpoint fail-closed policy (P0 remediation)."""
import json, os, shutil, tempfile, unittest
from hg.history import ZERO, HistoryError, StateStore


def build():
    d = tempfile.mkdtemp()
    s = StateStore(d)
    s.emit("session.created", {"session_id": "a"})
    s.emit("session.created", {"session_id": "b"})
    return s, d


class IntegrityPolicyTests(unittest.TestCase):
    def tearDown(self):
        pass

    def test_fresh_directory_initialises(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        s = StateStore(d)
        self.assertEqual(len(s.replay()), 1)
        self.assertTrue(s.verify()["ok"])

    def test_missing_checkpoint_is_fail_closed(self):
        s, d = build(); os.remove(os.path.join(d, "head.json"))
        with self.assertRaises(HistoryError):
            StateStore(d)
        self.assertIn(StateStore.__name__, "StateStore")

    def test_missing_log_with_state_present_is_fail_closed(self):
        s, d = build(); os.remove(os.path.join(d, "history.jsonl"))
        self.assertEqual(s.verify()["reason"], "log_missing_while_state_present")
        with self.assertRaises(HistoryError):
            StateStore(d)

    def test_missing_log_and_state_but_runtime_id_present(self):
        s, d = build()
        os.remove(os.path.join(d, "history.jsonl")); os.remove(os.path.join(d, "head.json")); os.remove(os.path.join(d, "state.json"))
        with self.assertRaises(HistoryError):
            StateStore(d)

    def test_corrupt_checkpoint_json(self):
        s, d = build()
        open(os.path.join(d, "head.json"), "w", encoding="utf-8").write("{not json")
        self.assertEqual(s.verify()["reason"], "checkpoint_unreadable")
        with self.assertRaises(HistoryError):
            StateStore(d)

    def test_checkpoint_rollback_mismatch(self):
        s, d = build()
        open(os.path.join(d, "head.json"), "w", encoding="utf-8").write(json.dumps({"seq": 1, "head_hash": ZERO}))
        self.assertEqual(s.verify()["reason"], "checkpoint_mismatch")
        with self.assertRaises(HistoryError):
            StateStore(d)

    def test_state_projection_tamper(self):
        s, d = build()
        p = os.path.join(d, "state.json")
        doc = json.loads(open(p, encoding="utf-8").read())
        doc["sessions"] = {}
        open(p, "w", encoding="utf-8").write(json.dumps(doc))
        with self.assertRaises(HistoryError):
            StateStore(d)

    def test_state_projection_corrupt(self):
        s, d = build()
        open(os.path.join(d, "state.json"), "w", encoding="utf-8").write("not json")
        with self.assertRaises(HistoryError):
            StateStore(d)

    def test_torn_append_is_fail_closed(self):
        s, d = build()
        with open(os.path.join(d, "history.jsonl"), "a", encoding="utf-8") as fh:
            fh.write('{"seq": 4, "event_id": "torn", "event_type": "sess')  # interrupted write, no newline
        with self.assertRaises(HistoryError):
            StateStore(d)

    def test_tail_truncation_and_reorder_and_duplicate(self):
        for mutate in (lambda L: L[:-1], lambda L: [L[0], L[2], L[1]], lambda L: L + [L[-1]]):
            s, d = build()
            p = os.path.join(d, "history.jsonl")
            L = [x for x in open(p, encoding="utf-8").read().splitlines() if x.strip()]
            open(p, "w", encoding="utf-8").write("\n".join(mutate(L)) + "\n")
            self.assertFalse(s.verify()["ok"])
            with self.assertRaises(HistoryError):
                StateStore(d)
            shutil.rmtree(d, ignore_errors=True)

    def test_healthy_roundtrip_and_recovery(self):
        s, d = build()
        self.assertTrue(s.verify()["ok"])
        again = StateStore(d)
        self.assertEqual(len(again.replay()), 3)
        self.assertEqual(sorted(again._sessions), ["a", "b"])
        shutil.rmtree(d, ignore_errors=True)
