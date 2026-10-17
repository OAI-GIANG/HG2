import tempfile, unittest
from hg.agent import HGAgent
from hg.auth import BearerAuthenticator
from hg.phone_runtime import PhoneRuntime
from hg.toolplane import ToolPlaneError


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
            auth = BearerAuthenticator("agent-token", {"provider.invoke"})
            agent = HGAgent(runtime, provider, authenticator=auth)
            self.assertIs(agent.tools.store, store)
            self.assertIs(agent.provider, provider)
            self.assertEqual(agent.ask("hello", authorization="Bearer agent-token"), "HG-agent-answer")
            self.assertEqual(provider.calls, 1)
            self.assertIn("provider.call.completed", [e["event_type"] for e in store.replay()])

    def test_agent_keeps_authentication_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = FakeProvider()
            auth = BearerAuthenticator("agent-token", {"provider.invoke"})
            agent = HGAgent(PhoneRuntime(state_dir=directory), provider, authenticator=auth)
            with self.assertRaises(ToolPlaneError) as ctx:
                agent.ask("hello")
            self.assertEqual(ctx.exception.code, "AUTHENTICATION_REQUIRED")
            self.assertEqual(provider.calls, 0)

    def test_agent_rejects_wrong_bearer_without_provider_call(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = FakeProvider()
            auth = BearerAuthenticator("agent-token", {"provider.invoke"})
            agent = HGAgent(PhoneRuntime(state_dir=directory), provider, authenticator=auth)
            with self.assertRaises(ToolPlaneError) as ctx:
                agent.ask("hello", authorization="Bearer wrong")
            self.assertEqual(ctx.exception.code, "AUTHENTICATION_REQUIRED")
            self.assertEqual(provider.calls, 0)


if __name__ == "__main__":
    unittest.main()
