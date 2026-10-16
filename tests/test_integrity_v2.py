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
            with open(p, encoding="utf-8") as fh:
                L = [x for x in fh.read().splitlines() if x.strip()]
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("\n".join(mutate(L)) + "\n")
            self.assertFalse(s.verify()["ok"])
            with self.assertRaises(HistoryError):
                StateStore(d)
            shutil.rmtree(d, ignore_errors=True)

    def test_event_id_reuse_with_different_payload_is_rejected(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        store = StateStore(d)
        store.emit("session.created", {"session_id": "stable"}, event_id="fixed-id")
        with self.assertRaisesRegex(HistoryError, "event_id_conflict"):
            store.emit("session.created", {"session_id": "changed"}, event_id="fixed-id")
        self.assertEqual(store.replay()[-1]["payload"]["session_id"], "stable")
        self.assertTrue(store.verify()["ok"])

    def test_verify_detects_missing_checkpoint_and_projection(self):
        for artifact, reason in (("head.json", "checkpoint_missing"), ("state.json", "state_projection_missing")):
            with self.subTest(artifact=artifact):
                d = tempfile.mkdtemp()
                self.addCleanup(shutil.rmtree, d, ignore_errors=True)
                store = StateStore(d)
                os.remove(os.path.join(d, artifact))
                result = store.verify()
                self.assertFalse(result["ok"])
                self.assertEqual(result["reason"], reason)

    def test_verify_detects_projection_tamper(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        store = StateStore(d)
        with open(os.path.join(d, "state.json"), encoding="utf-8") as fh:
            doc = json.load(fh)
        doc["last_seq"] += 100
        with open(os.path.join(d, "state.json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        self.assertEqual(store.verify()["reason"], "state_projection_mismatch")

    def test_healthy_roundtrip_and_recovery(self):
        s, d = build()
        self.assertTrue(s.verify()["ok"])
        again = StateStore(d)
        self.assertEqual(len(again.replay()), 3)
        self.assertEqual(sorted(again._sessions), ["a", "b"])
        shutil.rmtree(d, ignore_errors=True)
