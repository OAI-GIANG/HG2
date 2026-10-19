"""Isolated prototype integration: SyncContext reuses PhoneRuntime's one store."""
import os
import tempfile
import unittest
from unittest.mock import patch

from hg.phone_runtime import PhoneRuntime
from hg.sync import SyncContext


class PhoneRuntimeSyncIntegrationTests(unittest.TestCase):
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
