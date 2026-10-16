"""Mocked contract tests for the bounded DeepSeek Task Draft Provider.

No real credential or external HTTP request is used by these tests. All provider responses
are treated as untrusted drafts and pass the local contract validator.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

from hg.agentic_intelligence import compile_request
from hg.model_provider import DeepSeekTaskDraftProvider, ModelProviderError
from hg.task_compiler import compile_natural_language
from hg.task_contract import SCHEMA_VERSION, contract_digest, validate_contract
from tests.test_task_contract import make_contract


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def read(self, limit=-1):
        if limit < 0:
            return self._body
        return self._body[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def valid_api_response(contract: dict, *, finish_reason: str = "stop", model: str = "deepseek-flash") -> bytes:
    return json.dumps({
        "id": "test-response-id",
        "model": model,
        "choices": [{
            "index": 0,
            "finish_reason": finish_reason,
            "message": {"role": "assistant", "content": json.dumps(contract, separators=(",", ":"))},
        }],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }).encode("utf-8")


def provider(**overrides) -> DeepSeekTaskDraftProvider:
    values = {
        "api_key": "TEST-ONLY-NOT-A-REAL-KEY",
        "base_url": "https://api.deepseek.com",
        "model_id": "deepseek-flash",
    }
    values.update(overrides)
    return DeepSeekTaskDraftProvider(**values)


class ProviderConfigTests(unittest.TestCase):
    def test_from_environment_requires_supported_model(self):
        with self.assertRaises(ModelProviderError) as ctx:
            DeepSeekTaskDraftProvider.from_environment({
                "HG_MODEL_API_KEY": "TEST-ONLY",
                "HG_MODEL_BASE_URL": "https://api.deepseek.com",
                "HG_MODEL_ID": "deepseek-chat",
            })
        self.assertEqual(ctx.exception.code, "MODEL_PROVIDER_MODEL_UNSUPPORTED")

    def test_http_remote_endpoint_rejected(self):
        with self.assertRaises(ModelProviderError) as ctx:
            provider(base_url="http://api.deepseek.com")
        self.assertEqual(ctx.exception.code, "MODEL_PROVIDER_ENDPOINT_REJECTED")

    def test_untrusted_endpoint_rejected(self):
        for url in (
            "https://attacker.example",
            "https://user:password@api.deepseek.com",
            "https://api.deepseek.com?token=leak",
            "https://api.deepseek.com/#fragment",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ModelProviderError) as ctx:
                    provider(base_url=url)
                self.assertEqual(ctx.exception.code, "MODEL_PROVIDER_ENDPOINT_REJECTED")

    def test_secure_env_file_loader_reads_only_operator_config(self):
        with tempfile.TemporaryDirectory(prefix="hg-model-config-") as directory:
            path = Path(directory) / "secret.env"
            path.write_text(
                "HG_MODEL_API_KEY=TEST-ONLY-NOT-A-REAL-KEY\n"
                "HG_MODEL_BASE_URL=https://api.deepseek.com\n"
                "HG_MODEL_ID=deepseek-flash\n",
                encoding="utf-8",
            )
            os.chmod(path, 0o600)
            draft_provider = DeepSeekTaskDraftProvider.from_env_file(path)
            self.assertEqual(draft_provider.model_id, "deepseek-flash")
            self.assertEqual(draft_provider.timeout_seconds, 20)

    def test_env_file_with_loose_permissions_rejected(self):
        with tempfile.TemporaryDirectory(prefix="hg-model-config-") as directory:
            path = Path(directory) / "secret.env"
            path.write_text(
                "HG_MODEL_API_KEY=TEST-ONLY\n"
                "HG_MODEL_BASE_URL=https://api.deepseek.com\n"
                "HG_MODEL_ID=deepseek-flash\n",
                encoding="utf-8",
            )
            os.chmod(path, 0o644)
            with self.assertRaises(ModelProviderError) as ctx:
                DeepSeekTaskDraftProvider.from_env_file(path)
            self.assertEqual(ctx.exception.code, "MODEL_PROVIDER_CONFIG_PERMISSIONS")

    def test_invalid_timeout_config_normalized(self):
        with self.assertRaises(ModelProviderError) as ctx:
            DeepSeekTaskDraftProvider.from_environment({
                "HG_MODEL_API_KEY": "TEST-ONLY",
                "HG_MODEL_BASE_URL": "https://api.deepseek.com",
                "HG_MODEL_ID": "deepseek-flash",
                "HG_MODEL_TIMEOUT_SECONDS": "not-an-int",
            })
        self.assertEqual(ctx.exception.code, "MODEL_PROVIDER_CONFIG_INVALID")


class ProviderRequestTests(unittest.TestCase):
    def test_contract_response_locally_validated_and_metadata_replaced(self):
        draft = make_contract("model:replace")
        original_digest = draft["contract_digest"]
        fake = FakeResponse(valid_api_response(draft))
        with patch("hg.model_provider.urlopen", return_value=fake) as mocked:
            contract = provider()( "Check a bounded read-only health status." )
        validate_contract(contract)
        self.assertEqual(contract["schema_version"], SCHEMA_VERSION)
        self.assertTrue(contract["task_id"].startswith("task:nl:"))
        self.assertEqual(contract["created_by"], "hg-task-compiler:model-draft")
        self.assertNotEqual(contract["task_id"], "model:replace")
        self.assertNotEqual(contract["contract_digest"], original_digest)
        req = mocked.call_args.args[0]
        self.assertEqual(req.full_url, "https://api.deepseek.com/chat/completions")
        self.assertEqual(req.get_header("Authorization"), "Bearer TEST-ONLY-NOT-A-REAL-KEY")
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body["model"], "deepseek-flash")
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(body["stream"], False)
        self.assertIn("health.read", body["messages"][0]["content"])

    def test_agentic_intelligence_facade_returns_validated_contract(self):
        draft = make_contract("model:facade")
        plan = compile_request(
            "Draft a read-only task contract for a health check.",
            draft_provider=lambda request: draft,
        )
        self.assertEqual(plan["state"], "VALIDATED")
        self.assertEqual(plan["task_contract"]["task_id"], "model:facade")
        self.assertFalse(plan["executable"])
        validate_contract(plan["task_contract"])

    def test_compiler_can_use_provider_but_output_stays_non_executable(self):
        draft = make_contract("model:compile")
        with patch("hg.model_provider.urlopen", return_value=FakeResponse(valid_api_response(draft))):
            plan = compile_natural_language(
                "Create a read-only task that summarizes a local health result.",
                draft_provider=provider(),
            )
        self.assertEqual(plan["state"], "VALIDATED")
        self.assertFalse(plan["executable"])
        self.assertEqual(plan["draft_provider_state"], "UNTRUSTED_PROPOSAL_VALIDATED")
        self.assertIn("source_request_digest", plan)
        self.assertIn("task_contract", plan)
        self.assertEqual(plan["task_contract"]["schema_version"], SCHEMA_VERSION)

    def test_approval_reference_hallucination_rejected(self):
        draft = make_contract("model:bad-approval")
        draft["approval_ref"] = "approval:invented"
        with patch("hg.model_provider.urlopen", return_value=FakeResponse(valid_api_response(draft))):
            with self.assertRaises(ModelProviderError) as ctx:
                provider()("Do an operation that requires approval.")
        self.assertEqual(ctx.exception.code, "MODEL_DRAFT_APPROVAL_REFERENCE_REJECTED")

    def test_invalid_contract_rejected_locally(self):
        draft = make_contract("model:bad")
        draft.pop("objective")
        with patch("hg.model_provider.urlopen", return_value=FakeResponse(valid_api_response(draft))):
            with self.assertRaises(ModelProviderError) as ctx:
                provider()("Invalid model draft test")
        self.assertEqual(ctx.exception.code, "MODEL_DRAFT_REJECTED")

    def test_truncated_response_never_compiles(self):
        draft = make_contract("model:cutoff")
        with patch("hg.model_provider.urlopen", return_value=FakeResponse(valid_api_response(draft, finish_reason="length"))):
            with self.assertRaises(ModelProviderError) as ctx:
                provider()("A response that was cut off")
        self.assertEqual(ctx.exception.code, "MODEL_RESPONSE_INCOMPLETE")

    def test_duplicate_json_keys_rejected(self):
        response = {
            "id": "test-id",
            "model": "deepseek-flash",
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": '{"task_id":"A","task_id":"B"}'},
            }],
        }
        with patch("hg.model_provider.urlopen", return_value=FakeResponse(json.dumps(response).encode())):
            with self.assertRaises(ModelProviderError) as ctx:
                provider()("duplicate key test")
        self.assertEqual(ctx.exception.code, "MODEL_RESPONSE_INVALID_CONTRACT_JSON")

    def test_http_error_does_not_leak_response_or_credentials(self):
        sentinel = "DO-NOT-LEAK-TEST-SECRET"
        error = HTTPError("https://api.deepseek.com/chat/completions", 401, sentinel,
                          hdrs=None, fp=BytesIO(sentinel.encode()))
        with patch("hg.model_provider.urlopen", side_effect=error):
            with self.assertRaises(ModelProviderError) as ctx:
                provider(api_key=sentinel)("test request")
        self.assertEqual(ctx.exception.code, "MODEL_PROVIDER_HTTP_ERROR")
        self.assertNotIn(sentinel, str(ctx.exception))
        self.assertNotIn(sentinel, repr(ctx.exception))

    def test_request_size_bounded_before_network(self):
        provider_instance = provider()
        with patch("hg.model_provider.urlopen") as mocked:
            with self.assertRaises(ModelProviderError) as ctx:
                provider_instance("x" * 16_385)
        self.assertEqual(ctx.exception.code, "MODEL_REQUEST_TOO_LARGE")
        mocked.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
