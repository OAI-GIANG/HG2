"""Runtime acceptance tests for the owner-approved HG2 product-scope decisions."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from http.server import ThreadingHTTPServer

from hg import edge
from hg.history import StateStore
from hg.identity import PRODUCT_ID

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "hg_store_pre_mapping"
FIXTURE_SOURCE_SHA = "d11e71ed8b34338b8568664b39bc777c926826d5"
DURABLE_FILES = ("history.jsonl", "head.json", "state.json", "runtime_id")
EDGE_TOKEN = "scope-acceptance-test-token"


class CandidateEdgeServer:
    def __init__(self, testcase):
        self.testcase = testcase
        self._token_patch = patch.dict(os.environ, {"HG_EDGE_TOKEN": EDGE_TOKEN}, clear=False)
        self._token_patch.start()
        edge.DEVICES.clear()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), edge.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.server.server_port
        testcase.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        edge.DEVICES.clear()
        self._token_patch.stop()

    def request(self, method, path, body=None):
        req = urllib.request.Request(self.base + path, data=body, method=method)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=3) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, exc.read()
            finally:
                exc.close()


class HttpApiRemovalAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.edge_server = CandidateEdgeServer(self)

    def test_legacy_hg_api_routes_are_not_served_by_candidate_router(self):
        cases = (
            ("GET", "/v1/sessions", None),
            ("POST", "/v1/sessions", b"{}"),
            ("GET", "/v1/history", None),
            ("POST", "/v1/history", b"{}"),
        )
        for method, path, body in cases:
            with self.subTest(method=method, path=path):
                status, raw = self.edge_server.request(method, path, body)
                self.assertEqual(status, 404)
                self.assertEqual(json.loads(raw), {"ok": False, "error": "NOT_FOUND"})
        self.assertEqual(edge.DEVICES, {}, "unsupported legacy routes must not mutate edge state")

    def test_supported_edge_routes_remain_available_and_auth_fail_closed(self):
        status, raw = self.edge_server.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(raw)["ok"])
        status, raw = self.edge_server.request("POST", "/edge/register", b'{"device_id":"d1"}')
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(raw)["error"], "AUTHENTICATION_REQUIRED")
        self.assertEqual(edge.DEVICES, {})

    def test_candidate_manifest_does_not_ship_legacy_http_service(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("runtime.hg_runtime.service", manifest["modules"])
        self.assertFalse((ROOT / "hg" / "service.py").exists())
        self.assertFalse((ROOT / "hg" / "runtime").exists())


class PhoneBridgeRemovalAcceptanceTests(unittest.TestCase):
    def test_bridge_implementation_protocol_and_claims_are_absent_from_runtime_package(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertFalse(any("bridge" in module.lower() for module in manifest["modules"]))
        self.assertFalse(any("bridge" in path.name.lower() for path in (ROOT / "hg").rglob("*")))
        forbidden_runtime_symbols = (
            "PROTOCOL_VERSION", "ReplayGuard", "GovernedExecutionSubmission",
            "EvidenceCorrelation", "BridgeRequest", "AuthenticatedPrincipal",
        )
        for path in (ROOT / "hg").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for symbol in forbidden_runtime_symbols:
                with self.subTest(path=str(path.relative_to(ROOT)), symbol=symbol):
                    self.assertNotIn(symbol, source)

    def test_phone_runtime_still_fails_closed_without_real_verifier(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = __import__("hg.phone_runtime", fromlist=["PhoneRuntime"]).PhoneRuntime(state_dir=directory)
            before = Path(directory, "history.jsonl").read_bytes()
            with self.assertRaises(PermissionError):
                runtime.start_session(credential="arbitrary-credential")
            self.assertEqual(Path(directory, "history.jsonl").read_bytes(), before)
            self.assertTrue(runtime.store.verify()["ok"])


class ProductIdentityAcceptanceTests(unittest.TestCase):
    def test_fresh_store_replay_projection_and_audit_export_keep_hg_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(directory, clock=lambda: 1700000000.0)
            store.emit("session.created", {"session_id": "new-session", "product": "HG"},
                       event_id="new-session-event", correlation_id="new-session-correlation")
            self.assertEqual(PRODUCT_ID, "HG")
            self.assertTrue(store.verify()["ok"])
            self.assertTrue(all(record["product_id"] == "HG" for record in store.replay()))
            self.assertEqual(store.audit_export()["product_id"], "HG")
            self.assertEqual(store.audit_export()["state"]["product_id"], "HG")
            manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["product_id"], "HG")
            self.assertEqual(manifest["product_name"], "HG2")
            self.assertEqual(manifest["name"], "hg2")

    def test_pre_mapping_canonical_fixture_reopens_without_rewriting_durable_bytes(self):
        fixture_manifest = json.loads((FIXTURE / "fixture_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(fixture_manifest["source_canonical_sha"], FIXTURE_SOURCE_SHA)
        with tempfile.TemporaryDirectory() as directory:
            for name in DURABLE_FILES:
                shutil.copyfile(FIXTURE / name, Path(directory) / name)
            before = {name: (Path(directory) / name).read_bytes() for name in DURABLE_FILES}
            reopened = StateStore(directory)
            exported = reopened.audit_export()
            self.assertTrue(exported["verify"]["ok"], exported["verify"])
            self.assertEqual(exported["product_id"], "HG")
            self.assertEqual(exported["state"]["product_id"], "HG")
            self.assertTrue(all(event["product_id"] == "HG" for event in reopened.replay()))
            self.assertEqual([event["event_id"] for event in reopened.replay()], fixture_manifest["event_ids"])
            self.assertEqual([event["event_type"] for event in reopened.replay()], fixture_manifest["event_types"])
            self.assertEqual(reopened.replay()[-1]["event_id"], "legacy-fixture-event")
            after = {name: (Path(directory) / name).read_bytes() for name in DURABLE_FILES}
            self.assertEqual(before, after, "opening/replaying must not rewrite historical durable bytes")

    def test_fixture_file_hashes_match_recorded_manifest(self):
        fixture_manifest = json.loads((FIXTURE / "fixture_manifest.json").read_text(encoding="utf-8"))
        for name in DURABLE_FILES:
            with self.subTest(file=name):
                actual = hashlib.sha256((FIXTURE / name).read_bytes()).hexdigest()
                self.assertEqual(actual, fixture_manifest["sha256"][name])


class DependencyInventoryTests(unittest.TestCase):
    def test_source_inventory_has_exact_refs_hashes_and_open_external_consumer_limit(self):
        inventory = json.loads((ROOT / "evidence" / "HG2_PRODUCT_SCOPE_DEPENDENCY_INVENTORY_V1.json").read_text(encoding="utf-8"))
        self.assertEqual(inventory["candidate_before_acceptance_tests"]["sha"], "d834b7424c89c346b9db55d79dd869ecca46cd31")
        self.assertEqual(inventory["http_api"]["legacy_source"]["commit"], "0495ac8bba4dc59bbf5b84ef7f38dd78bae7dead")
        self.assertEqual(inventory["phone_bridge"]["source"]["commit"], "4a20c319fe740f1a092ade4e407d693439629385")
        ops = next(repo for repo in inventory["repositories_examined"] if repo["repository"] == "OAI-GIANG/hg-ops")
        self.assertEqual(ops["sha"], "2e75a6cbae2fa46e48ffa3fe67a134c385ee880e")
        self.assertIn("No references", inventory["http_api"]["known_dependencies"]["operations_repo_scan"]["result"])
        self.assertEqual(inventory["http_api"]["known_dependencies"]["external_deployments_or_clients"], "UNKNOWN_NOT_ACCESSIBLE_FROM_REPOSITORY_SOURCES")
        self.assertEqual(inventory["phone_bridge"]["consumer_search"]["external_clients_or_deployments"], "UNKNOWN_NOT_ACCESSIBLE_FROM_REPOSITORY_SOURCES")
        for source in inventory["http_api"]["legacy_source"]["files"] + inventory["phone_bridge"]["source"]["files"]:
            with self.subTest(path=source["path"]):
                self.assertEqual(len(source["git_blob"]), 40)
                self.assertEqual(len(source["sha256"]), 64)
        self.assertEqual(inventory["overall_gate"], "BLOCKED_NO_GO")


if __name__ == "__main__":
    unittest.main()
