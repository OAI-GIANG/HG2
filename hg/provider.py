"""Bounded OpenAI-compatible model provider with fail-closed configuration.

Credentials are read as data from an explicit environment variable or a small,
allowlisted config file. This module never logs prompts, response bodies or keys.
"""
from __future__ import annotations
import json, os, urllib.error, urllib.request
from pathlib import Path
from urllib.parse import urlsplit

MAX_RESPONSE_BYTES = 1_048_576
MAX_REQUEST_BYTES = 262_144
MAX_TIMEOUT_SECONDS = 60.0
CONFIG_KEYS = frozenset({"HG_MODEL_BASE_URL", "HG_MODEL_ID", "HG_MODEL_API_KEY"})


class ProviderError(RuntimeError):
    """A safe, non-sensitive provider error code."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _parse_config_file(path: str) -> dict[str, str]:
    """Read only known KEY=value fields; never source or execute the file."""
    result: dict[str, str] = {}
    try:
        config_path = Path(os.path.expanduser(path))
        if config_path.stat().st_size > 65_536:
            return result
        lines = config_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return result
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, separator, value = line.partition("=")
        if not separator or key.strip() not in CONFIG_KEYS:
            continue
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        result[key] = value
    return result


def _no_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _reject_json_constant(value):
    raise ValueError("NON_STANDARD_JSON_CONSTANT")


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Do not forward bearer credentials through provider-controlled redirects."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _validate_base_url(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ProviderError("INVALID_PROVIDER_URL")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
    except ValueError:
        raise ProviderError("INVALID_PROVIDER_URL") from None
    if (parsed.scheme != "https" or not hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment):
        raise ProviderError("INVALID_PROVIDER_URL")
    return value.rstrip("/")


class OpenAICompatibleProvider:
    """Small standard-library Chat Completions client; no credential in repr."""
    def __init__(self, base_url: str, model: str, api_key: str, *,
                 timeout: float = 20.0, max_response_bytes: int = MAX_RESPONSE_BYTES):
        self.base_url = _validate_base_url(base_url)
        if not isinstance(model, str) or not model.strip() or len(model) > 128:
            raise ProviderError("INVALID_MODEL_ID")
        self.model = model.strip()
        self.api_key = api_key if isinstance(api_key, str) else ""
        if "\r" in self.api_key or "\n" in self.api_key:
            raise ProviderError("INVALID_API_KEY_FORMAT")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ProviderError("INVALID_TIMEOUT")
        if timeout <= 0 or timeout > MAX_TIMEOUT_SECONDS:
            raise ProviderError("INVALID_TIMEOUT")
        if (isinstance(max_response_bytes, bool) or not isinstance(max_response_bytes, int)
                or max_response_bytes < 1024 or max_response_bytes > MAX_RESPONSE_BYTES):
            raise ProviderError("INVALID_RESPONSE_LIMIT")
        self.timeout = float(timeout)
        self.max_response_bytes = max_response_bytes

    @classmethod
    def from_env(cls) -> "OpenAICompatibleProvider":
        path = os.environ.get("HG_PROVIDER_CONFIG_FILE", "~/.config/hg/secret.env")
        values = _parse_config_file(path)
        base_url = os.environ.get("HG_MODEL_BASE_URL") or values.get("HG_MODEL_BASE_URL", "https://api.deepseek.com")
        model = os.environ.get("HG_MODEL_ID") or values.get("HG_MODEL_ID", "deepseek-chat")
        api_key = os.environ.get("HG_MODEL_API_KEY") or values.get("HG_MODEL_API_KEY", "")
        return cls(base_url, model, api_key)

    def __repr__(self) -> str:
        return f"OpenAICompatibleProvider(model={self.model!r}, base_url={self.base_url!r}, configured={bool(self.api_key)})"

    def _open(self, request):
        opener = urllib.request.build_opener(_NoRedirectHandler())
        return opener.open(request, timeout=self.timeout)

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        if not self.api_key:
            raise ProviderError("MISSING_API_KEY")
        if not isinstance(messages, list) or not messages or len(messages) > 128:
            raise ProviderError("INVALID_MESSAGES")
        payload = {"model": self.model, "messages": messages}
        if tools is not None:
            if not isinstance(tools, list) or len(tools) > 32:
                raise ProviderError("INVALID_TOOL_SCHEMAS")
            payload["tools"], payload["tool_choice"] = tools, "auto"
        try:
            raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError, UnicodeEncodeError):
            raise ProviderError("INVALID_REQUEST_PAYLOAD") from None
        if len(raw) > MAX_REQUEST_BYTES:
            raise ProviderError("REQUEST_TOO_LARGE")
        request = urllib.request.Request(
            self.base_url + "/chat/completions", data=raw, method="POST",
            headers={"Authorization": "Bearer " + self.api_key,
                     "Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with self._open(request) as response:
                body = response.read(self.max_response_bytes + 1)
        except urllib.error.HTTPError as error:
            try:
                error.close()
            except Exception:
                pass
            raise ProviderError("PROVIDER_HTTP_ERROR") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ProviderError("PROVIDER_NETWORK_ERROR") from None
        except Exception:
            raise ProviderError("PROVIDER_TRANSPORT_ERROR") from None
        if len(body) > self.max_response_bytes:
            raise ProviderError("PROVIDER_RESPONSE_TOO_LARGE")
        try:
            decoded = json.loads(body.decode("utf-8"), object_pairs_hook=_no_duplicate_json_keys,
                                  parse_constant=_reject_json_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise ProviderError("INVALID_PROVIDER_RESPONSE") from None
        if not isinstance(decoded, dict):
            raise ProviderError("INVALID_PROVIDER_RESPONSE")
        choices = decoded.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderError("INVALID_PROVIDER_RESPONSE")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ProviderError("INVALID_PROVIDER_RESPONSE")
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise ProviderError("INVALID_PROVIDER_RESPONSE")
        if len(content or "") > 32768:
            raise ProviderError("PROVIDER_CONTENT_TOO_LARGE")
        if message.get("tool_calls", []) is not None and not isinstance(message.get("tool_calls", []), list):
            raise ProviderError("INVALID_PROVIDER_RESPONSE")
        return dict(message)
