"""Isolated transactional authenticated sync tests; all credentials are ephemeral."""
import hashlib, json, os, shutil, tarfile, tempfile, unittest
from hg.history import StateStore, digest
from hg.sync import SyncContext, SyncError
from hg.sync_auth import AuthenticatedBatchGate, PeerAuthError, authenticate_batch

ZERO = "0" * 64
class EphemeralTestKeyProvider:
    def __init__(self, keys): self._keys = keys
    def get_peer_key(self, peer_id, key_id): return self._keys.get(peer_id, {}).get(key_id)


class TestMonotonicAnchor:
    def __init__(self): self.values={}
    def read_anchor(self, peer_id): return dict(self.values[peer_id]) if peer_id in self.values else None
    def initialize_anchor(self, peer_id, checkpoint):
        if peer_id in self.values and self.values[peer_id] != checkpoint: raise ValueError("anchor already initialized")
        self.values.setdefault(peer_id,dict(checkpoint))
    def advance_anchor(self, peer_id, expected, proposed):
        if self.values.get(peer_id) != expected: raise ValueError("anchor conflict")
        if proposed["seq"] <= expected["seq"]: raise ValueError("non-monotonic anchor")
        self.values[peer_id]=dict(proposed)

class Harness:
    def __init__(self, root):
        self.root=root; self.keys={"a":os.urandom(32), "b":os.urandom(32)}; self.anchors={}; self.checkpoints={}

        self.sa=StateStore(os.path.join(root,"state-a")); self.sb=StateStore(os.path.join(root,"state-b"))
        self.a=SyncContext("a",os.path.join(root,"state-a"),os.path.join(root,"spool-a"),store=self.sa)
        self.b=SyncContext("b",os.path.join(root,"state-b"),os.path.join(root,"spool-b"),store=self.sb)
    def batch(self, sender, receiver, origin):
        out=sender.publish("note.created",{"from":origin,"nonce":os.urandom(4).hex()})
        src=os.path.join(sender.spool,"outbox",out["file"])
        with open(src,"rb") as stream: raw=stream.read()
        batch=json.loads(raw)
        ev=batch["events"][0]
        authenticated=authenticate_batch(batch,peer_id=origin,key_id="k1",key_provider=EphemeralTestKeyProvider({origin:{"k1":self.keys[origin]}}))
        # The trust checkpoint is the known predecessor of the first exported event.
        anchor_key=receiver.context_id+"-"+origin
        anchor=self.anchors.setdefault(anchor_key,TestMonotonicAnchor())
        checkpoint=self.checkpoints.setdefault(anchor_key,{"seq":ev["origin_seq"]-1,"hash":ev["origin_prev_hash"]})
        gate=AuthenticatedBatchGate(key_provider=EphemeralTestKeyProvider({origin:{"k1":self.keys[origin]}}),
          checkpoints={origin:checkpoint},
          cursor_path=os.path.join(self.root,"cursor-"+receiver.context_id+"-"+origin,"cursor.json"),cursor_anchor=anchor)
        name=out["file"]
        with open(os.path.join(receiver.spool,"inbox",name),"wb") as f: f.write(json.dumps(authenticated,sort_keys=True,separators=(",",":")).encode())
        return name, authenticated, gate, raw
    def integrity(self):
        for store in (self.sa,self.sb):
            self.assert_store(store)
    @staticmethod
    def assert_store(store):
        assert store.verify()["ok"], store.verify()

