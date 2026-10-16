"""Isolated bootstrap contract tests; all test key material is ephemeral in memory."""
import importlib, json, os, secrets, tempfile, unittest
from pathlib import Path

from hg.history import StateStore
from hg.phone_runtime import PhoneRuntime
from hg.sync_auth import KeyManagementInterface, PeerAuthError, sign_batch
from hg.sync_bootstrap import create_authenticated_runtime

ZERO='0'*64

class TestMonotonicAnchor:
    def __init__(self): self.values={}
    def read_anchor(self, peer_id): return dict(self.values[peer_id]) if peer_id in self.values else None
    def initialize_anchor(self, peer_id, checkpoint): self.values.setdefault(peer_id,dict(checkpoint))
    def advance_anchor(self, peer_id, expected, proposed):
        if self.values.get(peer_id) != expected: raise ValueError("anchor compare-and-advance conflict")
        if proposed["seq"] <= expected["seq"]: raise ValueError("anchor must advance")
        self.values[peer_id]=dict(proposed)

class EphemeralProvider(KeyManagementInterface):
    def __init__(self, keys): self.keys=keys; self.calls=[]
    def get_peer_key(self, peer_id, key_id):
        self.calls.append((peer_id,key_id))
        return self.keys.get((peer_id,key_id))

def peer_config(context_id, peer_id, key_id, checkpoint):
    return {'context_id':context_id,'trusted_peers':[{'peer_id':peer_id,'key_id':key_id,'checkpoint':checkpoint}]}

def signed_transfer(sender, receiver, origin, key_id, key, provider, name):
    published=sender.publish_sync_event('bootstrap.probe', {'from':origin,'nonce':secrets.token_hex(8)})
    src=Path(sender.sync_context.spool)/'outbox'/published['file']
    batch=json.loads(src.read_text())
    signed=sign_batch(batch,peer_id=origin,key_id=key_id,key_provider=provider)
    inbox=Path(receiver.sync_context.spool)/'inbox'/name
    inbox.write_text(json.dumps(signed,separators=(',',':')))
    return receiver.import_authenticated_batch(name)

