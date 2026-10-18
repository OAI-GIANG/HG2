import tempfile, unittest
from hg.agent import HGAgent
from hg.auth import BearerAuthenticator
from hg.phone_runtime import PhoneRuntime
from hg.toolplane import ToolPlaneError
from hg.provider import ProviderError


class FakeProvider:
    def __init__(self): self.calls = 0
    def complete(self, messages, tools=None):
        self.calls += 1
        return {"content": "HG-agent-answer"}


class AgentTests(unittest.TestCase):
    def test_agent_wires_store_provider_and_toolplane(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime, provider = PhoneRuntime(state_dir=directory), FakeProvider()
            store = runtime.store
            auth = BearerAuthenticator("agent-token", {"provider.invoke", "brain.request"}, principal_id="alice")
            agent = HGAgent(runtime, provider, authenticator=auth)
            self.assertIs(agent.tools.store, store)
            self.assertIs(agent.provider, provider)
            self.assertEqual(agent.ask("hello", authorization="Bearer agent-token"), "HG-agent-answer")
            self.assertEqual(provider.calls, 1)
            events = store.replay()
            names = [e["event_type"] for e in events]
            self.assertIn("provider.call.completed", names)
            self.assertLess(names.index("brain.request.accepted"), names.index("provider.call.started"))
            self.assertLess(names.index("provider.call.completed"), names.index("brain.request.completed"))
            accepted = next(e for e in events if e["event_type"] == "brain.request.accepted")
            completed = next(e for e in events if e["event_type"] == "brain.request.completed")
            self.assertEqual(accepted["correlation_id"], completed["correlation_id"])
            self.assertEqual(accepted["payload"]["request_id"], completed["payload"]["request_id"])
            self.assertEqual(completed["payload"]["status"], "RESPONSE_ONLY")
            self.assertEqual(completed["payload"]["error_code"], "PROVIDER_RESPONSE_ONLY_NOT_EXECUTION_PROOF")
            self.assertEqual(completed["payload"]["evidence_refs"], [])
            self.assertTrue(store.verify()["ok"])

    def test_agent_is_the_only_public_goal_entry_and_uses_one_toolplane(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime, provider = PhoneRuntime(state_dir=directory), FakeProvider()
            auth = BearerAuthenticator("brain-token", {"provider.invoke", "brain.request"}, principal_id="alice")
            agent = HGAgent(runtime, provider, authenticator=auth)
            self.assertIs(agent.tools.runtime, runtime)
            self.assertEqual(agent.ask("goal", authorization="Bearer brain-token"), "HG-agent-answer")
            self.assertEqual(provider.calls, 1)
            events = runtime.store.replay()
            self.assertEqual(sum(1 for event in events if event["event_type"] == "provider.call.started"), 1)
            accepted = next(event for event in events if event["event_type"] == "brain.request.accepted")
            completed = next(event for event in events if event["event_type"] == "brain.request.completed")
            self.assertEqual(accepted["payload"]["request_id"], completed["payload"]["request_id"])
            self.assertEqual(accepted["correlation_id"], completed["correlation_id"])

    def test_agent_records_failed_provider_result_as_fail_not_success(self):
        class BrokenProvider:
            def complete(self, messages, tools=None):
                raise ProviderError("MISSING_API_KEY")

        with tempfile.TemporaryDirectory() as directory:
            runtime = PhoneRuntime(state_dir=directory)
            auth = BearerAuthenticator("fail-token", {"provider.invoke", "brain.request"}, principal_id="alice")
            agent = HGAgent(runtime, BrokenProvider(), authenticator=auth)
            with self.assertRaises(ToolPlaneError) as ctx:
                agent.ask("failure", authorization="Bearer fail-token")
            self.assertEqual(ctx.exception.code, "MISSING_API_KEY")
            events = runtime.store.replay()
            completed = [event for event in events if event["event_type"] == "brain.request.completed"]
            self.assertEqual(len(completed), 1)
            self.assertEqual(completed[0]["payload"]["status"], "FAIL")
            self.assertEqual(completed[0]["payload"]["error_code"], "MISSING_API_KEY")
            self.assertIsNone(completed[0]["payload"]["output_digest"])
            self.assertTrue(runtime.store.verify()["ok"])

    def test_agent_keeps_authentication_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = FakeProvider()
            auth = BearerAuthenticator("agent-token", {"provider.invoke", "brain.request"}, principal_id="alice")
            agent = HGAgent(PhoneRuntime(state_dir=directory), provider, authenticator=auth)
            with self.assertRaises(ToolPlaneError) as ctx:
                agent.ask("hello")
            self.assertEqual(ctx.exception.code, "AUTHENTICATION_REQUIRED")
            self.assertEqual(provider.calls, 0)

    def test_agent_rejects_wrong_bearer_without_provider_call(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = FakeProvider()
            auth = BearerAuthenticator("agent-token", {"provider.invoke", "brain.request"}, principal_id="alice")
            agent = HGAgent(PhoneRuntime(state_dir=directory), provider, authenticator=auth)
            with self.assertRaises(ToolPlaneError) as ctx:
                agent.ask("hello", authorization="Bearer wrong")
            self.assertEqual(ctx.exception.code, "AUTHENTICATION_REQUIRED")
            self.assertEqual(provider.calls, 0)


if __name__ == "__main__":
    unittest.main()
