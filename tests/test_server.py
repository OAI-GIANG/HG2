import json, os, tempfile, threading, unittest, urllib.error, urllib.request
from unittest.mock import patch
from http.client import HTTPConnection
from hg.history import StateStore
from hg.phone_runtime import PhoneRuntime
from hg.server import HGHTTPServer

TOKEN = "test-hg-api-token"

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {"HG_API_TOKEN": TOKEN, "HG_API_PRINCIPAL_ID":"test-owner",
            "HG_MEMORY_READ_SCOPES":"owner", "HG_MEMORY_WRITE_SCOPES":"owner"}, clear=False)
        self.env.start(); self.addCleanup(self.env.stop)
        self.rt = PhoneRuntime(state_dir=self.tmp.name)
        self.srv = HGHTTPServer(("127.0.0.1", 0), runtime=self.rt)
        self.th = threading.Thread(target=self.srv.serve_forever, daemon=True); self.th.start()
        self.addCleanup(self.stop)
        self.base = "http://127.0.0.1:%d" % self.srv.server_port
    def stop(self):
        self.srv.shutdown(); self.srv.server_close(); self.th.join(timeout=2)
    def call(self, path, method="GET", obj=None, token=TOKEN, raw=None):
        data = raw if raw is not None else (None if obj is None else json.dumps(obj).encode())
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if token: req.add_header("Authorization", "Bearer " + token)
        if data is not None: req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=3) as resp: return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
    def test_health_and_auth(self):
        with urllib.request.urlopen(self.base + "/", timeout=3) as page:
            self.assertEqual(page.status, 200)
            self.assertIn("Bộ nhớ hợp nhất", page.read().decode())
        status, body = self.call("/api/health")
        self.assertEqual(status, 200); self.assertTrue(body["integrity"]["ok"])
        self.assertEqual(self.call("/api/memory", token=None)[0], 401)
        self.assertEqual(self.call("/api/memory", token="wrong")[0], 401)
    def test_create_list_read_delete(self):
        record = {"id":"api-fact", "type":"fact", "title":"HG2", "content":"Single system", "scope_id":"owner"}
        status, body = self.call("/api/memory", "POST", {"record":record, "idempotency_key":"create-1"})
        self.assertEqual(status, 201); self.assertEqual(body["memory"]["version"], 1)
        status, body = self.call("/api/memory")
        self.assertEqual(status, 200); self.assertEqual(body["count"], 1)
        self.assertEqual(self.call("/api/memory/api-fact")[0], 200)
        status, body = self.call("/api/memory/api-fact", "DELETE", {"expected_version":1,"idempotency_key":"delete-1"})
        self.assertEqual(status, 200); self.assertEqual(body["memory"]["status"], "tombstoned")
        self.assertEqual(self.call("/api/memory/api-fact")[0], 404)
    def test_scope_enforced_and_no_duplicate_json_keys(self):
        record = {"id":"denied", "type":"fact", "title":"x", "content":"y", "scope_id":"other"}
        self.assertEqual(self.call("/api/memory", "POST", {"record":record,"idempotency_key":"k"})[0], 403)
        self.assertEqual(self.call("/api/memory", "POST", raw=b'{"record":{},"record":{},"idempotency_key":"k"}')[0], 400)
    def test_startup_fails_without_token(self):
        with patch.dict(os.environ, {"HG_API_TOKEN":""}, clear=False):
            with self.assertRaises(RuntimeError): HGHTTPServer(("127.0.0.1", 0), runtime=self.rt)

if __name__ == "__main__": unittest.main()
