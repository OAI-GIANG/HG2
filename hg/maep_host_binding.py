"""Fail-closed MAEP host binding for explicitly registered phase handlers.

This is an integration seam, not a production route. The caller must provide a
canonical workflow adapter, authenticated sealed principal, real authorization
and evidence-verification callbacks, and a static handler registry. No handler
is derived from task prompts or arbitrary input.
"""
from __future__ import annotations

from typing import Any, Callable

from .auth import CONFIGURABLE_SCOPES
from .maep import MaepOrchestrator, PHASE_IDS
from .workflow_store_adapter import CanonicalWorkflowAdapter


class MaepHostBindingError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class MaepHostBinding:
    """Bind MAEP phases to a static handler registry and real host policy callbacks."""

    def __init__(self, adapter: CanonicalWorkflowAdapter, *,
                 phase_actions: dict[str, str],
                 handler_registry: dict[str, dict[str, Any]],
                 action_scopes: dict[str, str],
                 authorizer: Callable[[str, dict[str, Any]], tuple[bool, str]],
                 evidence_verifier: Callable[[list[str], dict[str, Any]], tuple[bool, str]]):
        if not isinstance(adapter, CanonicalWorkflowAdapter):
            raise MaepHostBindingError("MAEP_CANONICAL_WORKFLOW_ADAPTER_REQUIRED")
        if not callable(authorizer):
            raise MaepHostBindingError("MAEP_REAL_AUTHORIZER_REQUIRED")
        if not callable(evidence_verifier):
            raise MaepHostBindingError("MAEP_REAL_EVIDENCE_VERIFIER_REQUIRED")
        if type(phase_actions) is not dict or not phase_actions:
            raise MaepHostBindingError("MAEP_PHASE_ALLOWLIST_REQUIRED")
        if set(phase_actions) - set(PHASE_IDS):
            raise MaepHostBindingError("MAEP_PHASE_ALLOWLIST_INVALID")
        if type(handler_registry) is not dict or type(action_scopes) is not dict:
            raise MaepHostBindingError("MAEP_HANDLER_REGISTRY_INVALID")
        principal = adapter.principal
        handlers: dict[str, dict[str, Any]] = {}
        for phase_id, action in phase_actions.items():
            if not isinstance(action, str) or not action.strip():
                raise MaepHostBindingError("MAEP_ACTION_ALLOWLIST_INVALID")
            scope = action_scopes.get(action)
            if not isinstance(scope, str) or scope not in CONFIGURABLE_SCOPES:
                raise MaepHostBindingError("MAEP_ACTION_SCOPE_NOT_CONFIGURED")
            if not principal.allows(scope):
                raise MaepHostBindingError("MAEP_ACTION_SCOPE_NOT_GRANTED")
            spec = handler_registry.get(action)
            if (type(spec) is not dict or spec.get("action") != action
                    or not callable(spec.get("prepare")) or not callable(spec.get("run"))):
                raise MaepHostBindingError("MAEP_REGISTERED_HANDLER_INVALID")
            handlers[phase_id] = {"action": action, "prepare": spec["prepare"], "run": spec["run"]}
        self.adapter = adapter
        self.principal = principal
        self.phase_actions = dict(phase_actions)
        self.action_scopes = dict(action_scopes)
        self.handlers = handlers
        self._authorizer = authorizer
        self._evidence_verifier = evidence_verifier

    def _authorize(self, action: str, context: dict[str, Any]) -> tuple[bool, str]:
        phase_id = context.get("phase_id") if isinstance(context, dict) else None
        if (phase_id not in self.phase_actions or self.phase_actions[phase_id] != action
                or not self.principal.allows(self.action_scopes.get(action, ""))):
            return False, "MAEP_HOST_ACTION_NOT_ALLOWLISTED"
        try:
            decision = self._authorizer(action, dict(context))
        except Exception:
            return False, "MAEP_HOST_AUTHORIZER_ERROR"
        if (type(decision) is not tuple or len(decision) != 2
                or type(decision[0]) is not bool
                or not isinstance(decision[1], str) or not decision[1].strip()):
            return False, "MAEP_HOST_AUTHORIZER_INVALID_RESPONSE"
        return decision

    def _verify_evidence(self, evidence_ids: list[str], context: dict[str, Any]) -> tuple[bool, str]:
        try:
            decision = self._evidence_verifier(list(evidence_ids), dict(context))
        except Exception:
            return False, "MAEP_HOST_EVIDENCE_VERIFIER_ERROR"
        if (type(decision) is not tuple or len(decision) != 2
                or type(decision[0]) is not bool
                or not isinstance(decision[1], str) or not decision[1].strip()):
            return False, "MAEP_HOST_EVIDENCE_VERIFIER_INVALID_RESPONSE"
        return decision

    def build_orchestrator(self) -> MaepOrchestrator:
        """Use the adapter's existing SQLiteStateStore; never open a second store."""
        return self.adapter.maep_orchestrator(
            handlers=self.handlers,
            authorizer=self._authorize,
            evidence_verifier=self._verify_evidence,
        )
