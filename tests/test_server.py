import json, os, tempfile, threading, unittest, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from http.client import HTTPConnection
from hg.history import StateStore
from hg.phone_runtime import PhoneRuntime
from hg.server import HGHTTPServer
from hg.model_gateway import ModelGateway

READ_TOKEN = "test-hg-api-read-token"
WRITE_TOKEN = "test-hg-api-write-token"

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {"HG_API_READ_TOKEN": READ_TOKEN, "HG_API_WRITE_TOKEN": WRITE_TOKEN,
            "HG_API_READ_TOKEN_ID":"read-v1", "HG_API_WRITE_TOKEN_ID":"write-v1",
            "HG_API_READ_TOKEN_EXPIRES_AT":"4102444800", "HG_API_WRITE_TOKEN_EXPIRES_AT":"4102444800",
            "HG_API_REVOKED_TOKEN_IDS":"", "HG_API_PRINCIPAL_ID":"test-owner",
            "HG_MEMORY_READ_SCOPES":"owner,global,HG", "HG_MEMORY_WRITE_SCOPES":"owner,global,HG"}, clear=False)
        self.env.start(); self.addCleanup(self.env.stop)
        self.rt = PhoneRuntime(state_dir=self.tmp.name)
        self.srv = HGHTTPServer(("127.0.0.1", 0), runtime=self.rt)
        self.th = threading.Thread(target=self.srv.serve_forever, daemon=True); self.th.start()
        self.addCleanup(self.stop)
        self.base = "http://127.0.0.1:%d" % self.srv.server_port
    def stop(self):
        self.srv.shutdown(); self.srv.server_close(); self.th.join(timeout=2)
    def call(self, path, method="GET", obj=None, token=READ_TOKEN, raw=None, headers=None):
        data = raw if raw is not None else (None if obj is None else json.dumps(obj).encode())
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if token: req.add_header("Authorization", "Bearer " + token)
        if data is not None: req.add_header("Content-Type", "application/json")
        for name, value in (headers or {}).items():
            req.add_header(name, value)
        try:
            with urllib.request.urlopen(req, timeout=3) as resp: return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read())
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
    def test_credential_expiry_and_revocation_fail_closed(self):
        self.srv.read_token_expires_at = 1
        status, body = self.call("/api/memory")
        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["code"], "CREDENTIAL_EXPIRED")
        self.assertNotIn(READ_TOKEN, json.dumps(body))
        self.srv.read_token_expires_at = 4102444800
        self.srv.revoked_token_ids = frozenset({"read-v1"})
        status, body = self.call("/api/memory")
        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["code"], "CREDENTIAL_REVOKED")
        self.assertNotIn(READ_TOKEN, json.dumps(body))

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
        test_case = self
        class FakeGateway:
            def __init__(self):
                self.calls = 0
            def status(self):
                return {"configured": True, "status": "CONFIGURED", "network_called": False}
            def ask(self, query, context):
                self.calls += 1
                assert context["manifest"]["model_called"] is False
                event_types = [event["event_type"] for event in test_case.rt.store.replay()]
                test_case.assertIn("model.call.started", event_types)
                test_case.assertEqual(event_types[-1], "model.call.started")
                return {"answer":"mock answer","model":"fake-model","manifest":{
                    "query_sha256":"a"*64,"context_manifest_sha256":context["manifest"]["manifest_sha256"],
                    "request_sha256":"b"*64,"response_sha256":"c"*64,"manifest_sha256":"d"*64}}
        gateway = FakeGateway()
        self.rt.model_gateway = gateway
        idem = {"Idempotency-Key": "ask-success-test-01"}
        status, body = self.call("/api/ask", "POST", {"query": "What is HG2?"},
                                 token=READ_TOKEN, headers=idem)
        self.assertEqual(status, 200)
        self.assertEqual(body["answer"], "mock answer")
        self.assertEqual(body["brain"]["status"], "PARTIAL")
        self.assertEqual(body["brain"]["invoked_branches"], ["memory_knowledge", "research_synthesis"])
        self.assertEqual([item["status"] for item in body["brain"]["branch_results"]], ["SUCCESS", "RESPONSE_ONLY"])
        self.assertRegex(body["brain"]["plan_digest"], r"^[0-9a-f]{64}$")
        self.assertEqual(body["context_manifest"]["model_called"],False)
        events = self.rt.store.replay()
        event_types = [event["event_type"] for event in events]
        self.assertIn("brain.request.harness.gated", event_types)
        gate_event = next(event for event in events if event["event_type"] == "brain.request.harness.gated")
        self.assertTrue(gate_event["payload"]["ok"])
        self.assertRegex(gate_event["payload"]["receipt_digest"], r"^[0-9a-f]{64}$")
        self.assertLess(event_types.index("brain.request.planned"), event_types.index("brain.request.harness.gated"))
        self.assertLess(event_types.index("brain.request.harness.gated"), event_types.index("brain.request.started"))
        self.assertLess(event_types.index("brain.request.harness.gated"), event_types.index("model.call.started"))
        self.assertEqual(body["unified_harness"]["pre_dispatch"]["reason_code"], "HARNESS_DISPATCH_ALLOWED")
        self.assertEqual(body["unified_harness"]["quality_gate"]["result_status"], "PARTIAL")
        self.assertTrue(body["unified_harness"]["quality_gate"]["ok"])
        self.assertIn("model.call.started", event_types)
        self.assertIn("model.call.completed", event_types)
        self.assertLess(event_types.index("model.call.started"), event_types.index("model.call.completed"))
        start_event = next(event for event in events if event["event_type"] == "model.call.started")
        self.assertEqual(start_event["payload"]["brain_request_id"], body["brain"]["request_id"])
        self.assertNotIn("What is HG2?", json.dumps(start_event["payload"]))
        self.assertIn("brain.request.accepted", event_types)
        self.assertIn("brain.request.planned", event_types)
        self.assertIn("brain.request.attempt.started", event_types)
        self.assertIn("brain.step.started", event_types)
        self.assertIn("brain.step.completed", event_types)
        self.assertIn("brain.request.finished", event_types)
        self.assertRegex(body["capability_registry"]["registry_digest"], r"^[0-9a-f]{64}$")
        self.assertEqual(set(body["capability_registry"]["active_capabilities"]),
                         {"memory.search", "synthesis.propose"})
        planned = next(event for event in events if event["event_type"] == "brain.request.planned")
        self.assertEqual(planned["payload"]["registry_digest"],
                         body["capability_registry"]["registry_digest"])
        registry_by_id = {item["capability_id"]: item for item in planned["payload"]["registry_entries"]}
        self.assertEqual(registry_by_id["memory.search"]["lifecycle_state"], "TESTED")
        self.assertNotIn("task.decompose", registry_by_id)
        self.assertFalse(registry_by_id["synthesis.propose"]["hard_timeout_enforced"])

        # A duplicate with the same principal, key, source and normalized input replays
        # the bounded in-process response cache without calling the provider twice.
        replay_status, replay_body = self.call(
            "/api/ask", "POST", {"query": "What is HG2?"},
            token=READ_TOKEN, headers=idem,
        )
        self.assertEqual(replay_status, 200)
        self.assertEqual(replay_body["answer"], "mock answer")
        self.assertTrue(replay_body["idempotency"]["replayed"])
        self.assertEqual(gateway.calls, 1)

        conflict_status, conflict_body = self.call(
            "/api/ask", "POST", {"query": "A different request"},
            token=READ_TOKEN, headers=idem,
        )
        self.assertEqual(conflict_status, 409)
        self.assertEqual(conflict_body["error"]["code"], "IDEMPOTENCY_KEY_CONFLICT")
        self.assertEqual(gateway.calls, 1)

        # Simulate process-local cache loss after restart. Do not repeat provider call.
        self.srv._ask_response_cache.clear()
        final_status, final_body = self.call(
            "/api/ask", "POST", {"query": "What is HG2?"},
            token=READ_TOKEN, headers=idem,
        )
        self.assertEqual(final_status, 409)
        self.assertEqual(final_body["error"]["code"], "IDEMPOTENCY_OUTCOME_FINAL_RESPONSE_NOT_CACHED")
        self.assertEqual(gateway.calls, 1)

    def test_ask_normalizes_exact_output_envelope_and_replays(self):
        token = "HG2_RUNTIME_IDEMPOTENCY_CHECK"

        class ProviderHandler(BaseHTTPRequestHandler):
            calls = 0
            def do_POST(self):
                n = int(self.headers.get("Content-Length", "0"))
                json.loads(self.rfile.read(n))
                ProviderHandler.calls += 1
                content = json.dumps({"answer": token}, separators=(",", ":"))
                payload = json.dumps({"model": "fake-model-v1", "choices": [{"message": {"content": content}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            def log_message(self, *args):
                return

        ProviderHandler.calls = 0
        provider = ThreadingHTTPServer(("127.0.0.1", 0), ProviderHandler)
        provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
        provider_thread.start()
        def stop_provider():
            provider.shutdown(); provider.server_close(); provider_thread.join(timeout=2)
        self.addCleanup(stop_provider)
        self.rt.model_gateway = ModelGateway(
            base_url="http://127.0.0.1:%d/v1" % provider.server_port,
            api_key="fake-provider-key", model="fake-model", timeout=3,
        )
        headers = {"Idempotency-Key": "ask-exact-output-normalizer-test-01"}
        status, body = self.call(
            "/api/ask", "POST", {"query": "Return exactly HG2_RUNTIME_IDEMPOTENCY_CHECK and nothing else."},
            token=READ_TOKEN, headers=headers,
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["answer"], token)
        self.assertEqual(body["model_manifest"]["answer_normalization"], "UNWRAPPED_EXACT_ANSWER_JSON_ENVELOPE")
        self.assertNotEqual(body["model_manifest"]["provider_answer_sha256"], body["model_manifest"]["normalized_answer_sha256"])
        self.assertEqual(body["brain"]["status"], "PARTIAL")
        self.assertEqual([x["status"] for x in body["brain"]["branch_results"]], ["SUCCESS", "RESPONSE_ONLY"])
        events_after_first = len(self.rt.store.replay())
        self.assertEqual(ProviderHandler.calls, 1)

        replay_status, replay_body = self.call(
            "/api/ask", "POST", {"query": "Return exactly HG2_RUNTIME_IDEMPOTENCY_CHECK and nothing else."},
            token=READ_TOKEN, headers=headers,
        )
        self.assertEqual(replay_status, 200)
        self.assertEqual(replay_body["answer"], token)
        self.assertTrue(replay_body["idempotency"]["replayed"])
        self.assertEqual(ProviderHandler.calls, 1)
        self.assertEqual(len(self.rt.store.replay()), events_after_first)
        self.assertTrue(self.rt.store.verify()["ok"])

    def test_ask_fails_closed_when_precall_audit_write_fails(self):
        self.rt.memory.remember({"id":"audit-fail-memory","type":"fact","title":"HG2","content":"single runtime","scope_id":"owner"},
            principal_id="test-owner", grants={"owner"}, idempotency_key="audit-fail-memory-create")
        class FakeGateway:
            def __init__(self):
                self.calls = 0
            def status(self):
                return {"configured": True, "status": "CONFIGURED", "network_called": False}
            def ask(self, query, context):
                self.calls += 1
                return {"answer":"must not be reached","model":"fake-model","manifest":{
                    "query_sha256":"a"*64,"context_manifest_sha256":context["manifest"]["manifest_sha256"],
                    "request_sha256":"b"*64,"response_sha256":"c"*64,"manifest_sha256":"d"*64}}
        gateway = FakeGateway()
        self.rt.model_gateway = gateway
        original_emit = self.rt.store.emit
        def fail_start(event_type, payload, **kwargs):
            if event_type == "model.call.started":
                raise OSError("simulated audit storage failure")
            return original_emit(event_type, payload, **kwargs)
        with patch.object(self.rt.store, "emit", side_effect=fail_start):
            status, body = self.call(
                "/api/ask", "POST", {"query": "Do not call without an audit record"},
                token=READ_TOKEN, headers={"Idempotency-Key": "ask-audit-fail-test-01"})
        self.assertEqual(status, 503)
        self.assertEqual(body["brain"]["status"], "BLOCKED")
        self.assertEqual(body["brain"]["branch_results"][-1]["error_code"], "PRECALL_AUDIT_WRITE_FAILED")
        self.assertEqual(gateway.calls, 0)
        event_types = [event["event_type"] for event in self.rt.store.replay()]
        self.assertNotIn("model.call.started", event_types)
        self.assertNotIn("model.call.completed", event_types)

    def test_strict_harness_blocks_provider_before_dispatch_and_persists_receipt(self):
        from hg.unified_harness import UnifiedHarness
        self.srv.harness = UnifiedHarness(profile="strict")
        self.rt.memory.remember(
            {"id": "strict-harness-memory", "type": "fact", "title": "HG2",
             "content": "strict harness pre-dispatch gate", "scope_id": "owner"},
            principal_id="test-owner", grants={"owner"}, idempotency_key="strict-harness-memory-create")

        class FakeGateway:
            def __init__(self):
                self.calls = 0
            def status(self):
                return {"configured": True, "status": "CONFIGURED", "network_called": False}
            def ask(self, query, context):
                self.calls += 1
                raise AssertionError("strict harness must block before provider call")

        gateway = FakeGateway()
        self.rt.model_gateway = gateway
        status, body = self.call(
            "/api/ask", "POST", {"query": "strict pre-dispatch test"},
            token=READ_TOKEN, headers={"Idempotency-Key": "strict-harness-block-01"})
        self.assertEqual(status, 503)
        self.assertEqual(body["brain"]["status"], "BLOCKED_HARNESS_GATE")
        self.assertEqual(body["error"]["code"], "HARNESS_STRICT_TIMEOUT_GATE_BLOCKED")
        self.assertEqual(gateway.calls, 0)
        events = self.rt.store.replay()
        event_types = [event["event_type"] for event in events]
        self.assertIn("brain.request.harness.gated", event_types)
        self.assertLess(event_types.index("brain.request.harness.gated"),
                        event_types.index("brain.request.blocked"))
        self.assertNotIn("brain.request.started", event_types)
        self.assertNotIn("model.call.started", event_types)
        gate_event = next(event for event in events if event["event_type"] == "brain.request.harness.gated")
        self.assertFalse(gate_event["payload"]["ok"])
        self.assertEqual(gate_event["payload"]["profile"], "strict")
        self.assertTrue(self.rt.store.verify()["ok"])

    def test_ask_without_provider_config_fails_closed(self):
        from hg.model_gateway import ModelGateway
        self.rt.model_gateway = ModelGateway(base_url="", api_key="", model="")
        status, body = self.call("/api/ask", "POST", {"query": "No provider"},
                                 token=READ_TOKEN, headers={"Idempotency-Key": "ask-no-provider-test-01"})
        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["code"], "MODEL_NOT_CONFIGURED")

    def test_ask_requires_client_idempotency_key(self):
        class FakeGateway:
            def status(self):
                return {"configured": True, "network_called": False}
        self.rt.model_gateway = FakeGateway()
        status, body = self.call("/api/ask", "POST", {"query": "no key"}, token=READ_TOKEN)
        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["code"], "IDEMPOTENCY_KEY_REQUIRED")
        event_types = [event["event_type"] for event in self.rt.store.replay()]
        self.assertNotIn("brain.request.accepted", event_types)
        self.assertNotIn("model.call.started", event_types)

    def test_concurrent_duplicate_ask_is_not_dispatched_twice(self):
        entered = threading.Event()
        release = threading.Event()
        class FakeGateway:
            def __init__(self): self.calls = 0
            def status(self):
                return {"configured": True, "status": "CONFIGURED", "network_called": False}
            def ask(self, query, context):
                self.calls += 1
                entered.set()
                if not release.wait(2.0):
                    raise TimeoutError("test release timed out")
                return {"answer": "single provider call", "model": "fake-model", "manifest": {
                    "query_sha256": "a" * 64,
                    "context_manifest_sha256": context["manifest"]["manifest_sha256"],
                    "request_sha256": "b" * 64, "response_sha256": "c" * 64,
                    "manifest_sha256": "d" * 64,
                }}
        gateway = FakeGateway()
        self.rt.model_gateway = gateway
        headers = {"Idempotency-Key": "ask-concurrent-test-01"}
        result = {}
        thread = threading.Thread(target=lambda: result.setdefault(
            "first", self.call("/api/ask", "POST", {"query": "same concurrent request"},
                               token=READ_TOKEN, headers=headers)))
        thread.start()
        self.assertTrue(entered.wait(1.5), "provider request did not start")
        status, body = self.call("/api/ask", "POST", {"query": "same concurrent request"},
                                 token=READ_TOKEN, headers=headers)
        self.assertEqual(status, 409)
        self.assertEqual(body["error"]["code"], "IDEMPOTENCY_REQUEST_IN_PROGRESS")
        release.set()
        thread.join(timeout=3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["first"][0], 200)
        self.assertEqual(gateway.calls, 1)
        self.assertTrue(self.rt.store.verify()["ok"])

    def test_memory_evidence_verifier_rejects_tampered_context(self):
        from hg.contracts import canonical_digest
        from hg.server import HGRequestHandler
        self.rt.memory.remember(
            {"id": "verify-source", "type": "fact", "title": "HG2 evidence",
             "content": "authorized source content", "scope_id": "owner"},
            principal_id="test-owner", grants={"owner"}, idempotency_key="verify-source-create")
        request_id = "ask-" + "f" * 32
        correlation_id = "corr-" + "f" * 32
        attempt_id = "attempt-fixture"
        self.rt.store.emit(
            "brain.step.started",
            {"request_id": request_id, "correlation_id": correlation_id,
             "attempt_id": attempt_id, "plan_digest": "d" * 64,
             "domain_id": "memory_knowledge", "required_capabilities": ["memory.search"]},
            correlation_id=correlation_id,
            event_id=f"brain-step-started:{request_id}:{attempt_id}:memory_knowledge")
        context = self.rt.memory.build_context("HG2 evidence", grants={"owner"}, limit=10, max_chars=12000)
        digest = canonical_digest(context["manifest"])
        handler = object.__new__(__import__("hg.server", fromlist=["HGRequestHandler"]).HGRequestHandler)
        handler.server = self.srv
        reference = "evidence:sha256:" + digest
        self.assertTrue(handler._verify_memory_evidence(
            reference, context_value=context, query="HG2 evidence", grants={"owner"}, request_id=request_id))
        altered = json.loads(json.dumps(context))
        altered["context"][0]["content"] = "forged context bytes"
        self.assertFalse(handler._verify_memory_evidence(
            reference, context_value=altered, query="HG2 evidence", grants={"owner"}, request_id=request_id))
        self.assertFalse(handler._verify_memory_evidence(
            "evidence:sha256:" + "0" * 64, context_value=context,
            query="HG2 evidence", grants={"owner"}, request_id=request_id))

    def test_phone_runtime_restart_marks_orphan_provider_call_in_doubt(self):
        request_id = "ask-" + "e" * 32
        correlation_id = "corr-" + "e" * 32
        payload = {
            "operation": "model_answer", "query_sha256": "a" * 64,
            "context_manifest_sha256": "b" * 64, "brain_plan_digest": "c" * 64,
            "brain_request_id": request_id, "correlation_id": correlation_id,
            "operation_key_sha256": "e" * 64,
        }
        self.rt.store.emit("model.call.started", payload, correlation_id=correlation_id,
                           event_id="model-call-start:" + request_id)
        recovered = PhoneRuntime(state_dir=self.tmp.name)
        doubts = [e for e in recovered.store.replay()
                  if e["event_type"] == "model.call.in_doubt"
                  and e["payload"].get("brain_request_id") == request_id]
        self.assertEqual(len(doubts), 1)
        self.assertEqual(doubts[0]["payload"]["reason"], "OUTCOME_UNKNOWN_AFTER_START")
        self.assertTrue(recovered.store.verify()["ok"])
        recovered_again = PhoneRuntime(state_dir=self.tmp.name)
        doubts_again = [e for e in recovered_again.store.replay()
                        if e["event_type"] == "model.call.in_doubt"
                        and e["payload"].get("brain_request_id") == request_id]
        self.assertEqual(len(doubts_again), 1)

    def test_second_http_server_cannot_own_same_state_directory(self):
        with self.assertRaisesRegex(RuntimeError, "RUNTIME_STATE_DIRECTORY_ALREADY_IN_USE"):
            HGHTTPServer(("127.0.0.1", 0), runtime=self.rt)
        self.assertTrue(self.rt.store.verify()["ok"])

    def test_production_server_creates_fresh_state_under_process_lock(self):
        fresh = os.path.join(self.tmp.name, "fresh-not-created")
        self.assertFalse(os.path.exists(fresh))
        with patch.dict(os.environ, {"HG_STATE_DIR": fresh}, clear=False):
            server = HGHTTPServer(("127.0.0.1", 0))
            try:
                self.assertTrue(os.path.isdir(fresh))
                self.assertTrue(os.path.isfile(os.path.join(fresh, ".hg2-http-runtime.lock")))
                self.assertTrue(server.runtime.store.verify()["ok"])
                with self.assertRaisesRegex(RuntimeError, "RUNTIME_STATE_DIRECTORY_ALREADY_IN_USE"):
                    HGHTTPServer(("127.0.0.1", 0))
            finally:
                server.server_close()
    def test_scope_enforced_and_no_duplicate_json_keys(self):
        record = {"id":"denied", "type":"fact", "title":"x", "content":"y", "scope_id":"other"}
        self.assertEqual(self.call("/api/memory", "POST", {"record":record,"idempotency_key":"k"}, token=WRITE_TOKEN)[0], 403)
        self.assertEqual(self.call("/api/memory", "POST", raw=b'{"record":{},"record":{},"idempotency_key":"k"}', token=WRITE_TOKEN)[0], 400)
    def test_startup_fails_closed_for_invalid_credential_ids_or_revocation_list(self):
        cases = [
            {"HG_API_READ_TOKEN_ID": ""},
            {"HG_API_READ_TOKEN_ID": "same-id", "HG_API_WRITE_TOKEN_ID": "same-id"},
            {"HG_API_REVOKED_TOKEN_IDS": "*"},
        ]
        for values in cases:
            with self.subTest(values=values), patch.dict(os.environ, values, clear=False):
                with self.assertRaises(RuntimeError):
                    HGHTTPServer(("127.0.0.1", 0), runtime=self.rt)

    def test_startup_fails_without_credential_expiry(self):
        with patch.dict(os.environ, {"HG_API_READ_TOKEN_EXPIRES_AT": ""}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "HG_API_READ_TOKEN_EXPIRES_AT"):
                HGHTTPServer(("127.0.0.1", 0), runtime=self.rt)

    def test_startup_fails_without_token(self):
        with patch.dict(os.environ, {"HG_API_READ_TOKEN":"", "HG_API_WRITE_TOKEN":""}, clear=False):
            with self.assertRaises(RuntimeError): HGHTTPServer(("127.0.0.1", 0), runtime=self.rt)

    def test_startup_fails_when_read_and_write_credentials_match(self):
        with patch.dict(os.environ, {"HG_API_READ_TOKEN":"same", "HG_API_WRITE_TOKEN":"same"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "distinct"):
                HGHTTPServer(("127.0.0.1", 0), runtime=self.rt)

if __name__ == "__main__": unittest.main()