class AuthenticatedTransactionTests(unittest.TestCase):
    def setUp(self): self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.h=Harness(self.tmp.name)
    def test_bidirectional_a_to_b_and_b_to_a(self):
        for sender,receiver,origin in ((self.h.a,self.h.b,"a"),(self.h.b,self.h.a,"b")):
            name,batch,gate,_=self.h.batch(sender,receiver,origin)
            result=receiver.import_authenticated_batch(name,gate)
            self.assertEqual(result["cursor"]["seq"],batch["events"][-1]["origin_seq"])
            self.h.integrity()
    def test_unknown_peer_rejected_without_state_mutation(self):
        name,batch,gate,_=self.h.batch(self.h.a,self.h.b,"a")
        bad=AuthenticatedBatchGate(key_provider=EphemeralTestKeyProvider({}),checkpoints={"a":{"seq":batch["events"][0]["origin_seq"]-1,"hash":batch["events"][0]["origin_prev_hash"]}},cursor_path=gate.cursor_path,cursor_anchor=self.h.anchors["b-a"])
        before=len(self.h.sb.replay())
        with self.assertRaisesRegex(PeerAuthError,"untrusted peer"): bad.verify(batch)
        self.assertEqual(len(self.h.sb.replay()),before); self.h.integrity()
    def test_tamper_gap_and_fork_rejected(self):
        for mode in ("tamper","gap","fork"):
            name,batch,gate,_=self.h.batch(self.h.a,self.h.b,"a")
            b=json.loads(json.dumps(batch))
            if mode=="tamper": b["events"][0]["payload"]["from"]="evil"
            if mode=="gap": b["events"][0]["origin_seq"]+=1
            if mode=="fork": b["events"][0]["origin_prev_hash"]="f"*64
            with self.subTest(mode=mode), self.assertRaises(PeerAuthError): gate.verify(b)
            self.h.integrity()
    def test_duplicate_delivery_after_commit_is_idempotent_success(self):
        name,batch,gate,_=self.h.batch(self.h.a,self.h.b,"a")
        self.h.b.import_authenticated_batch(name,gate)
        with open(os.path.join(self.h.b.spool,"inbox",name),"wb") as f: f.write(json.dumps(batch,sort_keys=True,separators=(",",":")).encode())
        before=len(self.h.sb.replay())
        result=self.h.b.import_authenticated_batch(name,gate)
        self.assertEqual(result["accepted"],[]); self.assertEqual(len(result["duplicates"]),1)
        self.assertEqual(len(self.h.sb.replay()),before); self.h.integrity()
    def test_restart_recovery_and_cursor_persistence(self):
        name,batch,gate,_=self.h.batch(self.h.a,self.h.b,"a")
        self.h.b.import_authenticated_batch(name,gate)
        restarted=AuthenticatedBatchGate(key_provider=EphemeralTestKeyProvider({"a":{"k1":self.h.keys["a"]}}),
          checkpoints={"a":{"seq":batch["events"][0]["origin_seq"]-1,"hash":batch["events"][0]["origin_prev_hash"]}},cursor_path=gate.cursor_path,cursor_anchor=self.h.anchors["b-a"])
        self.assertEqual(restarted._cursors["a"]["seq"],batch["events"][-1]["origin_seq"]); self.h.integrity()
    def test_crash_after_import_before_cursor_then_redelivery_recovers(self):
        name,batch,gate,_=self.h.batch(self.h.a,self.h.b,"a")
        original_commit=gate.commit
        def crash(_proposal): raise OSError("injected crash before cursor commit")
        gate.commit=crash
        with self.assertRaisesRegex(OSError,"injected crash"): self.h.b.import_authenticated_batch(name,gate)
        self.assertEqual(gate._cursors,{"a":self.h.checkpoints["b-a"]}); self.h.integrity()
        # Sender redelivery restages identical authenticated bytes after receiver crash.
        with open(os.path.join(self.h.b.spool,"inbox",name),"wb") as f: f.write(json.dumps(batch,sort_keys=True,separators=(",",":")).encode())
        gate.commit=original_commit
        result=self.h.b.import_authenticated_batch(name,gate)
        self.assertEqual(len(result["duplicates"]),1); self.assertEqual(len([r for r in self.h.sb.replay() if r["event_type"]=="sync.received"]),1)
        self.h.integrity()
    def test_crash_mid_batch_import_then_resume_idempotently(self):
        first=self.h.a.local_event("note.created",{"n":1})
        second=self.h.a.local_event("note.created",{"n":2})
        batch={"schema":"HG_SYNC_BATCH_V2","context_id":"a","created_at":1,"events":[first,second]}
        authenticated=authenticate_batch(batch,peer_id="a",key_id="k1",key_provider=EphemeralTestKeyProvider({"a":{"k1":self.h.keys["a"]}}))
        checkpoint={"seq":first["origin_seq"]-1,"hash":first["origin_prev_hash"]}
        cursor=os.path.join(self.tmp.name,"cursor-b-a","cursor.json")
        test_anchor=TestMonotonicAnchor()
        gate=AuthenticatedBatchGate(key_provider=EphemeralTestKeyProvider({"a":{"k1":self.h.keys["a"]}}),checkpoints={"a":checkpoint},cursor_path=cursor,cursor_anchor=test_anchor)
        name="two-event-crash.json"
        with open(os.path.join(self.h.b.spool,"inbox",name),"w") as f: json.dump(authenticated,f)
        emit=self.h.sb.emit; calls={"n":0}
        def fail_second(event_type,payload,**kwargs):
            if event_type=="sync.received":
                calls["n"]+=1
                if calls["n"]==2: raise OSError("injected crash mid import")
            return emit(event_type,payload,**kwargs)
        self.h.sb.emit=fail_second
        with self.assertRaisesRegex(OSError,"mid import"): self.h.b.import_authenticated_batch(name,gate)
        self.h.sb.emit=emit
        self.assertEqual(len([r for r in self.h.sb.replay() if r["event_type"]=="sync.received"]),1)
        self.assertEqual(gate._cursors,{"a":checkpoint})
        result=self.h.b.import_authenticated_batch(name,gate)
        self.assertEqual(result["duplicates"],[first["event_id"]]); self.assertEqual(result["accepted"],[second["event_id"]])
        self.assertEqual(len([r for r in self.h.sb.replay() if r["event_type"]=="sync.received"]),2)
        self.h.integrity()

    def test_phone_runtime_authenticated_bidirectional_end_to_end(self):
        from hg.phone_runtime import PhoneRuntime
        root=self.tmp.name
        a=PhoneRuntime(state_dir=os.path.join(root,"phone-a")); b=PhoneRuntime(state_dir=os.path.join(root,"phone-b"))
        keys={"a":os.urandom(32),"b":os.urandom(32)}
        provider=EphemeralTestKeyProvider({peer:{"k1":key} for peer,key in keys.items()})
        providers={"a":provider,"b":provider}
        phone_anchors={}
        def gate(receiver,peer,origin_store):
            genesis=origin_store.replay()[0]
            anchor=phone_anchors.setdefault(receiver+"-"+peer,TestMonotonicAnchor())
            return AuthenticatedBatchGate(key_provider=providers[receiver],
              checkpoints={peer:{"seq":genesis["seq"],"hash":genesis["record_hash"]}},
              cursor_path=os.path.join(root,"phone-cursors",receiver+"-"+peer+".json"),cursor_anchor=anchor)
        a.configure_authenticated_sync("a",os.path.join(root,"phone-a-spool"),gate("a","b",b.store))
        b.configure_authenticated_sync("b",os.path.join(root,"phone-b-spool"),gate("b","a",a.store))
        # Both peers publish before importing the other peer's envelope so the initial
        # trusted checkpoint matches each origin's uninterrupted local chain.
        out_a=a.publish_sync_event("note.created",{"origin":"a"})
        out_b=b.publish_sync_event("note.created",{"origin":"b"})
        def transfer(sender,receiver,origin,out):
            src=os.path.join(sender.sync_context.spool,"outbox",out["file"])
            with open(src,"r",encoding="utf-8") as f: batch=json.load(f)
            authenticated=authenticate_batch(batch,peer_id=origin,key_id="k1",key_provider=providers[origin])
            target=os.path.join(receiver.sync_context.spool,"inbox",out["file"])
            with open(target,"w",encoding="utf-8") as f: json.dump(authenticated,f,sort_keys=True,separators=(",",":"))
            return receiver.import_authenticated_batch(out["file"])
        self.assertEqual(transfer(a,b,"a",out_a)["accepted"], [next(r for r in a.store.replay() if r["event_type"]=="note.created")["event_id"]])
        self.assertEqual(transfer(b,a,"b",out_b)["accepted"], [next(r for r in b.store.replay() if r["event_type"]=="note.created")["event_id"]])
        self.assertIs(a.sync_context.store,a.store); self.assertIs(b.sync_context.store,b.store)
        self.assertTrue(a.health()["integrity"]["ok"]); self.assertTrue(b.health()["integrity"]["ok"])

    def test_rollback_archive_integrity_and_restore_fixture(self):
        archive=os.environ.get("HG2_ROLLBACK_ARCHIVE") or os.path.join(os.path.expanduser("~"),".cache/hg2-sync-closure-20261016/rollback/candidate-before-store-injection-207843bd.tar.gz")
        if not os.path.isfile(archive):
            self.skipTest("device-local rollback archive unavailable; provide HG2_ROLLBACK_ARCHIVE for live restore verification")
        with open(archive,"rb") as stream: archive_hash=hashlib.sha256(stream.read()).hexdigest()
        self.assertEqual(archive_hash,"36ef770bbad1678f94c48098132fa2110a0157708380ddaa503898fb58e364c3")
        # Exercise rollback restore in a fresh temporary directory; never overwrite candidate.
        restored=os.path.join(self.tmp.name,"rollback-restore")
        os.makedirs(restored)
        with tarfile.open(archive,"r:gz") as tf: tf.extractall(restored,filter="data")
        import subprocess
        head=subprocess.check_output(["git","-C",restored,"rev-parse","HEAD"],text=True).strip()
        self.assertEqual(head,"207843bd892c0d8543c8e8fec68e2cab9ed57781")
        expected={"hg/history.py":"8979e48f9d94c571d5e90691be16fc1b719a1cd8e4f51240f1a1ece254f92495",
                  "manifest.json":"56fec87dd5e4b4310e073021d8dfe2c295163813a98d6e09cb5d72c1d7765395",
                  "hg/sync.py":"cb57bc9e5cae5a7ce9f1b176538d686e7e0f809fb489e3d13db21574bc42e41d"}
        for rel,expected_hash in expected.items():
            with open(os.path.join(restored,rel),"rb") as stream: actual=hashlib.sha256(stream.read()).hexdigest()
            self.assertEqual(actual,expected_hash,rel)
        self.h.integrity()

if __name__=="__main__": unittest.main()
