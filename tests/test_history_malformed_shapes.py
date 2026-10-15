"""Counter-tests: structurally invalid JSON records must fail closed."""
import json
import os
import tempfile
import unittest

from hg.history import HistoryError, StateStore


class MalformedHistoryShapeTests(unittest.TestCase):
    def _store_with_line(self, raw):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "history.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(raw + "\n")
        store = StateStore.__new__(StateStore)
        store.dir = tmp.name
        store.log = path
        store.head = os.path.join(tmp.name, "head.json")
        store.state = os.path.join(tmp.name, "state.json")
        store._events = []
        store._by_id = {}
        store._sessions = {}
        store._counters = {}
        store.runtime_id = "shape-test"
        return store, tmp.name

    def test_non_object_json_fails_verify_closed(self):
        for raw in ("[]", "null", '"event"', "42"):
            with self.subTest(raw=raw):
                store, _ = self._store_with_line(raw)
                result = store.verify()
                self.assertFalse(result["ok"])
                self.assertEqual(result["reason"], "record_not_object_line_1")

    def test_non_object_json_fails_initialization_with_history_error(self):
        for raw in ("[]", "null", '"event"', "42"):
            with self.subTest(raw=raw):
                _, directory = self._store_with_line(raw)
                with self.assertRaisesRegex(HistoryError, "record is not an object"):
                    StateStore(directory)

    def test_missing_required_field_fails_closed(self):
        store, directory = self._store_with_line(json.dumps({"seq": 1}))
        self.assertEqual(store.verify()["reason"], "record_missing_fields_line_1")
        with self.assertRaisesRegex(HistoryError, "record missing required fields"):
            StateStore(directory)

    def test_invalid_field_types_fail_closed(self):
        record = {"seq": True, "event_id": "e1", "event_type": "hg.genesis",
                  "payload": {}, "prev_hash": "0" * 64, "record_hash": "0" * 64}
        store, directory = self._store_with_line(json.dumps(record))
        self.assertEqual(store.verify()["reason"], "record_invalid_field_types_line_1")
        with self.assertRaisesRegex(HistoryError, "record has invalid field types"):
            StateStore(directory)


if __name__ == "__main__":
    unittest.main()
