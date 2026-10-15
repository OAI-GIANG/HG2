"""Runtime acceptance tests for the owner-approved HG2 product-scope decisions."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from hg.history import StateStore
from hg.identity import PRODUCT_ID

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "hg_store_pre_mapping"
FIXTURE_SOURCE_SHA = "d11e71ed8b34338b8568664b39bc777c926826d5"
DURABLE_FILES = ("history.jsonl", "head.json", "state.json", "runtime_id")
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


class RuntimeSeparationTests(unittest.TestCase):
    def test_runtime_has_no_remote_endpoint_or_router(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("hg." + "edge", manifest["modules"])
        self.assertFalse((ROOT / "hg" / "edge.py").exists())
        source = (ROOT / "hg" / "phone_runtime.py").read_text(encoding="utf-8")
        forbidden = ("urllib.request", "urllib.error", "HG_" + "EDGE_URL", "HG_" + "EDGE_TOKEN", "/edge/" + "register", "/edge/" + "heartbeat")
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, source)

    def test_authority_allowlist_contains_only_local_actions(self):
        source = (ROOT / "hg" / "authority.py").read_text(encoding="utf-8")
        self.assertIn('ALLOWED = frozenset({"health.read", "session.create"})', source)
        self.assertNotIn("edge.heartbeat", source)
        self.assertNotIn("edge.register", source)


if __name__ == "__main__":
    unittest.main()
