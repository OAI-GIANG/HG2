"""Sealed-principal dispatch for explicitly registered elevated operations.

Only bounded evidence-file reads are built in. Other elevated actions require an
explicit, fixed adapter registration; the registry never turns a capability name
into arbitrary shell, network, deployment, identity, or import behavior.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import stat
from pathlib import Path
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
                 evidence_verifier: FilesystemEvidenceVerifier,
                 write_roots: tuple[str | os.PathLike[str], ...] | list[str | os.PathLike[str]] = (),
                 max_write_bytes: int = 1_000_000):
        if not isinstance(principal, AuthenticatedPrincipal) or not principal.principal_id:
            raise ElevatedCapabilityError("SEALED_PRINCIPAL_WITH_ID_REQUIRED")
        if not isinstance(evidence_verifier, FilesystemEvidenceVerifier):
            raise ElevatedCapabilityError("REAL_FILESYSTEM_EVIDENCE_VERIFIER_REQUIRED")
        if isinstance(max_write_bytes, bool) or not isinstance(max_write_bytes, int) or not 1 <= max_write_bytes <= 1_000_000:
            raise ElevatedCapabilityError("FILE_WRITE_MAX_BYTES_INVALID")
        if type(write_roots) not in (tuple, list) or len(write_roots) > 32:
            raise ElevatedCapabilityError("FILE_WRITE_ROOTS_INVALID")
        roots = []
        for supplied in write_roots:
            if not isinstance(supplied, (str, os.PathLike)) or not os.fspath(supplied):
                raise ElevatedCapabilityError("FILE_WRITE_ROOT_INVALID")
            path = Path(supplied)
            if path.is_symlink():
                raise ElevatedCapabilityError("FILE_WRITE_ROOT_SYMLINK_BLOCKED")
            try:
                resolved = path.resolve(strict=True)
            except OSError:
                raise ElevatedCapabilityError("FILE_WRITE_ROOT_NOT_FOUND") from None
            if not resolved.is_dir():
                raise ElevatedCapabilityError("FILE_WRITE_ROOT_NOT_DIRECTORY")
            roots.append(resolved)
        if len(set(roots)) != len(roots):
            raise ElevatedCapabilityError("FILE_WRITE_ROOT_DUPLICATE")
        self.principal = principal
        self.evidence_verifier = evidence_verifier
        self.write_roots = tuple(roots)
        self.max_write_bytes = max_write_bytes
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "file.read": self._read_verified_evidence,
            "file.write": self._write_confined_file,
        }
        self._metadata: dict[str, dict[str, str]] = {
            "file.read": {
                "scope": "file.read",
                "side_effect_class": "LOCAL_READ_ONLY",
                "adapter_id": "hg.elevated_capability_registry.verified_file_read.v1",
            },
            "file.write": {
                "scope": "file.write",
                "side_effect_class": "LOCAL_WRITE",
                "adapter_id": "hg.elevated_capability_registry.create_only_file_write.v1",
            }
        }

    def register(self, action: str, *, scope: str, adapter_id: str,
                 side_effect_class: str,
                 handler: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        """Register a fixed host adapter; never accepts a prompt-derived command."""
        if action not in ELEVATED_ACTIONS or action in {"file.read", "file.write", "shell.exec"}:
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

    def _write_confined_file(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Atomically create a new file under a trusted write root; never overwrite."""
        if set(payload) not in ({"relative_path", "content_utf8", "expected_sha256"},
                                {"relative_path", "content_base64", "expected_sha256"}):
            raise ElevatedCapabilityError("FILE_WRITE_PAYLOAD_INVALID")
        if not self.write_roots:
            raise ElevatedCapabilityError("FILE_WRITE_ROOTS_NOT_CONFIGURED")
        relative = payload.get("relative_path")
        expected = payload.get("expected_sha256")
        if not isinstance(relative, str) or not relative or "\x00" in relative or "\\" in relative:
            raise ElevatedCapabilityError("FILE_WRITE_PATH_INVALID")
        candidate_path = __import__("pathlib").PurePosixPath(relative)
        if candidate_path.is_absolute() or any(part in {"", ".", ".."} for part in candidate_path.parts):
            raise ElevatedCapabilityError("FILE_WRITE_PATH_TRAVERSAL_BLOCKED")
        if not re_full_sha256(expected):
            raise ElevatedCapabilityError("FILE_WRITE_DIGEST_INVALID")
        if "content_utf8" in payload:
            if not isinstance(payload["content_utf8"], str):
                raise ElevatedCapabilityError("FILE_WRITE_CONTENT_INVALID")
            content = payload["content_utf8"].encode("utf-8")
        else:
            encoded = payload["content_base64"]
            if not isinstance(encoded, str):
                raise ElevatedCapabilityError("FILE_WRITE_CONTENT_INVALID")
            try:
                content = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError):
                raise ElevatedCapabilityError("FILE_WRITE_BASE64_INVALID") from None
        if len(content) > self.max_write_bytes:
            raise ElevatedCapabilityError("FILE_WRITE_SIZE_LIMIT_EXCEEDED")
        digest = hashlib.sha256(content).hexdigest()
        if digest != expected:
            raise ElevatedCapabilityError("FILE_WRITE_DIGEST_MISMATCH")

        target = None
        for root in self.write_roots:
            current = root
            safe = True
            for part in candidate_path.parts[:-1]:
                current = current / part
                if current.is_symlink() or not current.is_dir():
                    safe = False
                    break
            if not safe:
                continue
            candidate = current / candidate_path.parts[-1]
            try:
                if os.path.commonpath((str(root), str(candidate.parent.resolve(strict=True)))) != str(root):
                    continue
            except (OSError, ValueError):
                continue
            if target is not None:
                raise ElevatedCapabilityError("FILE_WRITE_ROOT_AMBIGUOUS")
            target = candidate
        if target is None:
            raise ElevatedCapabilityError("FILE_WRITE_PARENT_NOT_ALLOWLISTED")
        if target.is_symlink():
            raise ElevatedCapabilityError("FILE_WRITE_TARGET_SYMLINK_BLOCKED")
        if target.exists():
            try:
                existing_info = target.stat(follow_symlinks=False)
                if not stat.S_ISREG(existing_info.st_mode) or existing_info.st_size > self.max_write_bytes:
                    raise ElevatedCapabilityError("FILE_WRITE_TARGET_CONFLICT")
                existing = target.read_bytes()
            except ElevatedCapabilityError:
                raise
            except OSError:
                raise ElevatedCapabilityError("FILE_WRITE_EXISTING_TARGET_UNREADABLE") from None
            existing_digest = hashlib.sha256(existing).hexdigest()
            if existing_digest == digest and len(existing) == len(content):
                return {"schema_version": ELEVATED_CAPABILITY_REGISTRY_V1, "status": "IDEMPOTENT_NOOP",
                        "relative_path": relative, "sha256": digest, "size_bytes": len(content),
                        "created": False, "idempotent": True}
            raise ElevatedCapabilityError("FILE_WRITE_TARGET_CONFLICT")

        temp_path = target.parent / (".hg-write-" + secrets.token_hex(12))
        fd = None
        try:
            fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            self._write_temp_bytes(fd, content)
            os.fsync(fd)
            os.close(fd)
            fd = None
            try:
                self._link_no_replace(temp_path, target)
            except FileExistsError:
                if target.is_symlink() or not target.is_file():
                    raise ElevatedCapabilityError("FILE_WRITE_TARGET_CONFLICT") from None
                existing_info = target.stat(follow_symlinks=False)
                if not stat.S_ISREG(existing_info.st_mode) or existing_info.st_size > self.max_write_bytes:
                    raise ElevatedCapabilityError("FILE_WRITE_TARGET_CONFLICT") from None
                existing_digest = hashlib.sha256(target.read_bytes()).hexdigest()
                if existing_digest != digest:
                    raise ElevatedCapabilityError("FILE_WRITE_TARGET_CONFLICT") from None
                return {"schema_version": ELEVATED_CAPABILITY_REGISTRY_V1, "status": "IDEMPOTENT_NOOP",
                        "relative_path": relative, "sha256": digest, "size_bytes": len(content),
                        "created": False, "idempotent": True}
            dir_fd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except ElevatedCapabilityError:
            raise
        except OSError as exc:
            raise ElevatedCapabilityError("FILE_WRITE_ATOMIC_CREATE_FAILED:" + type(exc).__name__) from None
        finally:
            if fd is not None:
                os.close(fd)
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
        return {"schema_version": ELEVATED_CAPABILITY_REGISTRY_V1, "status": "COMPLETE",
                "relative_path": relative, "sha256": digest, "size_bytes": len(content),
                "created": True, "idempotent": False}

    @staticmethod
    def _link_no_replace(source, destination) -> None:
        # Android may omit os.link and deny link(2); use atomic renameat2(NO_REPLACE).
        import ctypes
        import errno
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is not None:
            renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
            renameat2.restype = ctypes.c_int
            result = renameat2(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
        else:
            syscall = libc.syscall
            syscall.argtypes = (ctypes.c_long, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
            syscall.restype = ctypes.c_long
            # __NR_renameat2 on Linux aarch64; fail closed on other architectures.
            machine = __import__("platform").machine().lower()
            if machine not in {"aarch64", "arm64"}:
                raise OSError(errno.ENOSYS, "renameat2 unavailable")
            result = syscall(276, -100, os.fsencode(source), -100, os.fsencode(destination), 1)
        if result == 0:
            return
        code = ctypes.get_errno()
        if code == errno.EEXIST:
            raise FileExistsError(code, os.strerror(code), str(destination))
        raise OSError(code, os.strerror(code), str(destination))

    @staticmethod
    def _write_temp_bytes(fd: int, content: bytes) -> None:
        view = memoryview(content)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]

    def bind_registered_rdc_shell_exec(self, *, adapter: Any, operation_ids: tuple[str, ...] | list[str],
                                       source_revision: str,
                                       granted_capabilities_by_operation: dict[str, set[str] | frozenset[str] | tuple[str, ...] | list[str]],
                                       approval_verifier: Callable[[Any], bool] | None = None) -> None:
        """Bind shell.exec only to an explicit allowlist of pre-registered RDC operations.

        Caller input selects an operation ID and typed arguments; it cannot supply a
        shell command, executable string, target, capabilities, risk class or revision.
        The target, operation contract, and revision come from trusted host wiring.
        """
        if not callable(getattr(adapter, "execute", None)) or not isinstance(getattr(adapter, "_operations", None), dict):
            raise ElevatedCapabilityError("RDC_ADAPTER_CONTRACT_INVALID")
        if not isinstance(source_revision, str) or len(source_revision) not in {40, 64} or any(
            ch not in "0123456789abcdef" for ch in source_revision
        ):
            raise ElevatedCapabilityError("RDC_SOURCE_REVISION_INVALID")
        if type(operation_ids) not in (tuple, list) or not operation_ids or len(operation_ids) > 64:
            raise ElevatedCapabilityError("RDC_OPERATION_ALLOWLIST_INVALID")
        if len(set(operation_ids)) != len(operation_ids) or any(
            not isinstance(item, str) or item not in adapter._operations for item in operation_ids
        ):
            raise ElevatedCapabilityError("RDC_OPERATION_NOT_REGISTERED")
        if type(granted_capabilities_by_operation) is not dict or set(granted_capabilities_by_operation) != set(operation_ids):
            raise ElevatedCapabilityError("RDC_HOST_GRANTS_MUST_MATCH_ALLOWLIST")
        fixed_grants = {}
        risk_classes = set()
        for operation_id in operation_ids:
            registered = adapter._operations[operation_id]
            operation = registered.operation
            grants = granted_capabilities_by_operation[operation_id]
            if type(grants) not in (set, frozenset, tuple, list) or any(not isinstance(cap, str) for cap in grants):
                raise ElevatedCapabilityError("RDC_HOST_GRANTS_INVALID")
            if not set(operation.required_capabilities).issubset(set(grants)):
                raise ElevatedCapabilityError("RDC_HOST_GRANTS_INCOMPLETE")
            fixed_grants[operation_id] = frozenset(grants)
            risk_classes.add(operation.risk_class)
        if len(risk_classes) != 1:
            raise ElevatedCapabilityError("RDC_OPERATION_RISK_CLASSES_MUST_MATCH")
        risk = next(iter(risk_classes))
        def invoke(payload: dict[str, Any]) -> dict[str, Any]:
            required = {"operation_id", "command_id", "request_id", "idempotency_key", "arguments", "approval_ref"}
            if set(payload) != required:
                raise ElevatedCapabilityError("RDC_SHELL_PAYLOAD_INVALID")
            operation_id = payload["operation_id"]
            if not isinstance(operation_id, str) or operation_id not in fixed_grants:
                raise ElevatedCapabilityError("RDC_OPERATION_NOT_ALLOWLISTED")
            registered = adapter._operations[operation_id]
            operation = registered.operation
            if type(payload["arguments"]) is not dict:
                raise ElevatedCapabilityError("RDC_OPERATION_ARGUMENTS_INVALID")
            command = {
                "schema_version": "HG_REMOTE_DESKTOP_COMMAND_V1",
                "command_id": payload["command_id"],
                "request_id": payload["request_id"],
                "target_id": adapter.target_id,
                "operation_id": operation_id,
                "arguments": payload["arguments"],
                "required_capabilities": list(operation.required_capabilities),
                "risk_class": operation.risk_class,
                "idempotency_key": payload["idempotency_key"],
                "source_revision": source_revision,
                "approval_ref": payload["approval_ref"],
            }
            result = adapter.execute(command, granted_capabilities=fixed_grants[operation_id],
                                     approval_verifier=approval_verifier)
            from .contracts import canonical_digest
            return {
                "schema_version": ELEVATED_CAPABILITY_REGISTRY_V1,
                "status": "COMPLETE" if result.get("status") == "COMPLETED" else "BLOCKED",
                "operation_id": operation_id,
                "command_id": payload["command_id"],
                "reason_code": result.get("reason_code"),
                "decision_digest": (result.get("decision") or {}).get("decision_digest"),
                "output_digest": canonical_digest(result.get("result")),
                "side_effect_performed": result.get("status") == "COMPLETED",
            }

        if "shell.exec" in self._handlers:
            raise ElevatedCapabilityError("ELEVATED_HANDLER_ALREADY_REGISTERED")
        self._handlers["shell.exec"] = invoke
        self._metadata["shell.exec"] = {
            "scope": "shell.exec",
            "side_effect_class": risk,
            "adapter_id": "hg.elevated_capability_registry.registered_rdc_bridge.v1",
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
                if _action == "file.write":
                    inputs = state.get("INPUT")
                    payload = inputs.get("elevated_file_write") if type(inputs) is dict else None
                    if type(payload) is not dict:
                        return {"status": "BLOCKED", "reason": "MAEP_FILE_WRITE_INPUT_REQUIRED",
                                "side_effect_state": "NOT_PERFORMED"}
                    try:
                        written = self.dispatch("file.write", payload)
                    except ElevatedCapabilityError as exc:
                        return {"status": "BLOCKED", "reason": exc.code,
                                "side_effect_state": "NOT_PERFORMED"}
                    if written.get("status") not in {"COMPLETE", "IDEMPOTENT_NOOP"}:
                        return {"status": "BLOCKED", "reason": "MAEP_FILE_WRITE_RESULT_INVALID",
                                "side_effect_state": "IN_DOUBT"}
                    return {"status": "COMPLETE", "exit_criteria": {"passed": True, "evidence_ids": list(refs)},
                            "evidence_ids": list(refs), "reason": "CREATE_ONLY_FILE_WRITE_VERIFIED",
                            "write_receipt": {"reference": written.get("relative_path"),
                                              "sha256": written.get("sha256"),
                                              "size_bytes": written.get("size_bytes"),
                                              "created": written.get("created")}}
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