class BootstrapTests(unittest.TestCase):
    def test_manifest_declares_auth_and_bootstrap_modules(self):
        manifest=json.loads((Path(__file__).resolve().parents[1]/'manifest.json').read_text())
        self.assertIn('hg.sync_auth',manifest['modules'])
        self.assertIn('hg.sync_bootstrap',manifest['modules'])
        self.assertNotIn('hg.sync_auth',manifest.get('optional_modules',[]))
        for module in ('hg.sync_auth','hg.sync_bootstrap'):
            with self.subTest(module=module): self.assertIsNotNone(importlib.import_module(module))

    def test_fail_closed_for_missing_trust_or_key_provider(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'trusted_peers'):
                create_authenticated_runtime(state_dir=d+'/state',spool_dir=d+'/spool',cursor_path=d+'/cursor/c.json',config={'context_id':'a','trusted_peers':[]},key_provider=EphemeralProvider({}),cursor_anchor=TestMonotonicAnchor())
            with self.assertRaisesRegex(PeerAuthError,'KeyManagementInterface'):
                create_authenticated_runtime(state_dir=d+'/state2',spool_dir=d+'/spool2',cursor_path=d+'/cursor2/c.json',config=peer_config('a','b','k',{'seq':0,'hash':ZERO}),key_provider=object(),cursor_anchor=TestMonotonicAnchor())
            with self.assertRaisesRegex(ValueError,'outside StateStore'):
                create_authenticated_runtime(state_dir=d+'/state3',spool_dir=d+'/spool3',cursor_path=d+'/state3/cursor.json',config=peer_config('a','b','k',{'seq':0,'hash':ZERO}),key_provider=EphemeralProvider({}),cursor_anchor=TestMonotonicAnchor())

    def test_bootstrap_creates_new_runtime_with_gate_and_single_store(self):
        with tempfile.TemporaryDirectory() as d:
            provider=EphemeralProvider({('peer-b','kb'):secrets.token_bytes(32)}); anchor=TestMonotonicAnchor()
            rt=create_authenticated_runtime(state_dir=d+'/state-a',spool_dir=d+'/spool-a',cursor_path=d+'/cursor-a/c.json',config=peer_config('peer-a','peer-b','kb',{'seq':0,'hash':ZERO}),key_provider=provider,cursor_anchor=anchor)
            self.assertIsInstance(rt,PhoneRuntime)
            self.assertIsNotNone(rt.sync_context)
            self.assertIs(rt.sync_context.store,rt.store)
            self.assertIs(rt.authenticated_sync_gate.key_provider._delegate,provider)
            self.assertIsNone(rt.authenticated_sync_gate.key_provider.get_peer_key('peer-b','wrong-key-id'))
            self.assertTrue(rt.store.verify()['ok'])

    def test_bootstrapped_runtime_bidirectional_authenticated_sync_and_integrity(self):
        with tempfile.TemporaryDirectory() as d:
            ka,kb=secrets.token_bytes(32),secrets.token_bytes(32)
            # Seed each origin store first; checkpoint the receiver trusts is its known head.
            seed_a=PhoneRuntime(state_dir=d+'/state-a'); seed_b=PhoneRuntime(state_dir=d+'/state-b')
            ha=seed_a.store.replay()[-1]; hb=seed_b.store.replay()[-1]
            cpa={'seq':ha['seq'],'hash':ha['record_hash']}; cpb={'seq':hb['seq'],'hash':hb['record_hash']}
            aa,ab=TestMonotonicAnchor(),TestMonotonicAnchor()
            pa=EphemeralProvider({('b','kb'):kb,('a','ka'):ka})
            pb=EphemeralProvider({('a','ka'):ka,('b','kb'):kb})
            a=create_authenticated_runtime(state_dir=d+'/state-a',spool_dir=d+'/spool-a',cursor_path=d+'/cursor-a/c.json',config=peer_config('a','b','kb',cpb),key_provider=pa,cursor_anchor=aa)
            b=create_authenticated_runtime(state_dir=d+'/state-b',spool_dir=d+'/spool-b',cursor_path=d+'/cursor-b/c.json',config=peer_config('b','a','ka',cpa),key_provider=pb,cursor_anchor=ab)
            out_a=a.publish_sync_event('bootstrap.probe',{'origin':'a'})
            out_b=b.publish_sync_event('bootstrap.probe',{'origin':'b'})
            def stage(sender,receiver,out,origin,keyid,key,provider,name):
                batch=json.loads((Path(sender.sync_context.spool)/'outbox'/out['file']).read_text())
                signed=sign_batch(batch,peer_id=origin,key_id=keyid,key_provider=provider)
                (Path(receiver.sync_context.spool)/'inbox'/name).write_text(json.dumps(signed,separators=(',',':')))
                return receiver.import_authenticated_batch(name)
            rb=stage(a,b,out_a,'a','ka',ka,pa,'a-to-b.json')
            ra=stage(b,a,out_b,'b','kb',kb,pb,'b-to-a.json')
            self.assertEqual(len(rb['accepted']),1); self.assertEqual(len(ra['accepted']),1)
            self.assertIs(a.sync_context.store,a.store); self.assertIs(b.sync_context.store,b.store)
            self.assertTrue(a.store.verify()['ok']); self.assertTrue(b.store.verify()['ok'])
            self.assertIn(('a','ka'),pa.calls); self.assertIn(('b','kb'),pa.calls)
            self.assertIn(('b','kb'),pb.calls); self.assertIn(('a','ka'),pb.calls)

    def test_crash_before_cursor_commit_recovers_after_restart(self):
        with tempfile.TemporaryDirectory() as d:
            key=secrets.token_bytes(32); provider=EphemeralProvider({('a','ka'):key})
            sender_seed=PhoneRuntime(state_dir=d+'/sender')
            receiver_seed=PhoneRuntime(state_dir=d+'/receiver')
            sender_head=sender_seed.store.replay()[-1]; receiver_head=receiver_seed.store.replay()[-1]
            config=peer_config('b','a','ka',{'seq':sender_head['seq'],'hash':sender_head['record_hash']})
            sender_gate_provider=EphemeralProvider({('b','kb'):secrets.token_bytes(32)})
            sender=PhoneRuntime(state_dir=d+'/sender',sync_context_id='a',sync_spool_dir=d+'/sender-spool',authenticated_sync_gate=__import__('hg.sync_auth',fromlist=['AuthenticatedBatchGate']).AuthenticatedBatchGate(key_provider=sender_gate_provider,checkpoints={'b':{'seq':receiver_head['seq'],'hash':receiver_head['record_hash']}},cursor_path=d+'/sender-cursor/c.json',cursor_anchor=TestMonotonicAnchor()))
            anchor=TestMonotonicAnchor()
            receiver=create_authenticated_runtime(state_dir=d+'/receiver',spool_dir=d+'/receiver-spool',cursor_path=d+'/receiver-cursor/c.json',config=config,key_provider=provider,cursor_anchor=anchor)
            out=sender.publish_sync_event('bootstrap.crash',{'n':1})
            batch=json.loads((Path(sender.sync_context.spool)/'outbox'/out['file']).read_text())
            signed=sign_batch(batch,peer_id='a',key_id='ka',key_provider=EphemeralProvider({('a','ka'):key}))
            name='crash.json'; (Path(receiver.sync_context.spool)/'inbox'/name).write_text(json.dumps(signed,separators=(',',':')))
            gate=receiver.authenticated_sync_gate; original=gate.commit
            def crash(_): raise OSError('injected crash before cursor commit')
            gate.commit=crash
            with self.assertRaisesRegex(OSError,'injected crash'):
                receiver.import_authenticated_batch(name)
            self.assertEqual(gate._cursors,{'a': {'seq': sender_head['seq'], 'hash': sender_head['record_hash']}})
            self.assertTrue(receiver.store.verify()['ok'])
            # Re-create runtime against same isolated store/cursor; re-delivery is idempotent.
            receiver2=create_authenticated_runtime(state_dir=d+'/receiver',spool_dir=d+'/receiver-spool',cursor_path=d+'/receiver-cursor/c.json',config=config,key_provider=provider,cursor_anchor=anchor)
            (Path(receiver2.sync_context.spool)/'inbox'/name).write_text(json.dumps(signed,separators=(',',':')))
            result=receiver2.import_authenticated_batch(name)
            self.assertEqual(len(result['duplicates']),1)
            self.assertEqual(len([r for r in receiver2.store.replay() if r['event_type']=='sync.received']),1)
            self.assertTrue(sender.store.verify()['ok']); self.assertTrue(receiver2.store.verify()['ok'])

if __name__=='__main__': unittest.main(verbosity=2)
