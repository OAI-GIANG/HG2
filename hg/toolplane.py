"""HG-native tool plane: fixed allowlist, bounded orchestration, hash-only audit."""
from __future__ import annotations
import hashlib
from copy import deepcopy
from collections import Counter
from typing import Any
from .auth import AuthenticatedPrincipal, BearerAuthenticator
from .contracts import ContractError, canonical_digest, canonical_json, parse_json_no_duplicate_keys
from .policy import authorize_principal
from .identity import identity
from .provider import OpenAICompatibleProvider, ProviderError

MAX_PROMPT_CHARS = 16_000
MAX_TOOL_CALLS_PER_TURN = 4
MAX_TOOL_ARGUMENTS_CHARS = 8_192
SAFE_PROVIDER_ERRORS = frozenset({
    "INVALID_PROVIDER_URL", "INVALID_MODEL_ID", "INVALID_API_KEY_FORMAT", "INVALID_TIMEOUT",
    "INVALID_RESPONSE_LIMIT", "MISSING_API_KEY", "INVALID_MESSAGES", "INVALID_TOOL_SCHEMAS",
    "INVALID_REQUEST_PAYLOAD", "REQUEST_TOO_LARGE", "PROVIDER_HTTP_ERROR",
    "PROVIDER_NETWORK_ERROR", "PROVIDER_TRANSPORT_ERROR", "PROVIDER_RESPONSE_TOO_LARGE",
    "INVALID_PROVIDER_RESPONSE", "PROVIDER_CONTENT_TOO_LARGE",
})
ALLOWED_TOOL_NAMES = frozenset({"identity.get", "history.verify", "history.summary", "history.recent", "session.create"})
SAFE_EVENT_TYPES = frozenset({
    "hg.genesis", "session.created", "provider.call.started", "provider.call.completed",
    "tool.call.started", "tool.call.completed", "tool.loop_blocked", "tool.iteration_limit",
})
SYSTEM_MESSAGE = (
    "You are HG. Use only provided tools and returned evidence. Never claim an action occurred "
    "unless a tool result confirms it. Do not request secrets. Built-in tools cannot execute "
    "arbitrary commands or access arbitrary files."
)


class ToolPlaneError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _safe_event_type(value: Any) -> str:
    return value if isinstance(value, str) and value in SAFE_EVENT_TYPES else "OTHER"


_TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "identity.get",
     "description": "Return fixed HG product identity and architecture.",
     "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {"name": "history.verify",
     "description": "Verify local append-only history without returning event payloads.",
     "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {"name": "history.summary",
     "description": "Return aggregate history counts and checkpoint, without event payloads.",
     "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {"name": "history.recent",
     "description": "Return bounded recent event metadata; payloads are omitted.",
     "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 20}},
                    "additionalProperties": False}}},
    {"type": "function", "function": {"name": "session.create",
     "description": "Create one HG session; requires authenticated caller authorization.",
     "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
]


class ToolPlane:
    def __init__(self, runtime, provider: OpenAICompatibleProvider | Any, *,
                 authenticator: BearerAuthenticator | None = None,
                 max_iterations: int = 4,
                 max_tool_calls_per_turn: int = MAX_TOOL_CALLS_PER_TURN):
        if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or not 1 <= max_iterations <= 6:
            raise ToolPlaneError("INVALID_ITERATION_LIMIT")
        if (isinstance(max_tool_calls_per_turn, bool) or not isinstance(max_tool_calls_per_turn, int)
                or not 1 <= max_tool_calls_per_turn <= MAX_TOOL_CALLS_PER_TURN):
            raise ToolPlaneError("INVALID_TOOL_CALL_LIMIT")
        if not callable(getattr(runtime, "start_session", None)) or not hasattr(runtime, "store"):
            raise ToolPlaneError("RUNTIME_INTERFACE_REQUIRED")
        self.runtime, self.store, self.provider = runtime, runtime.store, provider
        self.authenticator = authenticator or BearerAuthenticator.from_env()
        self.max_iterations = max_iterations
        self.max_tool_calls_per_turn = max_tool_calls_per_turn

    @property
    def tool_schemas(self) -> list[dict]:
        return deepcopy(_TOOL_SCHEMAS)

    def _audit(self, event_type: str, payload: dict) -> None:
        try:
            self.store.emit(event_type, payload)
        except Exception:
            raise ToolPlaneError("AUDIT_UNAVAILABLE") from None

    def _run_tool(self, name: str, args: dict, *, principal: AuthenticatedPrincipal | None) -> dict | list:
        caller_decision = authorize_principal("provider.invoke", principal)
        if not caller_decision.allowed:
            raise ToolPlaneError(caller_decision.reason)
        expected = {"identity.get": set(), "history.verify": set(), "history.summary": set(),
                    "history.recent": {"limit"}, "session.create": set()}
        if name not in expected:
            raise ToolPlaneError("TOOL_NOT_ALLOWLISTED")
        if not isinstance(args, dict) or set(args) - expected[name]:
            raise ToolPlaneError("INVALID_TOOL_ARGUMENTS")
        if name != "history.recent" and args:
            raise ToolPlaneError("INVALID_TOOL_ARGUMENTS")
        if name == "history.recent":
            limit = args.get("limit", 10)
            if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
                raise ToolPlaneError("INVALID_TOOL_ARGUMENTS")
        if name == "session.create":
            decision = authorize_principal("session.create", principal)
            if not decision.allowed:
                raise ToolPlaneError(decision.reason)
            try:
                return self.runtime.start_session(principal=principal)
            except PermissionError as error:
                code = str(error) if str(error) in {
                    "AUTHENTICATION_REQUIRED", "ACTION_NOT_AUTHORIZED", "EXPLICITLY_FORBIDDEN",
                    "NOT_ALLOWLISTED", "AMBIGUOUS_SESSION_CREDENTIAL",
                } else "SESSION_CREATION_DENIED"
                raise ToolPlaneError(code) from None
            except Exception:
                raise ToolPlaneError("SESSION_CREATION_FAILED") from None
        if name == "identity.get":
            return identity()
        if name == "history.verify":
            result = self.store.verify()
            return {"ok": bool(result.get("ok")), "events": int(result.get("events", 0)),
                    "reason": str(result.get("reason", "UNKNOWN")), "head_hash": result.get("head_hash")}
        events = self.store.replay()
        if name == "history.summary":
            counts = Counter(_safe_event_type(event.get("event_type")) for event in events if isinstance(event, dict))
            checkpoint = self.store.audit_export()
            return {"events": len(events), "last_seq": checkpoint.get("last_seq", 0),
                    "head_hash": checkpoint.get("head_hash"), "event_type_counts": dict(sorted(counts.items()))}
        limit = args.get("limit", 10)
        return [{"seq": event.get("seq"), "event_type": _safe_event_type(event.get("event_type")),
                 "recorded_at": event.get("recorded_at"), "record_hash": event.get("record_hash")}
                for event in events[-limit:]]

    def ask(self, prompt: str, *, authorization: str | None = None) -> str:
        principal = self.authenticator.authenticate(authorization)
        decision = authorize_principal("provider.invoke", principal)
        if not decision.allowed:
            raise ToolPlaneError(decision.reason)
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARS:
            raise ToolPlaneError("INVALID_PROMPT")
        messages = [{"role": "system", "content": SYSTEM_MESSAGE}, {"role": "user", "content": prompt}]
        previous_signature = None
        for iteration in range(self.max_iterations):
            self._audit("provider.call.started", {
                "iteration": iteration + 1,
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            })
            try:
                message = self.provider.complete(messages, self.tool_schemas)
            except ProviderError as error:
                raw_code = getattr(error, "code", None)
                code = raw_code if isinstance(raw_code, str) and raw_code in SAFE_PROVIDER_ERRORS else "PROVIDER_ERROR"
                self._audit("provider.call.completed", {
                    "iteration": iteration + 1, "outcome": "error", "error_code": code})
                raise ToolPlaneError(code) from None
            except Exception:
                self._audit("provider.call.completed", {
                    "iteration": iteration + 1, "outcome": "error", "error_code": "PROVIDER_ERROR"})
                raise ToolPlaneError("PROVIDER_ERROR") from None
            if not isinstance(message, dict):
                self._audit("provider.call.completed", {
                    "iteration": iteration + 1, "outcome": "error",
                    "error_code": "INVALID_PROVIDER_RESPONSE"})
                raise ToolPlaneError("INVALID_PROVIDER_RESPONSE")
            calls = message.get("tool_calls") or []
            content = message.get("content") or ""
            if not isinstance(content, str):
                self._audit("provider.call.completed", {
                    "iteration": iteration + 1, "outcome": "error",
                    "error_code": "INVALID_PROVIDER_CONTENT"})
                raise ToolPlaneError("INVALID_PROVIDER_CONTENT")
            if not calls:
                self._audit("provider.call.completed", {
                    "iteration": iteration + 1, "outcome": "ok", "tool_call_count": 0,
                    "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()})
                return content
            if not isinstance(calls, list) or len(calls) > self.max_tool_calls_per_turn:
                raise ToolPlaneError("TOOL_CALL_LIMIT_EXCEEDED")
            parsed_calls = []
            for call in calls:
                if not isinstance(call, dict):
                    raise ToolPlaneError("INVALID_TOOL_CALL")
                call_id, function = call.get("id"), call.get("function")
                if not isinstance(call_id, str) or not call_id or len(call_id) > 128:
                    raise ToolPlaneError("INVALID_TOOL_CALL")
                if not isinstance(function, dict) or not isinstance(function.get("name"), str):
                    raise ToolPlaneError("INVALID_TOOL_CALL")
                if not function["name"] or len(function["name"]) > 64:
                    raise ToolPlaneError("INVALID_TOOL_CALL")
                raw_args = function.get("arguments", "{}")
                if not isinstance(raw_args, str) or len(raw_args) > MAX_TOOL_ARGUMENTS_CHARS:
                    raise ToolPlaneError("INVALID_TOOL_ARGUMENTS")
                try:
                    args = parse_json_no_duplicate_keys(raw_args)
                except ContractError:
                    raise ToolPlaneError("INVALID_TOOL_ARGUMENTS") from None
                if not isinstance(args, dict):
                    raise ToolPlaneError("INVALID_TOOL_ARGUMENTS")
                parsed_calls.append((call_id, function["name"], args))
            signature = canonical_digest([{"name": name, "args": args} for _, name, args in parsed_calls])
            if signature == previous_signature:
                self._audit("tool.loop_blocked", {
                    "iteration": iteration + 1, "signature_sha256": signature,
                    "outcome": "repeated_tool_call_sequence"})
                return "HG stopped a repeated tool-call cycle."
            previous_signature = signature
            messages.append({"role": "assistant", "content": message.get("content"), "tool_calls": calls})
            for call_id, name, args in parsed_calls:
                args_sha = canonical_digest(args)
                audit_name = name if name in ALLOWED_TOOL_NAMES else "UNRECOGNIZED"
                self._audit("tool.call.started", {
                    "iteration": iteration + 1, "tool": audit_name, "args_sha256": args_sha})
                try:
                    result = self._run_tool(name, args, principal=principal)
                except ToolPlaneError as error:
                    self._audit("tool.call.completed", {
                        "iteration": iteration + 1, "tool": audit_name, "args_sha256": args_sha,
                        "outcome": "denied_or_error", "error_code": error.code})
                    result = {"ok": False, "error": error.code}
                except Exception:
                    self._audit("tool.call.completed", {
                        "iteration": iteration + 1, "tool": audit_name, "args_sha256": args_sha,
                        "outcome": "error", "error_code": "TOOL_ERROR"})
                    result = {"ok": False, "error": "TOOL_ERROR"}
                outcome = "error" if isinstance(result, dict) and result.get("ok") is False else "ok"
                self._audit("tool.call.completed", {
                    "iteration": iteration + 1, "tool": audit_name, "args_sha256": args_sha,
                    "result_sha256": canonical_digest(result), "outcome": outcome})
                messages.append({"role": "tool", "tool_call_id": call_id, "content": canonical_json(result)})
        self._audit("tool.iteration_limit", {"max_iterations": self.max_iterations, "outcome": "limit_reached"})
        return "HG stopped tool execution because the iteration limit was reached."
