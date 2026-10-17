import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integration"))
import phone_hg2_readonly as connector
from phone_hg2_readonly import API_BASE, CAPABILITY_ID, ConnectorError, FULL_REPO, REF, read_hg2_ref


class FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self.body = json.dumps(payload).encode()
        self.closed = False
    def read(self, size=-1):
        return self.body[:size]
    def close(self):
        self.closed = True


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        # Isolate per-test state for the process-local rate limiter.
        with connector._RATE_LOCK:
            connector._RATE_WINDOW_STARTED = 0.0
            connector._RATE_COUNT = 0
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.token = root / "token"
        self.token.write_text("test-token-not-real\n", encoding="utf-8")
        os.chmod(self.token, 0o600)
        self.registry = root / "registry.json"
        self.write_grant()
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def write_grant(self, **overrides):
        grant = {
            "id": CAPABILITY_ID, "owner_authorization": "GRANTED",
            "install_state": "AUTHORIZED", "runtime_state": "READY",
            "revocation_state": "ACTIVE",
            "target": {"repository": FULL_REPO, "ref": REF},
            "actions": ["commit.read", "manifest.read"],
            "requested_permissions": ["metadata:read", "contents:read"],
            "write_enabled": False,
        }
        grant.update(overrides)
        self.registry.write_text(json.dumps({"capabilities": {CAPABILITY_ID: grant}}), encoding="utf-8")
        os.chmod(self.registry, 0o600)

    def fake_open(self, request, timeout=8.0):
        self.calls.append(request)
        self.assertEqual(request.get_method(), "GET")
        self.assertTrue(request.full_url.startswith(API_BASE + "/repos/OAI-GIANG/HG2/"))
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token-not-real")
        if "/commits/" in request.full_url:
            payload = {"sha": "a" * 40, "html_url": "https://github.com/OAI-GIANG/HG2/commit/" + "a" * 40,
                       "commit": {"tree": {"sha": "b" * 40}}}
        else:
            payload = {"path": "manifest.json", "sha": "c" * 40, "encoding": "base64"}
        return FakeResponse(200, payload)

    def call_read(self, **kw):
        return read_hg2_ref(FULL_REPO, REF, token_path=self.token, registry_path=self.registry,
                            opener=self.fake_open, **kw)

    def test_positive_returns_commit_and_manifest_hashes(self):
        result = self.call_read()
        self.assertTrue(result["ok"])
        self.assertEqual(result["commit_sha"], "a" * 40)
        self.assertEqual(result["tree_sha"], "b" * 40)
        self.assertEqual(result["manifest_blob_sha"], "c" * 40)
        self.assertEqual(result["http_status"], {"commit": 200, "manifest": 200})
        self.assertEqual(len(self.calls), 2)

    def test_wrong_repository_and_ref_denied_before_any_file_or_network_access(self):
        for repo, ref, reason in [
            ("OTHER/HG2", REF, "REPOSITORY_SCOPE_MISMATCH"),
            (FULL_REPO, "main", "REF_SCOPE_MISMATCH"),
        ]:
            with self.subTest(repo=repo, ref=ref):
                with self.assertRaises(ConnectorError) as caught:
                    read_hg2_ref(repo, ref, token_path=self.token, registry_path=self.registry, opener=self.fake_open)
                self.assertEqual(caught.exception.code, reason)
                self.assertEqual(self.calls, [])

    def test_missing_or_revoked_capability_fails_closed(self):
        self.registry.unlink()
        with self.assertRaises(ConnectorError) as caught:
            self.call_read()
        self.assertEqual(caught.exception.code, "CAPABILITY_REGISTRY_UNAVAILABLE")
        self.write_grant(revocation_state="REVOKED")
        with self.assertRaises(ConnectorError) as caught:
            self.call_read()
        self.assertEqual(caught.exception.code, "CAPABILITY_NOT_AUTHORIZED")
        self.assertEqual(self.calls, [])

    def test_write_permission_or_broadened_target_fails_closed(self):
        self.write_grant(write_enabled=True)
        with self.assertRaises(ConnectorError) as caught:
            self.call_read()
        self.assertEqual(caught.exception.code, "CAPABILITY_NOT_AUTHORIZED")
        self.write_grant(target={"repository": FULL_REPO, "ref": "main"})
        with self.assertRaises(ConnectorError) as caught:
            self.call_read()
        self.assertEqual(caught.exception.code, "CAPABILITY_NOT_AUTHORIZED")
        self.assertEqual(self.calls, [])

    def test_missing_bad_or_permissive_token_fails_closed(self):
        os.chmod(self.token, 0o644)
        with self.assertRaises(ConnectorError) as caught:
            self.call_read()
        self.assertEqual(caught.exception.code, "CREDENTIAL_PERMISSIONS_INVALID")
        self.token.write_text("")
        os.chmod(self.token, 0o600)
        with self.assertRaises(ConnectorError) as caught:
            self.call_read()
        self.assertEqual(caught.exception.code, "CREDENTIAL_FORMAT_INVALID")
        self.assertEqual(self.calls, [])

    def test_upstream_401_fails_closed_without_anonymous_fallback(self):
        def reject(request, timeout=8.0):
            self.calls.append(request)
            raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)
        with self.assertRaises(ConnectorError) as caught:
            read_hg2_ref(FULL_REPO, REF, token_path=self.token, registry_path=self.registry, opener=reject)
        self.assertEqual(caught.exception.code, "GITHUB_CREDENTIAL_REJECTED")
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn("test-token-not-real", str(caught.exception))

    def test_bad_upstream_schema_fails_closed(self):
        def wrong(request, timeout=8.0):
            self.calls.append(request)
            return FakeResponse(200, {"path": "wrong", "sha": "short"})
        with self.assertRaises(ConnectorError) as caught:
            read_hg2_ref(FULL_REPO, REF, token_path=self.token, registry_path=self.registry, opener=wrong)
        self.assertEqual(caught.exception.code, "GITHUB_RESPONSE_SCHEMA_INVALID")

    def test_rate_limit_fails_closed(self):
        for _ in range(connector.READ_RATE_LIMIT):
            self.call_read()
        with self.assertRaises(ConnectorError) as caught:
            self.call_read()
        self.assertEqual(caught.exception.code, "READ_RATE_LIMITED")
        self.assertEqual(caught.exception.status, 429)

    def test_result_contains_no_credential_or_authorization_header(self):
        result = self.call_read()
        encoded = json.dumps(result)
        self.assertNotIn("test-token-not-real", encoded)
        self.assertNotIn("Authorization", encoded)

    def test_request_verb_is_get_only(self):
        self.call_read()
        self.assertTrue(all(r.get_method() == "GET" for r in self.calls))
        self.assertFalse(any(r.get_method() in {"POST", "PATCH", "PUT", "DELETE"} for r in self.calls))


if __name__ == "__main__":
    unittest.main(verbosity=2)
