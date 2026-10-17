"""Application entry point wiring phone-owned StateStore to provider and tools."""
from __future__ import annotations
from typing import Any
from .auth import BearerAuthenticator
from .phone_runtime import PhoneRuntime
from .provider import OpenAICompatibleProvider
from .toolplane import ToolPlane


class HGAgent:
    """HG AI entry point. Bearer credentials are validated by the auth module."""

    def __init__(self, runtime: PhoneRuntime | Any | None = None,
                 provider: OpenAICompatibleProvider | Any | None = None, *,
                 authenticator: BearerAuthenticator | None = None,
                 max_iterations: int = 4):
        self.runtime = runtime or PhoneRuntime()
        self.provider = provider or OpenAICompatibleProvider.from_env()
        self.authenticator = authenticator or BearerAuthenticator.from_env()
        self.tools = ToolPlane(
            self.runtime.store, self.provider,
            authenticator=self.authenticator, max_iterations=max_iterations,
        )

    def ask(self, prompt: str, *, authorization: str | None = None) -> str:
        return self.tools.ask(prompt, authorization=authorization)
