"""Sealed-principal dispatch for explicitly registered elevated operations.

Only bounded evidence-file reads are built in. Other elevated actions require an
explicit, fixed adapter registration; the registry never turns a capability name
into arbitrary shell, network, deployment, identity, or import behavior.
"""
from __future__ import annotations

import hashlib
import os
import stat
from typing import Any, Callable

from .auth import AuthenticatedPrincipal, CONFIGURABLE_SCOPES
from .evidence_verifier import EvidenceVerificationError, FilesystemEvidenceVerifier
from .policy import authorize_principal

ELEVATED_CAPABILITY_REGISTRY_V1 = "HG_ELEVATED_CAPABILITY_REGISTRY_V1"
ELEVATED_ACTIONS = frozenset({
    "file.read", "file.write", "shell.exec", "network.fetch", "deploy",
    "identity.change", "state.import", "provider.invoke",
})


class ElevatedCapabilityError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ElevatedCapabilityRegistry:
    """Explicit action-to-handler registry with exact-scope sealed-principal checks."""

    def __init__(self, *, principal: AuthenticatedPrincipal,
                 evidence_verifier: FilesystemEvidenceVerifier):
        if not isinstance(principal, AuthenticatedPrincipal) or not principal.principal_id:
            raise ElevatedCapabilityError("SEALED_PRINCIPAL_WITH_ID_REQUIRED")
        if not isinstance(evidence_verifier, FilesystemEvidenceVerifier):
            raise ElevatedCapabilityError("REAL_FILESYSTEM_EVIDENCE_VERIFIER_REQUIRED")
        self.principal = principal
        self.evidence_verifier = evidence_verifier
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "file.read": self._read_verified_evidence,
        }
        self._metadata: dict[str, dict[str, str]] = {
            "file.read": {
                "scope": "file.read",
                "side_effect_class": "LOCAL_READ_ONLY",
                "adapter_id": "hg.elevated_capability_registry.verified_file_read.v1",
            }
        }

    def register(self, action: str, *, scope: str, adapter_id: str,
                 side_effect_class: str,
                 handler: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        """Register a fixed host adapter; never accepts a prompt-derived command."""
        if action not in ELEVATED_ACTIONS or action == "file.read":
            raise ElevatedCapabilityError("ELEVATED_ACTION_INVALID_OR_BUILTIN")
        if scope != action or scope not in CONFIGURABLE_SCOPES:
            raise ElevatedCapabilityError("ELEVATED_SCOPE_MUST_MATCH_ACTION")
        if not isinstance(adapter_id, str) or not adapter_id.strip() or len(adapter_id) > 256:
            raise ElevatedCapabilityError("ELEVATED_ADAPTER_ID_INVALID")
        if side_effect_class not in {"LOCAL_READ_ONLY", "LOCAL_WRITE", "OUTBOUND_PROVIDER_CALL", "EXTERNAL_WRITE", "DESTRUCTIVE"}:
            raise ElevatedCapabilityError("ELEVATED_SIDE_EFFECT_CLASS_INVALID")
        if not callable(handler):
            raise ElevatedCapabilityError("ELEVATED_HANDLER_REQUIRED")
        if action in self._handlers:
            raise ElevatedCapabilityError("ELEVATED_HANDLER_ALREADY_REGISTERED")
        self._handlers[action] = handler
        self._metadata[action] = {
            "scope": scope, "side_effect_class": side_effect_class, "adapter_id": adapter_id,
        }

    def dispatch(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(action, str) or action not in ELEVATED_ACTIONS:
            raise ElevatedCapabilityError("ELEVATED_ACTION_NOT_ALLOWLISTED")
        decision = authorize_principal(action, self.principal)
        if not decision.allowed:
            raise ElevatedCapabilityError("ELEVATED_AUTHORIZATION_DENIED:" + decision.reason)
        handler = self._handlers.get(action)
        if handler is None:
            raise ElevatedCapabilityError("ELEVATED_HANDLER_NOT_REGISTERED")
        if type(payload) is not dict:
            raise ElevatedCapabilityError("ELEVATED_PAYLOAD_INVALID")
        result = handler(dict(payload))
        if type(result) is not dict or result.get("schema_version") != ELEVATED_CAPABILITY_REGISTRY_V1:
            raise ElevatedCapabilityError("ELEVATED_HANDLER_RESULT_INVALID")
        result["principal_id"] = self.principal.principal_id
        result["action"] = action
        result["adapter_id"] = self._metadata[action]["adapter_id"]
        result["side_effect_class"] = self._metadata[action]["side_effect_class"]
        return result

    def _read_verified_evidence(self, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) != {"reference", "expected_sha256"}:
            raise ElevatedCapabilityError("FILE_READ_PAYLOAD_INVALID")
        reference, expected = payload["reference"], payload["expected_sha256"]
        if not isinstance(reference, str) or not isinstance(expected, str):
            raise ElevatedCapabilityError("FILE_READ_REFERENCE_INVALID")
        try:
            path = self.evidence_verifier._resolve_reference(reference)
            info = path.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_size > self.evidence_verifier.max_bytes:
                raise ElevatedCapabilityError("FILE_READ_TARGET_INVALID")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(path, flags)
            try:
                opened = os.fstat(fd)
                if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                    raise ElevatedCapabilityError("FILE_READ_TARGET_CHANGED")
                chunks = []
                digest = hashlib.sha256()
                size = 0
                while True:
                    block = os.read(fd, 65536)
                    if not block:
                        break
                    size += len(block)
                    if size > self.evidence_verifier.max_bytes:
                        raise ElevatedCapabilityError("FILE_READ_SIZE_LIMIT_EXCEEDED")
                    digest.update(block)
                    chunks.append(block)
            finally:
                os.close(fd)
        except (OSError, EvidenceVerificationError) as exc:
            code = getattr(exc, "code", "FILE_READ_FAILED")
            raise ElevatedCapabilityError(code) from None
        actual = digest.hexdigest()
        if size != info.st_size:
            raise ElevatedCapabilityError("FILE_READ_CHANGED_DURING_READ")
        if not re_full_sha256(expected) or actual != expected:
            raise ElevatedCapabilityError("FILE_READ_DIGEST_MISMATCH")
        content = b"".join(chunks)
        return {
            "schema_version": ELEVATED_CAPABILITY_REGISTRY_V1,
            "status": "COMPLETE",
            "reference": reference,
            "sha256": actual,
            "size_bytes": size,
            "content_utf8": _decode_utf8(content),
            "content_base64": None if _is_utf8(content) else __import__("base64").b64encode(content).decode("ascii"),
            "semantic_truth_verified": False,
        }

    def runtime_domain_binding(self, *, source_revision: str):
        """Expose verified evidence reads through the existing HG runtime capability registry."""
        import re
        from .capability_registry import RuntimeDomainBinding
        from .contracts import BRAIN_WORKER_CONTEXT_V1, CAPABILITY_RESULT_V1, canonical_digest

        if not isinstance(source_revision, str) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", source_revision):
            raise ElevatedCapabilityError("RUNTIME_BINDING_SOURCE_REVISION_INVALID")

        def adapter(context: dict[str, Any]) -> dict[str, Any]:
            required = context.get("required_capabilities")
            payload = context.get("elevated_payload")
            base = {
                "schema_version": CAPABILITY_RESULT_V1,
                "request_id": context.get("request_id"),
                "correlation_id": context.get("correlation_id"),
                "source_revision": context.get("source_revision"),
                "evidence_refs": [],
            }
            if (context.get("schema_version") != BRAIN_WORKER_CONTEXT_V1
                    or required != ["evidence.verify"]
                    or context.get("source_revision") != source_revision
                    or type(payload) is not dict):
                return {**base, "status": "BLOCKED", "output_digest": None,
                        "error_code": "ELEVATED_RUNTIME_CONTEXT_INVALID"}
            try:
                result = self.dispatch("file.read", payload)
                reference = payload.get("reference")
                expected = payload.get("expected_sha256")
                if not isinstance(reference, str) or not isinstance(expected, str):
                    raise ElevatedCapabilityError("FILE_READ_REFERENCE_INVALID")
                scheme = reference.split(":", 1)[0]
                receipt_ok, receipt_ref = self.evidence_verifier.verify_reference_decision(
                    scheme + ":" + expected + "/" + reference.split(":", 1)[1]
                )
                if not receipt_ok:
                    raise ElevatedCapabilityError(receipt_ref)
                public_result = {"sha256": result["sha256"], "size_bytes": result["size_bytes"],
                                 "reference": reference, "receipt_ref": receipt_ref}
                return {**base, "status": "SUCCESS", "output_digest": canonical_digest(public_result),
                        "error_code": None, "evidence_refs": [receipt_ref]}
            except (ElevatedCapabilityError, EvidenceVerificationError, KeyError, ValueError) as exc:
                return {**base, "status": "BLOCKED", "output_digest": None,
                        "error_code": getattr(exc, "code", str(exc) or "ELEVATED_RUNTIME_OPERATION_BLOCKED")}

        return RuntimeDomainBinding(
            domain_id="security_verification",
            capability_ids=("evidence.verify",),
            implementation_id="hg.elevated_capability_registry.ElevatedCapabilityRegistry",
            adapter_version="1",
            input_contract=BRAIN_WORKER_CONTEXT_V1,
            output_contract=CAPABILITY_RESULT_V1,
            authority_contract="sealed_principal_exact_file.read_scope_plus_filesystem_evidence_verifier",
            side_effect_class="LOCAL_READ_ONLY",
            declared_timeout_seconds=5.0,
            hard_timeout_enforced=False,
            max_invocations_per_request=1,
            lifecycle_state="VERIFIED",
            source_revision=source_revision,
            evidence_verifier_id=self.evidence_verifier.verifier_id,
            adapter=adapter,
            readiness_check=lambda: bool(self.evidence_verifier.allowed_roots),
        )

    def verify_evidence(self, evidence_ids: list[str], context: dict[str, Any]) -> tuple[bool, str]:
        if type(evidence_ids) is not list or not evidence_ids or type(context) is not dict:
            return False, "EVIDENCE_INPUT_INVALID"
        receipts = []
        for reference in evidence_ids:
            ok, receipt = self.evidence_verifier.verify_reference_decision(reference)
            if not ok:
                return False, receipt
            receipts.append(receipt)
        digest = hashlib.sha256("\n".join(receipts).encode("utf-8")).hexdigest()
        return True, "evidence-receipts:" + digest

    def authorize_maep_action(self, action: str, context: dict[str, Any]) -> tuple[bool, str]:
        phase_id = context.get("phase_id") if type(context) is dict else None
        if not isinstance(phase_id, str) or action not in self._handlers:
            return False, "MAEP_ACTION_HANDLER_NOT_REGISTERED"
        decision = authorize_principal(action, self.principal)
        if not decision.allowed:
            return False, decision.reason
        return True, "principal:" + self.principal.principal_id + ":scope:" + action

    def maep_handler_registry(self, actions: dict[str, str]) -> dict[str, dict[str, Any]]:
        """Build fixed MAEP phase wrappers around registered operations only."""
        handlers = {}
        for phase_id, action in actions.items():
            if phase_id not in {"S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11", "S12", "S13"}:
                raise ElevatedCapabilityError("MAEP_PHASE_NOT_ALLOWLISTED")
            if action not in self._handlers:
                raise ElevatedCapabilityError("ELEVATED_HANDLER_NOT_REGISTERED")
            def prepare(state, context, _phase=phase_id):
                refs = state.get("EVIDENCE")
                if type(refs) is not list or not refs or any(not isinstance(ref, str) for ref in refs):
                    return {"passed": False, "evidence_ids": []}
                return {"passed": True, "evidence_ids": list(refs)}
            def run(state, context, _action=action):
                refs = state.get("EVIDENCE")
                if type(refs) is not list or not refs:
                    return {"status": "BLOCKED", "reason": "MAEP_EVIDENCE_INPUT_REQUIRED"}
                # The MAEP task schema carries evidence references; dispatch verifies the
                # exact bytes and digest before reporting completion. No writes are made.
                try:
                    receipts = []
                    for ref in refs:
                        expected, sep, relative = ref.split(":", 1)[1].partition("/") if ":" in ref else ("", "", "")
                        if not sep:
                            raise ElevatedCapabilityError("FILE_READ_EXPECTED_DIGEST_REQUIRED")
                        receipts.append(self.dispatch(_action, {"reference": "evidence:" + relative, "expected_sha256": expected}))
                except ElevatedCapabilityError as exc:
                    return {"status": "BLOCKED", "reason": exc.code, "side_effect_state": "NOT_PERFORMED"}
                return {"status": "COMPLETE", "exit_criteria": {"passed": True, "evidence_ids": list(refs)},
                        "evidence_ids": list(refs), "reason": "READ_ONLY_EVIDENCE_VERIFIED"}
            handlers[phase_id] = {"action": action, "prepare": prepare, "run": run}
        return handlers


def re_full_sha256(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def _is_utf8(value: bytes) -> bool:
    try:
        value.decode("utf-8", errors="strict")
        return True
    except UnicodeDecodeError:
        return False


def _decode_utf8(value: bytes) -> str | None:
    return value.decode("utf-8", errors="strict") if _is_utf8(value) else None
