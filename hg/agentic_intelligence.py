"""Explicit local entrypoint for HG native task-contract drafting.

Calling compile_request sends the supplied request to the configured DeepSeek provider.
The returned Task Contract is validated locally and stays non-executable. No task body,
shell command, URL, capability adapter, or side effect is executed by this module.
"""
from __future__ import annotations

from os import PathLike
from typing import Any, Callable

from .model_provider import DeepSeekTaskDraftProvider, ModelProviderError
from .task_compiler import CompileError, compile_natural_language


def compile_request(
    request_text: str,
    *,
    draft_provider: Callable[[str], dict[str, Any]] | None = None,
    config_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Draft a complete task contract and return a non-executable validated plan.

    If no provider is injected, load the operator-managed mode-0600 HG provider config.
    A live provider call occurs only when this function is explicitly invoked.
    """
    if draft_provider is None:
        try:
            draft_provider = DeepSeekTaskDraftProvider.from_env_file(config_path)
        except ModelProviderError as exc:
            raise CompileError("TASK_DRAFT_PROVIDER_UNAVAILABLE", "$.provider", exc.code) from None
    return compile_natural_language(request_text, draft_provider=draft_provider)
