"""Counter-tests for HG2 history/checkpoint fail-closed policy (P0 remediation)."""
import json, multiprocessing, os, shutil, tempfile, unittest
from pathlib import Path
from unittest import mock
from hg.history import ZERO, HistoryError, StateStore


def build():
    d = tempfile.mkdtemp()
    s = StateStore(d)
    s.emit("session.created", {"session_id": "a"})
    s.emit("session.created", {"session_id": "b"})
    return s, d



def _append_from_process(directory, index):
    StateStore(directory).emit("concurrency.probe", {"writer": index},
                               event_id="process-%d" % index)


class IntegrityPolicyTests(unittest.TestCase):
    def tearDown(self):
        pass

    def test_fresh_directory_initialises(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        s = StateStore(d)
        self.assertEqual(len(s.replay()), 1)
        self.assertTrue(s.verify()["ok"])

    def test_json_numeric_type_substitution_is_detected(self):
        cases = (
            ("head-bool-seq", "head.json", lambda doc: doc.__setitem__("seq", True), "checkpoint_mismatch"),
            ("head-float-seq", "head.json", lambda doc: doc.__setitem__("seq", 1.0), "checkpoint_mismatch"),
            ("head-extra-field", "head.json", lambda doc: doc.__setitem__("unexpected", True), "checkpoint_mismatch"),
            ("projection-bool-last-seq", "state.json", lambda doc: doc.__setitem__("last_seq", True), "state_projection_mismatch"),
            ("projection-float-last-seq", "state.json", lambda doc: doc.__setitem__("last_seq", 1.0), "state_projection_mismatch"),
            ("projection-bool-counter", "state.json", lambda doc: doc["counters"].__setitem__("hg.genesis", True), "state_projection_mismatch"),
            ("projection-float-counter", "state.json", lambda doc: doc["counters"].__setitem__("hg.genesis", 1.0), "state_projection_mismatch"),
            ("projection-extra-field", "state.json", lambda doc: doc.__setitem__("unexpected", True), "state_projection_mismatch"),
        )
        for name, filename, mutate, reason in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as d:
                store = StateStore(d)
                path = Path(d) / filename
                doc = json.loads(path.read_text(encoding="utf-8"))
                mutate(doc)
                path.write_text(json.dumps(doc), encoding="utf-8")
                tampered = path.read_bytes()
                self.assertEqual(store.verify()["reason"], reason)
                with self.assertRaises(HistoryError):
                    StateStore(d)
                self.assertEqual(path.read_bytes(), tampered)

    def test_runtime_identity_whitespace_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            store = StateStore(d)
            path = Path(d) / "runtime_id"
            path.write_text(" " + store.runtime_id + "  \n", encoding="utf-8")
            tampered = path.read_bytes()
            self.assertEqual(store.verify()["reason"], "runtime_identity_malformed")
            with self.assertRaisesRegex(HistoryError, "runtime identity malformed"):
                StateStore(d)
            self.assertEqual(path.read_bytes(), tampered)

    def test_emit_rejects_invalid_input_before_durable_write(self):
        with tempfile.TemporaryDirectory() as d:
            store = StateStore(d)
            original = {path: Path(getattr(store, attr)).read_bytes()
                        for attr, path in (("log", "history.jsonl"),
                                           ("state", "state.json"),
                                           ("head", "head.json"))}
            invalid_cases = (("", {}), (123, {}), ("probe.invalid", []),
                             ("probe.invalid", None), ("probe.invalid", "not-an-object"))
            for event_type, payload in invalid_cases:
                with self.subTest(event_type=event_type, payload_type=type(payload).__name__):
                    with self.assertRaises(HistoryError):
                        store.emit(event_type, payload, event_id="valid-event-id")
                    for attr, path in (("log", "history.jsonl"),
                                       ("state", "state.json"),
                                       ("head", "head.json")):
                        self.assertEqual(Path(getattr(store, attr)).read_bytes(), original[path])
                    self.assertTrue(store.verify()["ok"])
            for event_id in ("", 123, True, 1.5, [], {}):
                with self.subTest(event_id=repr(event_id)):
                    with self.assertRaises(HistoryError):
                        store.emit("probe.valid", {}, event_id=event_id)
                    for attr, path in (("log", "history.jsonl"),
                                       ("state", "state.json"),
                                       ("head", "head.json")):
                        self.assertEqual(Path(getattr(store, attr)).read_bytes(), original[path])
                    self.assertTrue(store.verify()["ok"])
            reopened = StateStore(d)
            self.assertEqual(len(reopened.replay()), 1)
            self.assertTrue(reopened.verify()["ok"])

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

    def test_verify_fails_closed_when_checkpoint_missing(self):
        s, d = build()
        os.remove(os.path.join(d, "head.json"))
        self.assertEqual(s.verify()["reason"], "checkpoint_missing")
        with self.assertRaises(HistoryError):
            StateStore(d)

    def test_missing_state_projection_is_fail_closed_and_not_recreated(self):
        s, d = build()
        p = os.path.join(d, "state.json")
        os.remove(p)
        self.assertEqual(s.verify()["reason"], "state_projection_missing")
        with self.assertRaises(HistoryError):
            StateStore(d)
        self.assertFalse(os.path.exists(p))

    def test_missing_runtime_identity_is_fail_closed_and_not_recreated(self):
        s, d = build()
        p = os.path.join(d, "runtime_id")
        os.remove(p)
        self.assertEqual(s.verify()["reason"], "runtime_identity_missing")
        with self.assertRaises(HistoryError):
            StateStore(d)
        self.assertFalse(os.path.exists(p))

    def test_runtime_identity_tamper_is_detected(self):
        s, d = build()
        p = os.path.join(d, "runtime_id")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("substituted-runtime-id\n")
        self.assertEqual(s.verify()["reason"], "runtime_identity_mismatch")
        with self.assertRaises(HistoryError):
            StateStore(d)

    def test_verify_detects_projection_tamper_without_repair(self):
        s, d = build()
        p = os.path.join(d, "state.json")
        with open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
        doc["counters"]["session.created"] = 999
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        self.assertEqual(s.verify()["reason"], "state_projection_mismatch")
        with open(p, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), doc)

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

    def test_shared_directory_writers_refresh_under_exclusive_lock(self):
        with tempfile.TemporaryDirectory() as d:
            first = StateStore(d)
            second = StateStore(d)
            first.emit("probe.first", {"n": 1}, event_id="writer-first")
            second.emit("probe.second", {"n": 2}, event_id="writer-second")
            self.assertTrue(first.verify()["ok"])
            self.assertTrue(second.verify()["ok"])
            reopened = StateStore(d)
            self.assertEqual(reopened.verify()["events"], 3)

    def test_persistence_failure_poison_prevents_silent_repair(self):
        with tempfile.TemporaryDirectory() as d:
            store = StateStore(d)
            original_write_state = store._write_state
            calls = {"count": 0}

            def fail_once():
                calls["count"] += 1
                if calls["count"] == 1:
                    raise OSError("injected state projection failure")
                return original_write_state()

            store._write_state = fail_once
            with self.assertRaisesRegex(OSError, "injected state projection failure"):
                store.emit("probe.partial", {"n": 1}, event_id="partial-write")
            before_state = Path(store.state).read_bytes()
            before_head = Path(store.head).read_bytes()
            with self.assertRaisesRegex(HistoryError, "poisoned"):
                store.emit("probe.next", {"n": 2}, event_id="must-not-repair")
            self.assertEqual(Path(store.state).read_bytes(), before_state)
            self.assertEqual(Path(store.head).read_bytes(), before_head)
            self.assertFalse(store.verify()["ok"])

    def test_runtime_identity_directory_fsync_failure_fails_initialization(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch("hg.history._fsync_directory",
                            side_effect=HistoryError("injected runtime directory fsync failure")):
                with self.assertRaisesRegex(HistoryError, "runtime identity could not be initialized durably"):
                    StateStore(d)

    def test_state_projection_fsync_failure_poison_store(self):
        with tempfile.TemporaryDirectory() as d:
            store = StateStore(d)
            real_fsync = os.fsync
            calls = {"count": 0}

            def fail_second_fsync(fd):
                calls["count"] += 1
                if calls["count"] == 2:
                    raise OSError("injected file fsync failure")
                return real_fsync(fd)

            with mock.patch("hg.history.os.fsync", side_effect=fail_second_fsync):
                with self.assertRaisesRegex(OSError, "injected file fsync failure"):
                    store.emit("probe.fsync", {"n": 1}, event_id="fsync-failure")
            with self.assertRaisesRegex(HistoryError, "poisoned"):
                store.emit("probe.after-fsync-failure", {"n": 2}, event_id="must-not-repair")
            self.assertFalse(store.verify()["ok"])

    def test_state_replace_failure_poison_store(self):
        with tempfile.TemporaryDirectory() as d:
            store = StateStore(d)
            with mock.patch("hg.history.os.replace", side_effect=OSError("injected replace failure")):
                with self.assertRaisesRegex(OSError, "injected replace failure"):
                    store.emit("probe.replace", {"n": 1}, event_id="replace-failure")
            with self.assertRaisesRegex(HistoryError, "poisoned"):
                store.emit("probe.after-replace-failure", {"n": 2}, event_id="must-not-repair")
            self.assertFalse(store.verify()["ok"])

    def test_directory_fsync_failure_is_not_reported_as_durable(self):
        with tempfile.TemporaryDirectory() as d:
            store = StateStore(d)
            with mock.patch("hg.history._fsync_directory",
                            side_effect=HistoryError("injected directory fsync failure")):
                with self.assertRaisesRegex(HistoryError, "injected directory fsync failure"):
                    store.emit("probe.directory-fsync", {"n": 1},
                               event_id="directory-fsync-failure")
            with self.assertRaisesRegex(HistoryError, "poisoned"):
                store.emit("probe.after-directory-fsync-failure", {"n": 2},
                           event_id="must-not-repair")

    def test_concurrent_process_writers_preserve_hash_chain(self):
        with tempfile.TemporaryDirectory() as d:
            StateStore(d)
            count = 6
            workers = [multiprocessing.Process(target=_append_from_process, args=(d, i))
                       for i in range(count)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(20)
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                    worker.join()
                    self.fail("concurrent writer process timed out")
                self.assertEqual(worker.exitcode, 0)
            reopened = StateStore(d)
            result = reopened.verify()
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["events"], count + 1)

    def test_checkpoint_wrong_json_type_is_normalized_to_history_error(self):
        store, d = build()
        with open(store.head, "w", encoding="utf-8") as fh:
            json.dump([], fh)
        with self.assertRaisesRegex(HistoryError, "checkpoint"):
            StateStore(d)

    def test_healthy_roundtrip_and_recovery(self):
        s, d = build()
        self.assertTrue(s.verify()["ok"])
        again = StateStore(d)
        self.assertEqual(len(again.replay()), 3)
        self.assertEqual(sorted(again._sessions), ["a", "b"])
        shutil.rmtree(d, ignore_errors=True)
