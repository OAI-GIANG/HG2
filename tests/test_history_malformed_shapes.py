"""Counter-tests: structurally invalid JSON records must fail closed."""
import json
import os
import tempfile
import unittest

from hg.history import HistoryError, StateStore, canonical, digest, history_record_contract, _HISTORY_V1_FIELDS, _HISTORY_V2_FIELDS, HISTORY_EVENT_SCHEMA_V2


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
        with open(os.path.join(tmp.name, "runtime_id"), "w", encoding="utf-8") as fh:
            fh.write("shape-test\n")
        return store, tmp.name


    def _valid_store(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = StateStore(tmp.name)
        return store, tmp.name

    def _rewrite_single_record(self, directory, mutate=None, raw=None, newline=True):
        path = os.path.join(directory, "history.jsonl")
        with open(path, encoding="utf-8") as fh:
            record = json.loads(fh.readline())
        if mutate:
            mutate(record)
        if raw is None:
            record.pop("record_hash", None)
            record["record_hash"] = digest(record)
            line = canonical(record)
            head = {"seq": record.get("seq", 1), "head_hash": record["record_hash"]}
        else:
            line = raw
            head = None
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(line + ("\n" if newline else ""))
        if head is not None:
            with open(os.path.join(directory, "head.json"), "w", encoding="utf-8") as fh:
                json.dump(head, fh)

    def _valid_v1_record(self):
        store, _ = self._valid_store()
        return dict(store.replay()[0])

    def _valid_v2_record_shape(self):
        record = self._valid_v1_record()
        record.update({
            "event_schema": HISTORY_EVENT_SCHEMA_V2,
            "actor_id": "principal-a",
            "authority_context": {"principal": "principal-a", "scope": "audit.append"},
            "authorization_action": "audit.append",
            "idempotency_key": "history-contract-test-1",
        })
        return record

    def test_history_contract_classifies_legacy_v1_without_changing_record(self):
        record = self._valid_v1_record()
        before = dict(record)
        self.assertEqual(history_record_contract(record), "V1")
        self.assertEqual(record, before)
        self.assertEqual(set(record), _HISTORY_V1_FIELDS)

    def test_history_contract_classifies_well_formed_v2_as_structure_only(self):
        record = self._valid_v2_record_shape()
        self.assertEqual(history_record_contract(record), "V2")
        self.assertEqual(set(record), _HISTORY_V2_FIELDS)
        # Classifying a V2 record is not permission to append it to the legacy V1 store.
        store, _ = self._valid_store()
        with self.assertRaises(TypeError):
            store.emit("audit.note", {"note": "no authority permit provided"},
                       actor_id="principal-a", authority_context={"principal": "principal-a", "scope": "audit.append"})

    def test_history_contract_rejects_v2_authority_and_idempotency_mismatch(self):
        invalid = []
        bad_actor = self._valid_v2_record_shape(); bad_actor["actor_id"] = ""
        invalid.append((bad_actor, "V2 actor invalid"))
        bad_scope = self._valid_v2_record_shape(); bad_scope["authority_context"] = {"principal": "principal-a", "scope": "workflow.task.create"}
        invalid.append((bad_scope, "V2 authority context invalid"))
        bad_action = self._valid_v2_record_shape()
        bad_action["authorization_action"] = ""
        bad_action["authority_context"] = {"principal": "principal-a", "scope": ""}
        invalid.append((bad_action, "V2 authorization action invalid"))
        bad_key = self._valid_v2_record_shape(); bad_key["idempotency_key"] = "  "
        invalid.append((bad_key, "V2 idempotency key invalid"))
        for record, reason in invalid:
            with self.subTest(reason=reason), self.assertRaisesRegex(HistoryError, reason):
                history_record_contract(record)

    def test_history_contract_rejects_ambiguous_or_unknown_schema_fields(self):
        legacy = self._valid_v1_record(); legacy["unexpected"] = True
        with self.assertRaisesRegex(HistoryError, "V1 record schema mismatch"):
            history_record_contract(legacy)
        v2 = self._valid_v2_record_shape(); v2["unexpected"] = True
        with self.assertRaisesRegex(HistoryError, "V2 record schema mismatch"):
            history_record_contract(v2)

    def test_all_emitted_required_fields_are_required(self):
        missing_fields = (
            "seq", "event_id", "event_type", "recorded_at", "correlation_id",
            "causation_id", "product_id", "runtime_id", "schema", "payload", "prev_hash",
        )
        for field in missing_fields:
            with self.subTest(field=field):
                store, directory = self._valid_store()
                self._rewrite_single_record(directory, lambda rec, f=field: rec.pop(f))
                self.assertFalse(store.verify()["ok"], field)
                with self.assertRaises(HistoryError, msg=field):
                    StateStore(directory)

    def test_invalid_field_values_fail_closed_even_with_recomputed_hash(self):
        invalid_values = (
            ("seq_bool", lambda r: r.update(seq=True)),
            ("seq_zero", lambda r: r.update(seq=0)),
            ("event_id_empty", lambda r: r.update(event_id="")),
            ("event_type_empty", lambda r: r.update(event_type="")),
            ("event_type_whitespace", lambda r: r.update(event_type="   ")),
            ("recorded_at_bool", lambda r: r.update(recorded_at=True)),
            ("recorded_at_infinite", lambda r: r.update(recorded_at=float("inf"))),
            ("correlation_id_empty", lambda r: r.update(correlation_id="")),
            ("causation_id_wrong_type", lambda r: r.update(causation_id=[])),
            ("product_id_wrong", lambda r: r.update(product_id="OTHER")),
            ("runtime_id_empty", lambda r: r.update(runtime_id="")),
            ("runtime_id_mismatch", lambda r: r.update(runtime_id="other-runtime")),
            ("schema_wrong", lambda r: r.update(schema="OTHER")),
            ("payload_wrong_type", lambda r: r.update(payload=[])),
            ("prev_hash_wrong_type", lambda r: r.update(prev_hash=7)),
        )
        for name, mutate in invalid_values:
            with self.subTest(case=name):
                store, directory = self._valid_store()
                self._rewrite_single_record(directory, mutate)
                self.assertFalse(store.verify()["ok"], name)
                with self.assertRaises(HistoryError, msg=name):
                    StateStore(directory)

    def test_blank_line_and_missing_final_newline_fail_closed(self):
        for case in ("blank_line", "missing_final_newline"):
            with self.subTest(case=case):
                store, directory = self._valid_store()
                path = os.path.join(directory, "history.jsonl")
                with open(path, encoding="utf-8") as fh:
                    valid = fh.read().rstrip("\n")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(valid + ("\n\n" if case == "blank_line" else ""))
                self.assertFalse(store.verify()["ok"], case)
                with self.assertRaises(HistoryError, msg=case):
                    StateStore(directory)

    def test_invalid_utf8_fails_closed_without_raw_decode_error(self):
        store, directory = self._valid_store()
        path = os.path.join(directory, "history.jsonl")
        with open(path, "wb") as fh:
            fh.write(b"\xff\xfe\n")
        result = store.verify()
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "history_unreadable")
        with self.assertRaisesRegex(HistoryError, "history unreadable"):
            StateStore(directory)

    def test_checkpoint_json_non_object_fails_closed(self):
        for raw in ("[]", "null", '"checkpoint"', "42"):
            with self.subTest(raw=raw):
                store, directory = self._valid_store()
                with open(os.path.join(directory, "head.json"), "w", encoding="utf-8") as fh:
                    fh.write(raw)
                self.assertEqual(store.verify()["reason"], "checkpoint_not_object")
                with self.assertRaisesRegex(HistoryError, "head checkpoint is not an object"):
                    StateStore(directory)

    def test_valid_history_remains_compatible_after_restart(self):
        store, directory = self._valid_store()
        store.emit("session.created", {"session_id": "compat-session", "product": "HG"})
        self.assertTrue(store.verify()["ok"])
        restarted = StateStore(directory)
        self.assertEqual(len(restarted.replay()), 2)
        self.assertEqual(restarted.replay()[0]["event_type"], "hg.genesis")
        self.assertEqual(restarted.replay()[1]["event_type"], "session.created")
        self.assertTrue(restarted.verify()["ok"])

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
        store, directory = self._valid_store()
        self._rewrite_single_record(directory, lambda record: record.update(seq=True))
        self.assertEqual(store.verify()["reason"], "record_invalid_field_types_line_1")
        with self.assertRaisesRegex(HistoryError, "record has invalid field types"):
            StateStore(directory)


if __name__ == "__main__":
    unittest.main()
