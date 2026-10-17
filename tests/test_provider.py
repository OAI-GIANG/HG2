import io, json, os, tempfile, unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request
from hg.provider import OpenAICompatibleProvider, ProviderError, _NoRedirectHandler


class FakeResponse:
    def __init__(self, body): self.body = io.BytesIO(body)
    def __enter__(self): return self
    def __exit__(self, *args): self.body.close()
    def read(self, size=-1): return self.body.read(size)


def response_body(message):
    return json.dumps({"choices": [{"message": message}]}).encode("utf-8")


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider = OpenAICompatibleProvider("https://example.invalid/v1", "test-model", "TEST-SECRET-KEY")

    def test_sends_chat_completion_and_tool_schemas(self):
        with patch.object(self.provider, "_open", return_value=FakeResponse(response_body({"content": "hello"}))) as call:
            result = self.provider.complete([{"role": "user", "content": "test"}],
                                            [{"type": "function", "function": {"name": "identity.get"}}])
        self.assertEqual(result["content"], "hello")
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.invalid/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer TEST-SECRET-KEY")
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertEqual(payload["tools"][0]["function"]["name"], "identity.get")

    def test_missing_key_fails_without_network(self):
        provider = OpenAICompatibleProvider("https://example.invalid", "model", "")
        with patch.object(provider, "_open") as call:
            with self.assertRaises(ProviderError) as ctx:
                provider.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(ctx.exception.code, "MISSING_API_KEY")
        call.assert_not_called()

    def test_rejects_http_and_credential_urls(self):
        for url in ("http://example.com", "file:///tmp/x", "https://user:pass@example.com",
                    "https://example.com?key=x", "https://example.com#fragment", "https://[broken"):
            with self.subTest(url=url):
                with self.assertRaises(ProviderError) as ctx:
                    OpenAICompatibleProvider(url, "model", "key")
                self.assertEqual(ctx.exception.code, "INVALID_PROVIDER_URL")

    def test_redirect_handler_never_forwards_bearer_credentials(self):
        handler = _NoRedirectHandler()
        request = Request("https://provider.example/chat/completions")
        result = handler.redirect_request(request, None, 302, "Found", {}, "https://other.example/steal")
        self.assertIsNone(result)

    def test_http_error_is_redacted(self):
        error = HTTPError("https://example.invalid/v1/chat/completions", 401, "Unauthorized", {}, io.BytesIO(b"TEST-SECRET-KEY"))
        with patch.object(self.provider, "_open", side_effect=error):
            with self.assertRaises(ProviderError) as ctx:
                self.provider.complete([{"role": "user", "content": "private prompt"}])
        self.assertEqual(ctx.exception.code, "PROVIDER_HTTP_ERROR")
        self.assertNotIn("TEST-SECRET-KEY", str(ctx.exception))
        self.assertNotIn("private prompt", str(ctx.exception))

    def test_request_size_is_bounded_before_network(self):
        with patch.object(self.provider, "_open") as call:
            with self.assertRaises(ProviderError) as ctx:
                self.provider.complete([{"role": "user", "content": "x" * 270_000}])
        self.assertEqual(ctx.exception.code, "REQUEST_TOO_LARGE")
        call.assert_not_called()

    def test_response_size_is_bounded(self):
        provider = OpenAICompatibleProvider("https://example.invalid", "model", "key", max_response_bytes=1024)
        with patch.object(provider, "_open", return_value=FakeResponse(b"x" * 1025)):
            with self.assertRaises(ProviderError) as ctx:
                provider.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(ctx.exception.code, "PROVIDER_RESPONSE_TOO_LARGE")

    def test_invalid_response_shape_is_rejected(self):
        with patch.object(self.provider, "_open", return_value=FakeResponse(b'{"choices":[]}')):
            with self.assertRaises(ProviderError) as ctx:
                self.provider.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(ctx.exception.code, "INVALID_PROVIDER_RESPONSE")

    def test_duplicate_and_nonstandard_response_json_is_rejected(self):
        for body in (b'{"choices":[],"choices":[]}', b'{"choices":NaN}'):
            with self.subTest(body=body), patch.object(self.provider, "_open", return_value=FakeResponse(body)):
                with self.assertRaises(ProviderError) as ctx:
                    self.provider.complete([{"role": "user", "content": "hi"}])
                self.assertEqual(ctx.exception.code, "INVALID_PROVIDER_RESPONSE")

    def test_repr_never_contains_api_key(self):
        self.assertNotIn("TEST-SECRET-KEY", repr(self.provider))
        self.assertIn("configured=True", repr(self.provider))

    def test_safe_data_only_config_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "secret.env")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write("# values are data only\nHG_MODEL_BASE_URL=https://example.invalid/v1\nHG_MODEL_ID=fixture-model\nHG_MODEL_API_KEY=NEVER-PRINT-THIS\nSHELL_COMMAND=touch /tmp/should-not-run\n")
            with patch.dict(os.environ, {"HG_PROVIDER_CONFIG_FILE": path}, clear=True):
                provider = OpenAICompatibleProvider.from_env()
            self.assertEqual(provider.model, "fixture-model")
            self.assertEqual(provider.api_key, "NEVER-PRINT-THIS")
            self.assertNotIn("NEVER-PRINT-THIS", repr(provider))
            self.assertFalse(os.path.exists("/tmp/should-not-run"))


if __name__ == "__main__":
    unittest.main()
