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
        with open(os.path.join(d, "head.json"), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertEqual(s.verify()["reason"], "checkpoint_unreadable")
        with self.assertRaises(HistoryError):
            StateStore(d)

    def test_checkpoint_rollback_mismatch(self):
        s, d = build()
        with open(os.path.join(d, "head.json"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"seq": 1, "head_hash": ZERO}))
        self.assertEqual(s.verify()["reason"], "checkpoint_mismatch")
        with self.assertRaises(HistoryError):
            StateStore(d)

    def test_state_projection_tamper(self):
        for field, mutate in (
            ("sessions", lambda doc: doc["sessions"]["a"].__setitem__("tampered", True)),
            ("counters", lambda doc: doc["counters"].__setitem__("session.created", 999)),
            ("schema", lambda doc: doc.__setitem__("schema", "TAMPERED")),
            ("runtime_id", lambda doc: doc.__setitem__("runtime_id", "TAMPERED")),
            ("product_id", lambda doc: doc.__setitem__("product_id", "TAMPERED")),
            ("last_seq", lambda doc: doc.__setitem__("last_seq", 999)),
            ("extra_field", lambda doc: doc.__setitem__("unexpected", True)),
        ):
            with self.subTest(field=field):
                s, d = build()
                self.addCleanup(shutil.rmtree, d, ignore_errors=True)
                p = os.path.join(d, "state.json")
                with open(p, encoding="utf-8") as fh:
                    doc = json.load(fh)
                mutate(doc)
                with open(p, "w", encoding="utf-8") as fh:
                    json.dump(doc, fh)
                with self.assertRaisesRegex(HistoryError, "state projection does not match history"):
                    StateStore(d)
                # Fail-closed means the rejected projection is not rewritten.
                with open(p, encoding="utf-8") as fh:
                    self.assertEqual(json.load(fh), doc)

    def test_state_projection_corrupt(self):
        s, d = build()
        with open(os.path.join(d, "state.json"), "w", encoding="utf-8") as fh:
            fh.write("not json")
        with self.assertRaises(HistoryError):
            StateStore(d)

    def test_torn_append_is_quarantined_only_with_anchored_state(self):
        s, d = build()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        tail = b'{"seq": 4, "event_id": "torn", "event_type": "sess'
        log = os.path.join(d, "history.jsonl")
        with open(log, "ab") as fh:
            fh.write(tail)
        recovered = StateStore(d)
        with open(log, "rb") as fh:
            self.assertTrue(fh.read().endswith(b"\n"))
        quarantines = [n for n in os.listdir(d) if n.startswith("history.incomplete-tail.")]
        receipts = [n for n in os.listdir(d) if n.startswith("history.recovery.") and n.endswith(".json")]
        self.assertEqual(len(quarantines), 1)
        self.assertEqual(len(receipts), 1)
        with open(os.path.join(d, quarantines[0]), "rb") as fh:
            self.assertEqual(fh.read(), tail)
        self.assertTrue(any(e["event_type"] == "history.state.recovered" for e in recovered.replay()))
        self.assertTrue(recovered.verify()["ok"])

    def test_torn_append_refused_when_checkpoint_not_anchored(self):
        s, d = build()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        with open(os.path.join(d, "history.jsonl"), "ab") as fh:
            fh.write(b'{"seq": 4, "event_id": "torn"')
        with open(os.path.join(d, "head.json"), "w", encoding="utf-8") as fh:
            json.dump({"seq": 1, "head_hash": ZERO}, fh)
        with self.assertRaises(HistoryError):
            StateStore(d)

    def test_tail_truncation_and_reorder_and_duplicate(self):
        for mutate in (lambda L: L[:-1], lambda L: [L[0], L[2], L[1]], lambda L: L + [L[-1]]):
            s, d = build()
            p = os.path.join(d, "history.jsonl")
            with open(p, encoding="utf-8") as fh:
                L = [x for x in fh.read().splitlines() if x.strip()]
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("\n".join(mutate(L)) + "\n")
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
