"""T-018 cross-context synchronization tests: two real processes, spool transport, fail-closed."""
import json, os, subprocess, sys, tempfile, unittest
from hg.history import StateStore
from hg.sync import BATCH_SCHEMA, SyncContext, SyncError, digest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL = "local-device-credential"


def ctx(context_id, base):
    return SyncContext(context_id, os.path.join(base, context_id, "state"), os.path.join(base, "spool"))


def child(code):
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT,
                          env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.a = ctx("ctx-a", self.tmp)
        self.b = ctx("ctx-b", self.tmp)

    def _publish(self, c, payload):
        return c.publish("note.created", payload)

    def _move(self, src, dst, name):
        os.replace(os.path.join(src.spool, "outbox", name), os.path.join(dst.spool, "inbox", name))

    def test_a_to_b_via_spool(self):
        out = self._publish(self.a, {"note": "from-a"})
        self._move(self.a, self.b, out["file"])
        res = self.b.import_batch(out["file"])
        self.assertEqual(len(res["accepted"]), 1)
        received = [r for r in self.b.store.replay() if r["event_type"] == "sync.received"]
        self.assertEqual(received[0]["payload"]["payload"]["note"], "from-a")
        self.assertEqual(received[0]["payload"]["origin_context"], "ctx-a")
        self.assertTrue(self.b.store.verify()["ok"])

    def test_b_to_a_via_spool(self):
        out = self._publish(self.b, {"note": "from-b"})
        self._move(self.b, self.a, out["file"])
        res = self.a.import_batch(out["file"])
        self.assertEqual(len(res["accepted"]), 1)
        self.assertTrue(self.a.store.verify()["ok"])
        self.assertEqual(self.a.store.replay()[-1]["payload"]["origin_context"], "ctx-b")

    def test_two_processes_are_used(self):
        code = ("import os,sys;sys.path.insert(0,%r);from hg.sync import SyncContext;"
                "p=%r;c=SyncContext('ctx-a',os.path.join(p,'ctx-a','state'),os.path.join(p,'spool'));"
                "print(c.publish('note.created',{'note':'from-child'})['file'])" % (ROOT, self.tmp))
        r = child(code)
        self.assertEqual(r.returncode, 0, r.stderr)
        name = r.stdout.strip()
        self.assertTrue(os.path.exists(os.path.join(self.a.spool, "outbox", name)))
        self._move(self.a, self.b, name)
        self.assertEqual(len(self.b.import_batch(name)["accepted"]), 1)

    def test_duplicate_event_id_is_idempotent(self):
        out = self._publish(self.a, {"note": "dup"})
        self._move(self.a, self.b, out["file"])
        self.b.import_batch(out["file"])
        with open(os.path.join(self.b.spool, "inbox", ".consumed-" + out["file"]), encoding="utf-8") as fh:
            raw = json.loads(fh.read())
        replay = os.path.join(self.b.spool, "inbox", "again.json")
        with open(replay, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(raw))
        before = len(self.b.store.replay())
        res = self.b.import_batch("again.json")
        self.assertEqual(res["accepted"], [])
        self.assertEqual(len(res["duplicates"]), 1)
        self.assertEqual(len(self.b.store.replay()), before)

    def test_duplicate_event_id_different_payload_is_conflict(self):
        out = self._publish(self.a, {"note": "one"})
        self._move(self.a, self.b, out["file"])
        self.b.import_batch(out["file"])
        with open(os.path.join(self.b.spool, "inbox", ".consumed-" + out["file"]), encoding="utf-8") as fh:
            raw = json.loads(fh.read())
        ev = raw["events"][0]
        changed_payload = {"note": "changed"}
        origin_core = dict(ev["origin_record"])
        origin_core.pop("record_hash")
        origin_core["payload"] = changed_payload
        changed_origin_hash = digest(origin_core)
        ev["origin_record"] = {**origin_core, "record_hash": changed_origin_hash}
        ev["origin_hash"] = changed_origin_hash
        ev["payload"] = changed_payload
        ev["payload_hash"] = digest(changed_payload)
        p = os.path.join(self.b.spool, "inbox", "conflict.json")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(raw))
        with self.assertRaises(SyncError):
            self.b.import_batch("conflict.json")
        self.assertTrue(os.path.exists(os.path.join(self.b.spool, "conflicts", "conflict.json")))

    def test_tampered_payload_rejected(self):
        out = self._publish(self.a, {"note": "x"})
        p = os.path.join(self.a.spool, "outbox", out["file"])
        with open(p, encoding="utf-8") as fh:
            raw = json.loads(fh.read())
        raw["events"][0]["payload"] = {"note": "tampered"}
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(raw))
        self._move(self.a, self.b, out["file"])
        with self.assertRaises(SyncError):
            self.b.import_batch(out["file"])

    def test_unsupported_schema_and_missing_field_rejected(self):
        p = os.path.join(self.a.spool, "outbox", "bad.json")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"schema": "OTHER", "events": [{}]}))
        self._move(self.a, self.b, "bad.json")
        with self.assertRaises(SyncError):
            self.b.import_batch("bad.json")
        ev = self.a.local_event("note.created", {"note": "m"})
        del ev["origin_hash"]
        with open(os.path.join(self.a.spool, "outbox", "missing.json"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"schema": BATCH_SCHEMA, "context_id": "ctx-a", "events": [ev]}))
        self._move(self.a, self.b, "missing.json")
        with self.assertRaises(SyncError):
            self.b.import_batch("missing.json")

    def test_multi_event_batch_preserves_origin_chain(self):
        first = self.a.local_event("note.created", {"n": 1})
        second = self.a.local_event("note.created", {"n": 2})
        p = os.path.join(self.a.spool, "outbox", "two-events.json")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"schema": BATCH_SCHEMA, "context_id": "ctx-a", "events": [first, second]}))
        self._move(self.a, self.b, "two-events.json")
        result = self.b.import_batch("two-events.json")
        self.assertEqual(result["accepted"], [first["event_id"], second["event_id"]])
        received = [r["payload"] for r in self.b.store.replay() if r["event_type"] == "sync.received"]
        self.assertEqual([r["origin_seq"] for r in received], [first["origin_seq"], second["origin_seq"]])
        self.assertTrue(self.b.store.verify()["ok"])

    def test_rehashed_payload_without_matching_origin_record_rejected(self):
        out = self._publish(self.a, {"note": "original"})
        p = os.path.join(self.a.spool, "outbox", out["file"])
        with open(p, encoding="utf-8") as fh:
            raw = json.loads(fh.read())
        raw["events"][0]["payload"] = {"note": "forged"}
        raw["events"][0]["payload_hash"] = digest(raw["events"][0]["payload"])
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(raw))
        self._move(self.a, self.b, out["file"])
        with self.assertRaises(SyncError):
            self.b.import_batch(out["file"])
        self.assertFalse(any(r["event_type"] == "sync.received" for r in self.b.store.replay()))

    def test_origin_sequence_gap_rejected_before_apply(self):
        first = self.a.local_event("note.created", {"n": 1})
        second = self.a.local_event("note.created", {"n": 2})
        second["origin_seq"] += 2
        origin_core = dict(second["origin_record"])
        origin_core.pop("record_hash")
        origin_core["seq"] = second["origin_seq"]
        second["origin_hash"] = digest(origin_core)
        second["origin_record"] = {**origin_core, "record_hash": second["origin_hash"]}
        p = os.path.join(self.a.spool, "outbox", "sequence-gap.json")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"schema": BATCH_SCHEMA, "context_id": "ctx-a", "events": [first, second]}))
        self._move(self.a, self.b, "sequence-gap.json")
        with self.assertRaises(SyncError):
            self.b.import_batch("sequence-gap.json")
        self.assertFalse(any(r["event_type"] == "sync.received" for r in self.b.store.replay()))

    def test_invalid_later_event_does_not_partially_apply_batch(self):
        first = self.a.local_event("note.created", {"n": 1})
        second = self.a.local_event("note.created", {"n": 2})
        del second["origin_hash"]
        p = os.path.join(self.a.spool, "outbox", "partial-invalid.json")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"schema": BATCH_SCHEMA, "context_id": "ctx-a", "events": [first, second]}))
        self._move(self.a, self.b, "partial-invalid.json")
        with self.assertRaises(SyncError):
            self.b.import_batch("partial-invalid.json")
        received = [r for r in self.b.store.replay() if r["event_type"] == "sync.received"]
        self.assertEqual(received, [])
        self.assertTrue(any(r["event_type"] == "sync.rejected" for r in self.b.store.replay()))

    def test_stale_in_batch_chain_and_self_origin_rejected(self):
        e1 = self.a.local_event("note.created", {"n": 1})
        e2 = self.a.local_event("note.created", {"n": 2})
        e2["origin_prev_hash"] = "0" * 64
        origin_core = dict(e2["origin_record"])
        origin_core.pop("record_hash")
        origin_core["prev_hash"] = e2["origin_prev_hash"]
        e2["origin_hash"] = digest(origin_core)
        e2["origin_record"] = {**origin_core, "record_hash": e2["origin_hash"]}
        with open(os.path.join(self.a.spool, "outbox", "chain.json"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"schema": BATCH_SCHEMA, "context_id": "ctx-a", "events": [e1, e2]}))
        self._move(self.a, self.b, "chain.json")
        with self.assertRaises(SyncError):
            self.b.import_batch("chain.json")
        own = self.b.local_event("note.created", {"n": 3})
        with open(os.path.join(self.b.spool, "outbox", "self.json"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"schema": BATCH_SCHEMA, "context_id": "ctx-b", "events": [own]}))
        os.replace(os.path.join(self.b.spool, "outbox", "self.json"), os.path.join(self.b.spool, "inbox", "self.json"))
        with self.assertRaises(SyncError):
            self.b.import_batch("self.json")

    def test_truncated_batch_rejected_and_audited(self):
        p = os.path.join(self.a.spool, "outbox", "trunc.json")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write('{"schema": "HG_SYNC_BATCH_V2", "events": [')
        self._move(self.a, self.b, "trunc.json")
        with self.assertRaises(SyncError):
            self.b.import_batch("trunc.json")
        self.assertTrue(any(r["op"] == "reject" for r in self.b.audit_records()))

    def test_concurrent_updates_do_not_overwrite(self):
        out_a = self._publish(self.a, {"note": "a"})
        out_b = self._publish(self.b, {"note": "b"})
        self._move(self.a, self.b, out_a["file"])
        self._move(self.b, self.a, out_b["file"])
        self.b.import_batch(out_a["file"])
        self.a.import_batch(out_b["file"])
        self.assertTrue(self.a.store.verify()["ok"])
        self.assertTrue(self.b.store.verify()["ok"])
        self.assertEqual(len(self.a.store.replay()), 3)
        self.assertEqual(len(self.b.store.replay()), 3)

    def test_restart_recovery_keeps_state_and_no_reapply(self):
        out = self._publish(self.a, {"note": "persist"})
        self._move(self.a, self.b, out["file"])
        self.b.import_batch(out["file"])
        before = self.b.store.audit_export()["head_hash"]
        reopened = ctx("ctx-b", self.tmp)
        self.assertEqual(reopened.store.audit_export()["head_hash"], before)
        self.assertTrue(reopened.store.verify()["ok"])
        with open(os.path.join(self.b.spool, "inbox", ".consumed-" + out["file"]), encoding="utf-8") as fh:
            raw = json.loads(fh.read())
        with open(os.path.join(self.b.spool, "inbox", "again2.json"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps(raw))
        self.assertEqual(reopened.import_batch("again2.json")["duplicates"], [out and raw["events"][0]["event_id"]])


if __name__ == "__main__":
    unittest.main()
