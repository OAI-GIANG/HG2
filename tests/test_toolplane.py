import json, tempfile, unittest
from unittest.mock import patch
from hg.auth import BearerAuthenticator
from hg.phone_runtime import PhoneRuntime
from hg.policy import authorize, authorize_principal
from hg.history import StateStore
from hg.provider import ProviderError
from hg.toolplane import ToolPlane, ToolPlaneError
from tests._support import authorized_audit_emit


class FakeProvider:
    def __init__(self, responses): self.responses, self.calls = list(responses), []
    def complete(self, messages, tools=None):
        self.calls.append({"messages": json.loads(json.dumps(messages)), "tools": tools})
        if not self.responses: raise AssertionError("unexpected provider call")
        response = self.responses.pop(0)
        if isinstance(response, Exception): raise response
        return response


def tool_call(name, args="{}", call_id="call-1"):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": args}}


class ToolPlaneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = PhoneRuntime(state_dir=self.temp.name)
        self.store = self.runtime.store
        self.header = "Bearer hg-feature-test-token"
        self.authenticator = BearerAuthenticator("hg-feature-test-token", {"provider.invoke", "session.create", "brain.request"}, principal_id="alice")
        self.principal = self.authenticator.authenticate(self.header)

    def plane(self, provider, **kwargs):
        return ToolPlane(self.runtime, provider, authenticator=self.authenticator, **kwargs)

    def test_provider_policy_is_authenticated_and_shell_remains_forbidden(self):
        self.assertEqual(authorize("provider.invoke").reason, "SEALED_PRINCIPAL_REQUIRED")
        self.assertFalse(authorize("provider.invoke", authenticated=True).allowed)
        self.assertTrue(authorize_principal("provider.invoke", self.principal).allowed)
        self.assertFalse(authorize_principal("shell.exec", self.principal).allowed)
        self.assertFalse(authorize_principal("provider.invoke", object()).allowed)

    def test_tool_plane_requires_runtime_composition_root(self):
        with self.assertRaises(ToolPlaneError) as ctx:
            ToolPlane(self.store, FakeProvider([]), authenticator=self.authenticator)
        self.assertEqual(ctx.exception.code, "RUNTIME_INTERFACE_REQUIRED")

    def test_direct_toolplane_entry_cannot_bypass_brain_authority(self):
        auth = BearerAuthenticator("provider-only", {"provider.invoke"}, principal_id="alice")
        provider = FakeProvider([{"content": "must not run"}])
        plane = ToolPlane(self.runtime, provider, authenticator=auth)
        with self.assertRaises(ToolPlaneError) as ctx:
            plane.ask("goal", authorization="Bearer provider-only")
        self.assertEqual(ctx.exception.code, "ACTION_NOT_AUTHORIZED")
        self.assertEqual(provider.calls, [])

    def test_direct_private_tool_dispatch_cannot_bypass_brain_gate(self):
        auth = BearerAuthenticator(
            "capability-only", {"provider.invoke", "session.create"}, principal_id="alice"
        )
        principal = auth.authenticate("Bearer capability-only")
        with self.assertRaises(ToolPlaneError) as ctx:
            self.plane(FakeProvider([]))._run_tool("session.create", {}, principal=principal)
        self.assertEqual(ctx.exception.code, "ACTION_NOT_AUTHORIZED")
        self.assertEqual(
            [event["event_type"] for event in self.store.replay()].count("session.created"), 0
        )

    def test_provider_requires_authenticated_caller(self):
        provider = FakeProvider([{"content": "should not run"}])
        with self.assertRaises(ToolPlaneError) as ctx:
            self.plane(provider).ask("hello")
        self.assertEqual(ctx.exception.code, "AUTHENTICATION_REQUIRED")
        self.assertEqual(provider.calls, [])

    def test_invalid_prompt_is_rejected_before_provider_call(self):
        provider = FakeProvider([{"content": "should not run"}])
        plane = self.plane(provider)
        for prompt in ("", "   ", "x" * 16001):
            with self.subTest(prompt_len=len(prompt)), self.assertRaises(ToolPlaneError):
                plane.ask(prompt, authorization=self.header)
        self.assertEqual(provider.calls, [])

    def test_plain_answer_and_redacted_audit(self):
        provider = FakeProvider([{"content": "answer"}])
        prompt = "private prompt text"
        self.assertEqual(self.plane(provider).ask(prompt, authorization=self.header), "answer")
        serialized = json.dumps(self.store.replay())
        self.assertNotIn(prompt, serialized)
        self.assertNotIn(self.header, serialized)
        self.assertIn("provider.call.started", serialized)
        self.assertIn("provider.call.completed", serialized)
        self.assertIn("prompt_sha256", serialized)

    def test_tool_call_round_trip_and_schema_isolation(self):
        provider = FakeProvider([{"content": None, "tool_calls": [tool_call("identity.get")]},
                                 {"content": "verified answer"}])
        self.assertEqual(self.plane(provider).ask("what is your identity?", authorization=self.header), "verified answer")
        tool_message = [m for m in provider.calls[1]["messages"] if m["role"] == "tool"][0]
        result = json.loads(tool_message["content"])
        self.assertEqual(result["product"], "HG")
        self.assertEqual(result["architecture"], "PHONE_PRIMARY_V1")
        self.assertEqual(provider.calls[0]["tools"][0]["function"]["name"], "identity.get")
        serialized = json.dumps(self.store.replay())
        self.assertIn("tool.call.started", serialized)
        self.assertIn("tool.call.completed", serialized)
        self.assertNotIn('"arguments"', serialized)

    def test_tool_direct_entry_requires_authentication(self):
        with self.assertRaises(ToolPlaneError) as ctx:
            self.plane(FakeProvider([]))._run_tool("identity.get", {}, principal=None)
        self.assertEqual(ctx.exception.code, "AUTHENTICATION_REQUIRED")

    def test_history_summary_sanitizes_unknown_event_type(self):
        authorized_audit_emit(self.store, "PRIVATE_EVENT_NAME_MUST_NOT_LEAK", {"secret_value": "private payload"})
        result = self.plane(FakeProvider([]))._run_tool("history.summary", {}, principal=self.principal)
        encoded = json.dumps(result)
        self.assertIn("OTHER", encoded)
        self.assertNotIn("PRIVATE_EVENT_NAME_MUST_NOT_LEAK", encoded)
        self.assertNotIn("private payload", encoded)

    def test_recent_history_omits_event_payload(self):
        authorized_audit_emit(self.store, "private.example", {"secret_value": "DO-NOT-RETURN"})
        result = self.plane(FakeProvider([]))._run_tool("history.recent", {"limit": 5}, principal=self.principal)
        self.assertTrue(any(event["event_type"] == "OTHER" for event in result))
        self.assertNotIn("private.example", json.dumps(result))
        self.assertNotIn("payload", json.dumps(result))
        self.assertNotIn("DO-NOT-RETURN", json.dumps(result))

    def test_unknown_or_dangerous_tools_are_denied(self):
        plane = self.plane(FakeProvider([]))
        for name in ("shell.exec", "file.read", "network.fetch", "deploy", "made.up"):
            with self.subTest(name=name):
                with self.assertRaises(ToolPlaneError) as ctx:
                    plane._run_tool(name, {}, principal=self.principal)
                self.assertEqual(ctx.exception.code, "TOOL_NOT_ALLOWLISTED")

    def test_duplicate_json_keys_are_denied(self):
        provider = FakeProvider([{"content": None, "tool_calls": [tool_call("history.recent", '{"limit":5,"limit":6}')]}])
        with self.assertRaises(ToolPlaneError) as ctx:
            self.plane(provider).ask("list events", authorization=self.header)
        self.assertEqual(ctx.exception.code, "INVALID_TOOL_ARGUMENTS")

    def test_nonstandard_json_constants_are_denied(self):
        provider = FakeProvider([{"content": None, "tool_calls": [tool_call("history.recent", '{"limit":NaN}')]}])
        with self.assertRaises(ToolPlaneError) as ctx:
            self.plane(provider).ask("list events", authorization=self.header)
        self.assertEqual(ctx.exception.code, "INVALID_TOOL_ARGUMENTS")

    def test_unrecognized_tool_name_is_not_written_to_audit(self):
        provider = FakeProvider([{"content": None, "tool_calls": [tool_call("TOP-SECRET-UNIQUE")]},
                                 {"content": "tool denied"}])
        self.assertEqual(self.plane(provider).ask("test", authorization=self.header), "tool denied")
        audit = json.dumps(self.store.replay())
        self.assertIn("UNRECOGNIZED", audit)
        self.assertNotIn("TOP-SECRET-UNIQUE", audit)

    def test_bad_arguments_are_denied_before_tool_execution(self):
        plane = self.plane(FakeProvider([]))
        for args in ({"path": "/etc/passwd"}, {"limit": True}, {"limit": 21}, {"limit": "3"}):
            with self.subTest(args=args):
                with self.assertRaises(ToolPlaneError) as ctx:
                    plane._run_tool("history.recent", args, principal=self.principal)
                self.assertEqual(ctx.exception.code, "INVALID_TOOL_ARGUMENTS")

    def test_session_create_requires_separate_scope(self):
        only_provider = BearerAuthenticator("scoped-token", {"provider.invoke"})
        principal = only_provider.authenticate("Bearer scoped-token")
        plane = ToolPlane(self.runtime, FakeProvider([]), authenticator=only_provider)
        with self.assertRaises(ToolPlaneError) as ctx:
            plane._run_tool("session.create", {}, principal=principal)
        self.assertEqual(ctx.exception.code, "ACTION_NOT_AUTHORIZED")

        explicit = BearerAuthenticator("session-token", {"provider.invoke", "session.create", "brain.request"}, principal_id="alice")
        session_principal = explicit.authenticate("Bearer session-token")
        session = self.plane(FakeProvider([]))._run_tool("session.create", {}, principal=session_principal)
        self.assertTrue(session["session_id"])
        self.assertEqual(session["product"], "HG")
        self.assertEqual([event["event_type"] for event in self.store.replay()].count("session.created"), 1)

    def test_repeated_tool_cycle_is_stopped(self):
        same_call = {"content": None, "tool_calls": [tool_call("identity.get")]}
        provider = FakeProvider([same_call, same_call])
        result = self.plane(provider, max_iterations=4).ask("repeat", authorization=self.header)
        self.assertEqual(result, "HG stopped a repeated tool-call cycle.")
        self.assertEqual(len(provider.calls), 2)
        self.assertIn("tool.loop_blocked", json.dumps(self.store.replay()))

    def test_iteration_limit_is_bounded(self):
        provider = FakeProvider([{"content": None, "tool_calls": [tool_call("identity.get", call_id="a")]},
                                 {"content": None, "tool_calls": [tool_call("history.verify", call_id="b")]},
                                 {"content": "not reached"}])
        result = self.plane(provider, max_iterations=2).ask("bounded", authorization=self.header)
        self.assertIn("iteration limit", result)
        self.assertEqual(len(provider.calls), 2)

    def test_provider_errors_are_sanitized_and_audited(self):
        provider = FakeProvider([ProviderError("MISSING_API_KEY")])
        with self.assertRaises(ToolPlaneError) as ctx:
            self.plane(provider).ask("private prompt", authorization=self.header)
        self.assertEqual(ctx.exception.code, "MISSING_API_KEY")
        audit = json.dumps(self.store.replay())
        self.assertIn('"error_code": "MISSING_API_KEY"', audit)
        self.assertNotIn("private prompt", audit)

    def test_unrecognized_provider_error_code_is_not_echoed(self):
        provider = FakeProvider([ProviderError("DO-NOT-LEAK-THIS")])
        with self.assertRaises(ToolPlaneError) as ctx:
            self.plane(provider).ask("private prompt", authorization=self.header)
        self.assertEqual(ctx.exception.code, "PROVIDER_ERROR")
        self.assertNotIn("DO-NOT-LEAK-THIS", json.dumps(self.store.replay()))

    def test_tool_audit_failure_stops_mutation_before_tool_starts(self):
        provider = FakeProvider([{"content": None, "tool_calls": [tool_call("session.create")]},
                                 {"content": "should not be reached"}])
        original_emit = self.store.emit
        def fail_on_tool_start(event_type, payload, **kwargs):
            if event_type == "tool.call.started":
                raise OSError("PRIVATE_AUDIT_PATH")
            return original_emit(event_type, payload, **kwargs)
        with patch.object(self.store, "emit", side_effect=fail_on_tool_start):
            with self.assertRaises(ToolPlaneError) as ctx:
                self.plane(provider).ask("create a session", authorization=self.header)
        self.assertEqual(ctx.exception.code, "AUDIT_UNAVAILABLE")
        self.assertNotIn("session.created", [event["event_type"] for event in self.store.replay()])
        self.assertNotIn("PRIVATE_AUDIT_PATH", json.dumps(self.store.replay()))

    def test_audit_failure_fails_closed_before_provider_call(self):
        provider = FakeProvider([{"content": "no"}])
        with patch.object(self.store, "emit", side_effect=OSError("private filesystem detail")):
            with self.assertRaises(ToolPlaneError) as ctx:
                self.plane(provider).ask("hello", authorization=self.header)
        self.assertEqual(ctx.exception.code, "AUDIT_UNAVAILABLE")
        self.assertEqual(provider.calls, [])

    def test_iteration_and_tool_limits_validate(self):
        with self.assertRaises(ToolPlaneError): ToolPlane(self.store, FakeProvider([]), authenticator=self.authenticator, max_iterations=0)
        with self.assertRaises(ToolPlaneError): ToolPlane(self.store, FakeProvider([]), authenticator=self.authenticator, max_tool_calls_per_turn=5)
        calls = [tool_call("identity.get", call_id=str(i)) for i in range(5)]
        with self.assertRaises(ToolPlaneError) as ctx:
            self.plane(FakeProvider([{"content": None, "tool_calls": calls}])).ask("too many", authorization=self.header)
        self.assertEqual(ctx.exception.code, "TOOL_CALL_LIMIT_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
