"""Application entry point wiring phone-owned StateStore to provider and tools."""
from __future__ import annotations
from typing import Any
from .auth import BearerAuthenticator
from .phone_runtime import PhoneRuntime
from .provider import OpenAICompatibleProvider
from .toolplane import ToolPlane
from .policy import authorize_service_mutation, authorize_principal, issue_mutation_permit
from .contracts import BRAIN_REQUEST_V1, BRAIN_REQUEST_AUDIT_V1, CAPABILITY_RESULT_V1, canonical_digest, validate_brain_request, validate_brain_request_audit, validate_capability_result
from .toolplane import ToolPlaneError
import uuid


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
            self.runtime, self.provider,
            authenticator=self.authenticator, max_iterations=max_iterations,
        )

    def _record_brain_event(self, principal, event_type: str, payload: dict[str, Any], *,
                            correlation_id: str, idempotency_key: str) -> None:
        actor_id = principal.principal_id
        action = "brain.request"
        authority_context = {"principal": actor_id, "scope": action}
        try:
            permit = issue_mutation_permit(
                action, principal, event_type=event_type, actor_id=actor_id, payload=payload,
                correlation_id=correlation_id, idempotency_key=idempotency_key,
                authority_context=authority_context,
            )
            self.runtime.store.emit(
                event_type, payload, correlation_id=correlation_id, actor_id=actor_id,
                authority_context=authority_context, idempotency_key=idempotency_key,
                mutation_permit=permit,
            )
        except Exception:
            raise ToolPlaneError("BRAIN_RESULT_AUDIT_UNAVAILABLE") from None

    def ask(self, prompt: str, *, authorization: str | None = None) -> str:
        principal = self.authenticator.authenticate(authorization)
        decision = authorize_service_mutation("brain.request", principal)
        if not decision.allowed:
            raise ToolPlaneError(decision.reason)
        if not authorize_principal("provider.invoke", principal).allowed:
            raise ToolPlaneError("ACTION_NOT_AUTHORIZED")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 16_000:
            raise ToolPlaneError("INVALID_PROMPT")
        request = validate_brain_request({
            "schema_version": BRAIN_REQUEST_V1,
            "request_id": uuid.uuid4().hex,
            "correlation_id": uuid.uuid4().hex,
            "goal": prompt,
            "constraints": {},
            "source_revision": "RUNTIME_REVISION_UNATTESTED",
        })
        request_id = request["request_id"]
        correlation_id = request["correlation_id"]
        accepted = validate_brain_request_audit({
            "schema_version": BRAIN_REQUEST_AUDIT_V1,
            "request_id": request_id,
            "correlation_id": correlation_id,
            "goal_sha256": canonical_digest({"goal": request["goal"]}),
            "constraints_sha256": canonical_digest(request["constraints"]),
            "source_revision": request["source_revision"],
            "status": "ACCEPTED",
        })
        self._record_brain_event(
            principal, "brain.request.accepted", accepted,
            correlation_id=correlation_id, idempotency_key="brain:accepted:" + request_id,
        )

        try:
            answer = self.tools.ask(
                request["goal"], authorization=authorization,
                request_id=request_id, correlation_id=correlation_id,
            )
            result = validate_capability_result({
                "schema_version": CAPABILITY_RESULT_V1,
                "request_id": request_id,
                "correlation_id": correlation_id,
                "status": "RESPONSE_ONLY",
                "output_digest": canonical_digest({"answer": answer}),
                "error_code": "PROVIDER_RESPONSE_ONLY_NOT_EXECUTION_PROOF",
                "evidence_refs": [],
                "source_revision": request["source_revision"],
            }, expected_request_id=request_id, expected_correlation_id=correlation_id,
               expected_source_revision=request["source_revision"])
        except ToolPlaneError as error:
            result = validate_capability_result({
                "schema_version": CAPABILITY_RESULT_V1,
                "request_id": request_id,
                "correlation_id": correlation_id,
                "status": "FAIL",
                "output_digest": None,
                "error_code": error.code,
                "evidence_refs": [],
                "source_revision": request["source_revision"],
            }, expected_request_id=request_id, expected_correlation_id=correlation_id,
               expected_source_revision=request["source_revision"])
            self._record_brain_event(
                principal, "brain.request.completed", result,
                correlation_id=correlation_id, idempotency_key="brain:completed:" + request_id,
            )
            raise

        self._record_brain_event(
            principal, "brain.request.completed", result,
            correlation_id=correlation_id, idempotency_key="brain:completed:" + request_id,
        )
        return answer
