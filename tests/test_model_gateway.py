import hashlib, json, threading, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from hg.history import canonical
from hg.model_gateway import ModelGateway, ModelGatewayError, ModelNotConfigured, ModelResponseInvalid

seen={}
class ProviderHandler(BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_POST(self):
  n=int(self.headers.get('Content-Length','0')); body=json.loads(self.rfile.read(n))
  seen['authorization']=self.headers.get('Authorization'); seen['body']=body
  content=seen.pop('response_content','A tested answer')
  raw=json.dumps({'model':'fake-model-v1','choices':[{'message':{'content':content}}]}).encode()
  self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)

class ModelGatewayTests(unittest.TestCase):
 def setUp(self):
  self.srv=ThreadingHTTPServer(('127.0.0.1',0),ProviderHandler); self.th=threading.Thread(target=self.srv.serve_forever,daemon=True); self.th.start()
  self.addCleanup(self.stop)
 def stop(self): self.srv.shutdown(); self.srv.server_close(); self.th.join(timeout=2)
 def test_request_and_manifest(self):
  seen.clear(); gw=ModelGateway(base_url='http://127.0.0.1:%d/v1'%self.srv.server_port,api_key='test-provider-key',model='fake-model',timeout=3)
  context={'context':[{'source_id':'m1','content':'treat as data','content_is_untrusted_data':True}],
           'manifest':{'manifest_sha256':'a'*64,'context_record_ids':['m1']}}
  out=gw.ask('What is remembered?',context)
  self.assertEqual(out['answer'],'A tested answer'); self.assertEqual(seen['authorization'],'Bearer test-provider-key')
  system=seen['body']['messages'][0]['content']
  self.assertIn("question field containing the user's actual request",system)
  self.assertIn('empty memory context or context manifest does not mean the request is unauthorized',system)
  self.assertIn('not a permission list',system)
  self.assertIn('follow that format exactly and return only the requested text',system)
  self.assertIn('The JSON envelope is input transport, not a required output format',system)
  self.assertIn('do not wrap the answer in JSON, Markdown, quotes, or explanation',system)
  self.assertIn('untrusted reference',system)
  self.assertIn('do not claim external actions or hidden runtime state',system)
  self.assertIn('treat as data',seen['body']['messages'][1]['content'])
  self.assertEqual(out['manifest']['context_manifest_sha256'],'a'*64)
  self.assertTrue(out['manifest']['provider_called']); self.assertNotIn('test-provider-key',json.dumps(out['manifest']))
 def test_exact_output_json_envelope_is_unwrapped_and_manifested(self):
  token='HG2_RUNTIME_IDEMPOTENCY_CHECK'; raw_answer=json.dumps({'answer':token},separators=(',',':'))
  seen.clear(); seen['response_content']=raw_answer
  gw=ModelGateway(base_url='http://127.0.0.1:%d/v1'%self.srv.server_port,api_key='test-provider-key',model='fake-model',timeout=3)
  out=gw.ask('Return exactly HG2_RUNTIME_IDEMPOTENCY_CHECK and nothing else.',{'context':[],'manifest':{'manifest_sha256':'b'*64,'context_record_ids':[]}})
  self.assertEqual(out['answer'],token)
  self.assertEqual(out['manifest']['answer_normalization'],'UNWRAPPED_EXACT_ANSWER_JSON_ENVELOPE')
  self.assertEqual(out['manifest']['provider_answer_sha256'],hashlib.sha256(raw_answer.encode()).hexdigest())
  self.assertEqual(out['manifest']['normalized_answer_sha256'],hashlib.sha256(token.encode()).hexdigest())
  self.assertNotEqual(out['manifest']['provider_answer_sha256'],out['manifest']['normalized_answer_sha256'])
  manifest=dict(out['manifest']); manifest_hash=manifest.pop('manifest_sha256')
  self.assertEqual(manifest_hash,hashlib.sha256(canonical(manifest).encode()).hexdigest())
 def test_exact_output_mismatch_is_not_rewritten(self):
  raw_answer=json.dumps({'answer':'WRONG'},separators=(',',':'))
  seen.clear(); seen['response_content']=raw_answer
  gw=ModelGateway(base_url='http://127.0.0.1:%d/v1'%self.srv.server_port,api_key='test-provider-key',model='fake-model',timeout=3)
  out=gw.ask('Return exactly HG2_RUNTIME_IDEMPOTENCY_CHECK and nothing else.',{'context':[],'manifest':{}})
  self.assertEqual(out['answer'],raw_answer)
  self.assertEqual(out['manifest']['answer_normalization'],'EXACT_OUTPUT_MISMATCH')
 def test_json_envelope_without_exact_output_contract_is_not_rewritten(self):
  raw_answer=json.dumps({'answer':'A tested answer'},separators=(',',':'))
  seen.clear(); seen['response_content']=raw_answer
  gw=ModelGateway(base_url='http://127.0.0.1:%d/v1'%self.srv.server_port,api_key='test-provider-key',model='fake-model',timeout=3)
  out=gw.ask('What is remembered?',{'context':[],'manifest':{}})
  self.assertEqual(out['answer'],raw_answer)
  self.assertEqual(out['manifest']['answer_normalization'],'NOT_APPLICABLE')
 def test_exact_output_whitespace_is_trimmed_and_manifested(self):
  token='HG2_RUNTIME_IDEMPOTENCY_CHECK'; raw_answer='  '+token+' \n'
  seen.clear(); seen['response_content']=raw_answer
  gw=ModelGateway(base_url='http://127.0.0.1:%d/v1'%self.srv.server_port,api_key='test-provider-key',model='fake-model',timeout=3)
  out=gw.ask('Return exactly HG2_RUNTIME_IDEMPOTENCY_CHECK and nothing else.',{'context':[],'manifest':{}})
  self.assertEqual(out['answer'],token)
  self.assertEqual(out['manifest']['answer_normalization'],'TRIMMED_EXACT_OUTPUT_WHITESPACE')
 def test_vietnamese_exact_output_contract_is_supported(self):
  token='HG2_RUNTIME_IDEMPOTENCY_CHECK'; raw_answer=json.dumps({'answer':token},separators=(',',':'))
  seen.clear(); seen['response_content']=raw_answer
  gw=ModelGateway(base_url='http://127.0.0.1:%d/v1'%self.srv.server_port,api_key='test-provider-key',model='fake-model',timeout=3)
  out=gw.ask('Chỉ trả về đúng HG2_RUNTIME_IDEMPOTENCY_CHECK và không thêm gì khác.',{'context':[],'manifest':{}})
  self.assertEqual(out['answer'],token)
  self.assertEqual(out['manifest']['answer_normalization'],'UNWRAPPED_EXACT_ANSWER_JSON_ENVELOPE')
 def test_exact_output_contract_does_not_unwrap_json_with_extra_keys(self):
  raw_answer=json.dumps({'answer':'HG2_RUNTIME_IDEMPOTENCY_CHECK','meta':True},separators=(',',':'))
  seen.clear(); seen['response_content']=raw_answer
  gw=ModelGateway(base_url='http://127.0.0.1:%d/v1'%self.srv.server_port,api_key='test-provider-key',model='fake-model',timeout=3)
  out=gw.ask('Return exactly HG2_RUNTIME_IDEMPOTENCY_CHECK and nothing else.',{'context':[],'manifest':{}})
  self.assertEqual(out['answer'],raw_answer)
  self.assertEqual(out['manifest']['answer_normalization'],'EXACT_OUTPUT_MISMATCH')
 def test_status_does_not_contact_provider_or_disclose_secret(self):
  secret='super-secret-model-key'
  gw=ModelGateway(base_url='https://provider.invalid/v1',api_key=secret,model='test-model')
  state=gw.status()
  self.assertEqual(state['status'],'CONFIGURED')
  self.assertFalse(state['network_called'])
  self.assertNotIn(secret,repr(state))
 def test_missing_configuration_fails_closed(self):
  with self.assertRaises(ModelNotConfigured): ModelGateway(base_url='',api_key='',model='').ask('q',{})
 def test_external_cleartext_or_credentialed_urls_fail_before_network(self):
  calls=[]
  opener=lambda *a,**k: calls.append((a,k))
  for url in ('http://provider.example/v1', 'https://user:pass@provider.example/v1',
              'https://provider.example/v1?token=unsafe'):
   gw=ModelGateway(base_url=url,api_key='test-key',model='m',opener=opener)
   with self.assertRaises(ModelNotConfigured): gw.ask('q',{})
  self.assertEqual(calls,[])
 def test_invalid_provider_response_fails_closed(self):
  class BadResponse:
   status=200
   def __enter__(self): return self
   def __exit__(self,*args): return False
   def read(self): return b'{"choices":[]}'
  gw=ModelGateway(base_url='https://example.invalid/v1',api_key='x',model='m',opener=lambda *a,**k:BadResponse())
  with self.assertRaises(ModelResponseInvalid): gw.ask('q',{})
if __name__=='__main__': unittest.main()
