import os, tempfile, unittest
from hg.history import StateStore, digest
from hg.sync_auth import AuthenticatedBatchGate, PeerAuthError, sign_batch

KEY = os.urandom(32)  # ephemeral test credential; never persisted
ZERO = "0" * 64
class EphemeralTestKeyProvider:
    def __init__(self, keys): self._keys = keys
    def get_peer_key(self, peer_id, key_id): return self._keys.get(peer_id, {}).get(key_id)

def make_batch(origin="peer-a"):
    with tempfile.TemporaryDirectory() as td:
        s = StateStore(os.path.join(td, "state"))
        rec = s.emit("note.created", {"note": "hello"})
        ev = {"event_id": rec["event_id"], "event_type": rec["event_type"],
              "payload": rec["payload"], "payload_hash": digest(rec["payload"]),
              "origin_context": origin, "origin_seq": rec["seq"],
              "origin_prev_hash": rec["prev_hash"], "origin_hash": rec["record_hash"],
              "origin_record": rec}
        return {"schema": "HG_SYNC_BATCH_V2", "context_id": origin, "created_at": 1, "events": [ev]}


class TestMonotonicAnchor:
    """Test double only; persistent object simulates an independent anchor service."""
    def __init__(self): self.values={}
    def read_anchor(self, peer_id): return dict(self.values[peer_id]) if peer_id in self.values else None
    def initialize_anchor(self, peer_id, checkpoint):
        if peer_id in self.values and self.values[peer_id] != checkpoint: raise PeerAuthError("anchor already initialized")
        self.values.setdefault(peer_id,dict(checkpoint))
    def advance_anchor(self, peer_id, expected, proposed):
        if self.values.get(peer_id) != expected: raise PeerAuthError("anchor compare-and-advance conflict")
        if proposed["seq"] <= expected["seq"]: raise PeerAuthError("anchor must advance monotonically")
        self.values[peer_id]=dict(proposed)

class AuthGateTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory(); self.addCleanup(self.td.cleanup)
        self.cursor = os.path.join(self.td.name, "trust", "cursor.json")
        self.batch = make_batch()
        ev = self.batch["events"][0]
        self.checkpoint = {"seq": ev["origin_seq"] - 1, "hash": ev["origin_prev_hash"]}
        self.anchor = TestMonotonicAnchor()
        self.gate = AuthenticatedBatchGate(key_provider=EphemeralTestKeyProvider({"peer-a":{"k1":KEY}}),
            checkpoints={"peer-a":self.checkpoint}, cursor_path=self.cursor, cursor_anchor=self.anchor)
    def signed(self):
        return sign_batch(self.batch, peer_id="peer-a", key_id="k1", key_provider=EphemeralTestKeyProvider({"peer-a":{"k1":KEY}}))
    def test_valid_signature_and_checkpoint_chain(self):
        p=self.gate.verify(self.signed()); self.assertEqual(p["seq"],self.batch["events"][0]["origin_seq"]); self.gate.commit(p)
        restarted=AuthenticatedBatchGate(key_provider=EphemeralTestKeyProvider({"peer-a":{"k1":KEY}}),
            checkpoints={"peer-a":self.checkpoint},cursor_path=self.cursor,cursor_anchor=self.anchor)
        self.assertEqual(restarted._cursors["peer-a"]["seq"],self.batch["events"][0]["origin_seq"])
    def test_unknown_peer_rejected(self):
        with self.assertRaisesRegex(PeerAuthError,"untrusted peer"):
            self.gate.verify(sign_batch(make_batch(),peer_id="stranger",key_id="k1",key_provider=EphemeralTestKeyProvider({"stranger":{"k1":KEY}})))
    def test_tamper_rejected(self):
        b=self.signed(); b["events"][0]["payload"]["note"]="tampered"
        with self.assertRaisesRegex(PeerAuthError,"authentication failed"): self.gate.verify(b)
    def test_replay_rejected_after_commit(self):
        b=self.signed(); self.gate.commit(self.gate.verify(b))
        proposal=self.gate.verify(b)
        self.assertTrue(proposal["duplicate"])
    def test_fork_rejected(self):
        b=make_batch(); b["events"][0]["origin_prev_hash"]="1"*64
        b=sign_batch(b,peer_id="peer-a",key_id="k1",key_provider=EphemeralTestKeyProvider({"peer-a":{"k1":KEY}}))
        with self.assertRaisesRegex(PeerAuthError,"origin fork"): self.gate.verify(b)
    def test_gap_rejected(self):
        b=make_batch(); b["events"][0]["origin_seq"] += 1
        b=sign_batch(b,peer_id="peer-a",key_id="k1",key_provider=EphemeralTestKeyProvider({"peer-a":{"k1":KEY}}))
        with self.assertRaisesRegex(PeerAuthError,"sequence gap"): self.gate.verify(b)
    def test_missing_checkpoint_rejected(self):
        gate=AuthenticatedBatchGate(key_provider=EphemeralTestKeyProvider({"peer-a":{"k1":KEY}}),checkpoints={},cursor_path=os.path.join(self.td.name,"empty-checkpoint.json"),cursor_anchor=TestMonotonicAnchor())
        with self.assertRaisesRegex(PeerAuthError,"no trusted origin checkpoint"): gate.verify(self.signed())
    def test_short_key_rejected(self):
        with self.assertRaisesRegex(PeerAuthError,"256 bits"): sign_batch(make_batch(),peer_id="peer-a",key_id="k1",key_provider=EphemeralTestKeyProvider({"peer-a":{"k1":b"short"}}))
    def test_cursor_restart_rejects_replay(self):
        b=self.signed(); self.gate.commit(self.gate.verify(b))
        restarted=AuthenticatedBatchGate(key_provider=EphemeralTestKeyProvider({"peer-a":{"k1":KEY}}),
            checkpoints={"peer-a":self.checkpoint},cursor_path=self.cursor,cursor_anchor=self.anchor)
        self.assertTrue(restarted.verify(b)["duplicate"])
    def test_equal_sequence_cursor_with_wrong_hash_rejected(self):
        os.makedirs(os.path.dirname(self.cursor), exist_ok=True)
        with open(self.cursor, "w", encoding="utf-8") as f:
            import json
            json.dump({"peer-a":{"seq":self.checkpoint["seq"],"hash":"f"*64}},f)
        with self.assertRaisesRegex(PeerAuthError,"cursor hash differs from independent monotonic anchor"):
            AuthenticatedBatchGate(key_provider=EphemeralTestKeyProvider({"peer-a":{"k1":KEY}}),
                checkpoints={"peer-a":self.checkpoint},cursor_path=self.cursor,cursor_anchor=self.anchor)
    def test_corrupt_cursor_fails_closed(self):
        os.makedirs(os.path.dirname(self.cursor), exist_ok=True)
        with open(self.cursor, "w", encoding="utf-8") as f: f.write('{"peer-a":')
        with self.assertRaisesRegex(PeerAuthError,"cursor file corrupt or unreadable"):
            AuthenticatedBatchGate(key_provider=EphemeralTestKeyProvider({"peer-a":{"k1":KEY}}),
                checkpoints={"peer-a":self.checkpoint},cursor_path=self.cursor,cursor_anchor=self.anchor)
    def test_cursor_rollback_below_checkpoint_rejected(self):
        # Model a cursor file restored to a sequence older than the trusted checkpoint.
        import json
        os.makedirs(os.path.dirname(self.cursor), exist_ok=True)
        anchor={"seq":5,"hash":"a"*64}
        with open(self.cursor, "w", encoding="utf-8") as f:
            json.dump({"peer-a":{"seq":4,"hash":"b"*64}},f)
        with self.assertRaisesRegex(PeerAuthError,"cursor is not anchored to trusted peer checkpoint"):
            AuthenticatedBatchGate(key_provider=EphemeralTestKeyProvider({"peer-a":{"k1":KEY}}),
                checkpoints={"peer-a":anchor},cursor_path=self.cursor,cursor_anchor=self.anchor)
    def test_checkpoint_sequence_cursor_with_matching_hash_is_accepted(self):
        import json
        os.makedirs(os.path.dirname(self.cursor), exist_ok=True)
        with open(self.cursor, "w", encoding="utf-8") as f:
            json.dump({"peer-a":dict(self.checkpoint)},f)
        gate=AuthenticatedBatchGate(key_provider=EphemeralTestKeyProvider({"peer-a":{"k1":KEY}}),
            checkpoints={"peer-a":self.checkpoint},cursor_path=self.cursor,cursor_anchor=self.anchor)
        self.assertEqual(gate._cursors["peer-a"],self.checkpoint)
    def test_rollback_to_older_valid_cursor_is_detected_and_repaired_from_anchor(self):
        proposal=self.gate.verify(self.signed()); self.gate.commit(proposal)
        committed=dict(self.gate._cursors["peer-a"])
        # Restore the old, internally valid checkpoint cursor while independent anchor stays advanced.
        with open(self.cursor, "w", encoding="utf-8") as f:
            import json
            json.dump({"peer-a":dict(self.checkpoint)},f)
        restarted=AuthenticatedBatchGate(key_provider=EphemeralTestKeyProvider({"peer-a":{"k1":KEY}}),
            checkpoints={"peer-a":self.checkpoint},cursor_path=self.cursor,cursor_anchor=self.anchor)
        self.assertTrue(restarted.cursor_recovered_from_anchor)
        self.assertEqual(restarted._cursors["peer-a"],committed)
    def test_crash_after_anchor_advance_before_cursor_write_recovers_on_restart(self):
        proposal=self.gate.verify(self.signed())
        original_persist=self.gate._persist
        self.gate._persist=lambda _data: (_ for _ in ()).throw(OSError("injected cursor write failure"))
        with self.assertRaisesRegex(OSError,"cursor write failure"):
            self.gate.commit(proposal)
        self.gate._persist=original_persist
        restarted=AuthenticatedBatchGate(key_provider=EphemeralTestKeyProvider({"peer-a":{"k1":KEY}}),
            checkpoints={"peer-a":self.checkpoint},cursor_path=self.cursor,cursor_anchor=self.anchor)
        self.assertTrue(restarted.cursor_recovered_from_anchor)
        self.assertEqual(restarted._cursors["peer-a"]["seq"],proposal["seq"])

if __name__ == "__main__": unittest.main()
