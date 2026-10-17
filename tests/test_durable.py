import json, tempfile, unittest
from pathlib import Path
from urllib.error import HTTPError
from hg.history import StateStore
from hg.durable import DurableOutbox, DurableNotConfigured, DurableContractMismatch, DurableDeliveryError, CONTRACT

class Resp:
 def __init__(self, obj, status=200): self.raw=json.dumps(obj).encode(); self.status=status
 def __enter__(self): return self
 def __exit__(self,*a): return False
 def read(self): return self.raw

class FakeProvider:
 def __init__(self, caps=None, receipt=None): self.caps=caps; self.receipt=receipt; self.calls=[]
 def __call__(self,req,timeout=0):
  self.calls.append((req.full_url,req.get_method(),req.headers,req.data))
  if req.full_url.endswith('/backend/hg2/capabilities'):
   if self.caps is None: raise HTTPError(req.full_url,404,'not found',{},None)
   return Resp(self.caps)
  body=json.loads(req.data)
  return Resp(self.receipt(body) if callable(self.receipt) else (self.receipt or {}))

class DurableTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
  self.store=StateStore(self.tmp.name); self.store.emit('memory.mutated',{'record':{'id':'m1','content':'secret user memory'},'idempotency_key':'k'},event_id='memory:test-1')
 def test_missing_config_fails_closed(self):
  d=DurableOutbox(self.store,base_url='',token='')
  self.assertEqual(d.status()['pending_count'],1)
  with self.assertRaises(DurableNotConfigured): d.deliver_once()
 def test_legacy_backend_contract_mismatch_never_posts(self):
  f=FakeProvider(); d=DurableOutbox(self.store,base_url='http://127.0.0.1:9099',token='least-scope-test-token',opener=f)
  with self.assertRaises(DurableContractMismatch): d.deliver_once()
  self.assertEqual(len(f.calls),1); self.assertTrue(f.calls[0][0].endswith('/backend/hg2/capabilities'))
 def test_successful_delivery_is_acknowledged_idempotently(self):
  def receipt(body): return {'ok':True,'contract':CONTRACT,'batch_id':body['batch_id'],'accepted_count':len(body['events'])}
  f=FakeProvider({'contract':CONTRACT,'memory_schema':'HG_MEMORY_V1','supports_tombstones':True,'supports_scopes':True,'required_scope':'MEMORY_PERSIST'},receipt)
  d=DurableOutbox(self.store,base_url='https://durable.test',token='least-scope-test-token',opener=f)
  out=d.deliver_once(); self.assertEqual(out['status'],'ACKNOWLEDGED')
  self.assertEqual(d.status()['pending_count'],0); self.assertEqual(d.status()['acknowledged_count'],1)
  self.assertEqual(d.deliver_once()['status'],'EMPTY')
  self.assertEqual(sum(1 for x in f.calls if x[1]=='POST'),1)
  sent=json.loads(next(x[3] for x in f.calls if x[1]=='POST'))
  self.assertEqual(sent['contract'],CONTRACT); self.assertEqual(sent['events'][0]['event']['payload']['record']['content'],'secret user memory')
 def test_receipt_mismatch_does_not_acknowledge(self):
  f=FakeProvider({'contract':CONTRACT,'memory_schema':'HG_MEMORY_V1','supports_tombstones':True,'supports_scopes':True,'required_scope':'MEMORY_PERSIST'},{'ok':True,'contract':CONTRACT,'batch_id':'wrong','accepted_count':1})
  d=DurableOutbox(self.store,base_url='https://durable.test',token='least-scope-test-token',opener=f)
  with self.assertRaises(DurableDeliveryError): d.deliver_once()
  self.assertEqual(d.status()['pending_count'],1)
 def test_non_loopback_cleartext_is_rejected_before_network(self):
  f=FakeProvider({'contract':CONTRACT,'memory_schema':'HG_MEMORY_V1','supports_tombstones':True,'supports_scopes':True,'required_scope':'MEMORY_PERSIST'},{})
  d=DurableOutbox(self.store,base_url='http://durable.example',token='least-scope-test-token',opener=f)
  with self.assertRaises(DurableDeliveryError): d.deliver_once()
  self.assertEqual(f.calls,[])

if __name__=='__main__': unittest.main()
