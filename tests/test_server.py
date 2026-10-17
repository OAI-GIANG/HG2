import json, os, tempfile, threading, unittest, urllib.error, urllib.request
from unittest.mock import patch
from http.client import HTTPConnection
from hg.history import StateStore
from hg.phone_runtime import PhoneRuntime
from hg.server import HGHTTPServer

READ_TOKEN = "test-hg-api-read-token"
WRITE_TOKEN = "test-hg-api-write-token"

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {"HG_API_READ_TOKEN": READ_TOKEN, "HG_API_WRITE_TOKEN": WRITE_TOKEN, "HG_API_PRINCIPAL_ID":"test-owner",
            "HG_MEMORY_READ_SCOPES":"owner,global,HG", "HG_MEMORY_WRITE_SCOPES":"owner,global,HG"}, clear=False)
        self.env.start(); self.addCleanup(self.env.stop)
        self.rt = PhoneRuntime(state_dir=self.tmp.name)
        self.srv = HGHTTPServer(("127.0.0.1", 0), runtime=self.rt)
        self.th = threading.Thread(target=self.srv.serve_forever, daemon=True); self.th.start()
        self.addCleanup(self.stop)
        self.base = "http://127.0.0.1:%d" % self.srv.server_port
    def stop(self):
        self.srv.shutdown(); self.srv.server_close(); self.th.join(timeout=2)
    def call(self, path, method="GET", obj=None, token=READ_TOKEN, raw=None):
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
        self.assertEqual(body["build"]["git_commit"], os.environ.get("HG_BUILD_COMMIT", "UNDECLARED"))
        self.assertRegex(body["build"]["source_manifest_sha256"], r"^[0-9a-f]{64}$")
        self.assertGreater(body["build"]["source_file_count"], 1)
        self.assertTrue(body["provenance"]["ok"])
        self.assertEqual(body["provenance"]["current_manifest_sha256"], body["build"]["source_manifest_sha256"])
        self.assertEqual(body["model_gateway"]["status"], "NOT_CONFIGURED")
        self.assertFalse(body["model_gateway"]["network_called"])
        self.assertEqual(body["build"]["process_pid"], self.srv.build_identity["process_pid"])
        self.assertEqual(self.call("/api/library", token=None)[0], 401)
        self.assertEqual(self.call("/api/library", token=WRITE_TOKEN)[0], 401)
        self.srv.read_scopes = frozenset({"owner"})
        self.assertEqual(self.call("/api/library")[0], 403)
        self.srv.read_scopes = frozenset({"owner", "global", "HG"})
        self.assertEqual(self.call("/api/memory", token=None)[0], 401)
        self.assertEqual(self.call("/api/memory", token="wrong")[0], 401)
        self.assertEqual(self.call("/api/memory", token=WRITE_TOKEN)[0], 401)
        rec = {"id":"read-token-write-attempt", "type":"fact", "title":"x", "content":"y", "scope_id":"owner"}
        self.assertEqual(self.call("/api/memory", "POST", {"record":rec,"idempotency_key":"no-write"}, token=READ_TOKEN)[0], 401)
    def test_source_provenance_mismatch_degrades_health(self):
        with patch("hg.server.runtime_manifest", return_value={"manifest_sha256":"0" * 64, "files":[]}):
            status, body = self.call("/api/health")
        self.assertEqual(status, 503)
        self.assertFalse(body["ok"])
        self.assertFalse(body["provenance"]["ok"])

    def test_library_endpoint_empty_state_and_path_integrity_fail_closed(self):
        status, body = self.call("/api/library")
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["quarantined_count"], 0)
        self.assertEqual(body["source"], "LOCAL_HASH_VERIFIED_BLOBS")
        self.rt.store.emit("legacy.library.asset.imported", {
            "relative_blob": "library/" + "0" * 64, "sha256": "0" * 64, "legacy_id": "asset-1", "name": "x"
        }, event_id="library-test-event")
        status, body = self.call("/api/library")
        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["code"], "LIBRARY_INTEGRITY_FAILED")

    def test_create_list_read_delete(self):
        record = {"id":"api-fact", "type":"fact", "title":"HG2", "content":"Single system", "scope_id":"owner"}
        status, body = self.call("/api/memory", "POST", {"record":record, "idempotency_key":"create-1"}, token=WRITE_TOKEN)
        self.assertEqual(status, 201); self.assertEqual(body["memory"]["version"], 1)
        status, body = self.call("/api/memory")
        self.assertEqual(status, 200); self.assertEqual(body["count"], 1)
        self.assertEqual(self.call("/api/memory/api-fact")[0], 200)
        status, body = self.call("/api/memory/search?q=Single+system")
        self.assertEqual(status, 200); self.assertEqual(body["manifest"]["model_called"], False)
        status, body = self.call("/api/memory/context?q=Single+system")
        self.assertEqual(status, 200); self.assertEqual(body["manifest"]["operation"], "memory_context")
        status, body = self.call("/api/memory/api-fact", "DELETE", {"expected_version":1,"idempotency_key":"delete-1"}, token=WRITE_TOKEN)
        self.assertEqual(status, 200); self.assertEqual(body["memory"]["status"], "tombstoned")
        self.assertEqual(self.call("/api/memory/api-fact")[0], 404)
    def test_ask_uses_authorized_context_and_audits_call(self):
        self.rt.memory.remember({"id":"ask-memory","type":"fact","title":"HG2","content":"single runtime","scope_id":"owner"},
            principal_id="test-owner",grants={"owner"},idempotency_key="ask-memory-create")
        class FakeGateway:
            def ask(self, query, context):
                assert context["manifest"]["model_called"] is False
                return {"answer":"mock answer","model":"fake-model","manifest":{
                    "query_sha256":"a"*64,"context_manifest_sha256":context["manifest"]["manifest_sha256"],
                    "request_sha256":"b"*64,"response_sha256":"c"*64,"manifest_sha256":"d"*64}}
        self.rt.model_gateway=FakeGateway()
        status, body=self.call("/api/ask","POST",{"query":"What is HG2?"},token=READ_TOKEN)
        self.assertEqual(status,200); self.assertEqual(body["answer"],"mock answer")
        self.assertEqual(body["context_manifest"]["model_called"],False)
        self.assertIn("model.call.completed",[e["event_type"] for e in self.rt.store.replay()])
    def test_ask_without_provider_config_fails_closed(self):
        from hg.model_gateway import ModelGateway
        self.rt.model_gateway=ModelGateway(base_url="",api_key="",model="")
        status, body=self.call("/api/ask","POST",{"query":"No provider"},token=READ_TOKEN)
        self.assertEqual(status,503); self.assertEqual(body["error"]["code"],"MODEL_NOT_CONFIGURED")
    def test_scope_enforced_and_no_duplicate_json_keys(self):
        record = {"id":"denied", "type":"fact", "title":"x", "content":"y", "scope_id":"other"}
        self.assertEqual(self.call("/api/memory", "POST", {"record":record,"idempotency_key":"k"}, token=WRITE_TOKEN)[0], 403)
        self.assertEqual(self.call("/api/memory", "POST", raw=b'{"record":{},"record":{},"idempotency_key":"k"}', token=WRITE_TOKEN)[0], 400)
    def test_startup_fails_without_token(self):
        with patch.dict(os.environ, {"HG_API_READ_TOKEN":"", "HG_API_WRITE_TOKEN":""}, clear=False):
            with self.assertRaises(RuntimeError): HGHTTPServer(("127.0.0.1", 0), runtime=self.rt)

if __name__ == "__main__": unittest.main()
