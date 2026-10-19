"""Isolated prototype integration: SyncContext reuses PhoneRuntime's one store."""
import os
import tempfile
import unittest
from unittest.mock import patch

from hg.phone_runtime import PhoneRuntime
from hg.sync import SyncContext


class PhoneRuntimeSyncIntegrationTests(unittest.TestCase):
    def test_phone_runtime_explicit_sync_configuration_reuses_single_store(self):
        from hg.sync_auth import AuthenticatedBatchGate
        class Keys:
            def get_peer_key(self, peer_id, key_id):
                return b"k" * 32 if (peer_id, key_id) == ("peer-b", "key-b") else None
        class Anchor:
            def __init__(self): self.values = {}
            def read_anchor(self, peer_id): return dict(self.values[peer_id]) if peer_id in self.values else None
            def initialize_anchor(self, peer_id, checkpoint): self.values.setdefault(peer_id, dict(checkpoint))
            def advance_anchor(self, peer_id, expected, proposed):
                if self.values.get(peer_id) != expected: raise ValueError("anchor compare-and-advance conflict")
                if proposed["seq"] <= expected["seq"]: raise ValueError("anchor must advance")
                self.values[peer_id] = dict(proposed)
        with tempfile.TemporaryDirectory() as td:
            state = os.path.join(td, "state")
            spool = os.path.join(td, "spool")
            cursor = os.path.join(td, "cursor", "peer-b.json")
            gate = AuthenticatedBatchGate(key_provider=Keys(),
                checkpoints={"peer-b": {"seq": 0, "hash": "0" * 64}},
                cursor_path=cursor, cursor_anchor=Anchor())
            runtime = PhoneRuntime(state_dir=state, sync_context_id="peer-a",
                                   sync_spool_dir=spool, authenticated_sync_gate=gate)
            self.assertIs(runtime.sync_context.store, runtime.store)
            self.assertEqual(os.path.realpath(runtime.sync_context.store.dir), os.path.realpath(runtime.store.dir))
            self.assertTrue(runtime.store.verify()["ok"])

    def test_runtime_rejects_authenticated_cursor_inside_state_directory(self):
        from hg.sync_auth import AuthenticatedBatchGate
        class Keys:
            def get_peer_key(self, peer_id, key_id): return None
        class Anchor:
            def __init__(self): self.values = {}
            def read_anchor(self, peer_id): return dict(self.values[peer_id]) if peer_id in self.values else None
            def initialize_anchor(self, peer_id, checkpoint): self.values.setdefault(peer_id, dict(checkpoint))
            def advance_anchor(self, peer_id, expected, proposed):
                if self.values.get(peer_id) != expected: raise ValueError("anchor compare-and-advance conflict")
                if proposed["seq"] <= expected["seq"]: raise ValueError("anchor must advance")
                self.values[peer_id] = dict(proposed)
        with tempfile.TemporaryDirectory() as td:
            state = os.path.join(td, "state")
            cursor = os.path.join(state, "cursor.json")
            gate = AuthenticatedBatchGate(key_provider=Keys(),
                checkpoints={"peer-b": {"seq": 0, "hash": "0" * 64}},
                cursor_path=cursor, cursor_anchor=Anchor())
            with self.assertRaisesRegex(ValueError, "outside StateStore"):
                PhoneRuntime(state_dir=state, sync_context_id="peer-a",
                    sync_spool_dir=os.path.join(td, "spool"), authenticated_sync_gate=gate)

    def test_sync_reuses_runtime_store_and_two_runtime_contexts_exchange_envelopes(self):
        with tempfile.TemporaryDirectory() as td:
            a_dir = os.path.join(td, "a-state")
            b_dir = os.path.join(td, "b-state")
            spool = os.path.join(td, "spool")
            a = PhoneRuntime(state_dir=a_dir)
            b = PhoneRuntime(state_dir=b_dir)
            # Fail the test if SyncContext tries to construct a second store.
            with patch("hg.sync.StateStore", side_effect=AssertionError("second StateStore")):
                sa = SyncContext("runtime-a", a_dir, spool, store=a.store)
                sb = SyncContext("runtime-b", b_dir, spool, store=b.store)
            self.assertIs(sa.store, a.store)
            self.assertIs(sb.store, b.store)
            out = sa.publish("note.created", {"note": "isolated-runtime-a"})
            os.replace(os.path.join(spool, "outbox", out["file"]),
                       os.path.join(spool, "inbox", out["file"]))
            result = sb.import_batch(out["file"])
            self.assertEqual(len(result["accepted"]), 1)
            received = [r for r in b.store.replay() if r["event_type"] == "sync.received"]
            self.assertEqual(len(received), 1)
            self.assertEqual(received[0]["payload"]["payload"]["note"], "isolated-runtime-a")
            self.assertTrue(a.store.verify()["ok"])
            self.assertTrue(b.store.verify()["ok"])
            # The contract transports an envelope; it does not merge foreign
            # payloads into the receiver's application state.
            self.assertNotIn("isolated-runtime-a", repr(b.store._sessions))


if __name__ == "__main__":
    unittest.main()
