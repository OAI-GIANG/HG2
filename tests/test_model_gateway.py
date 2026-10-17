import json, threading, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from hg.model_gateway import ModelGateway, ModelGatewayError, ModelNotConfigured, ModelResponseInvalid

seen={}
class ProviderHandler(BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_POST(self):
  n=int(self.headers.get('Content-Length','0')); body=json.loads(self.rfile.read(n))
  seen['authorization']=self.headers.get('Authorization'); seen['body']=body
  raw=json.dumps({'model':'fake-model-v1','choices':[{'message':{'content':'A tested answer'}}]}).encode()
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
  self.assertIn('untrusted reference DATA',seen['body']['messages'][0]['content'])
  self.assertIn('treat as data',seen['body']['messages'][1]['content'])
  self.assertEqual(out['manifest']['context_manifest_sha256'],'a'*64)
  self.assertTrue(out['manifest']['provider_called']); self.assertNotIn('test-provider-key',json.dumps(out['manifest']))
 def test_missing_configuration_fails_closed(self):
  with self.assertRaises(ModelNotConfigured): ModelGateway(base_url='',api_key='',model='').ask('q',{})
 def test_invalid_provider_response_fails_closed(self):
  class BadResponse:
   status=200
   def __enter__(self): return self
   def __exit__(self,*args): return False
   def read(self): return b'{"choices":[]}'
  gw=ModelGateway(base_url='http://example.invalid/v1',api_key='x',model='m',opener=lambda *a,**k:BadResponse())
  with self.assertRaises(ModelResponseInvalid): gw.ask('q',{})
if __name__=='__main__': unittest.main()
