"""Source-backed verification of evidence references for HG2.

The adapter only verifies files under explicitly configured roots and binds the
verification decision to an identity and trust-root digest. It never treats a
caller-supplied SHA-256 as proof that a claim is semantically true.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping

from .task_contract import canonical_json

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERIFIER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_REFERENCE_SCHEMES = ("path:", "evidence:")
_MAX_BYTES = 50_000_000


class EvidenceVerificationError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class FilesystemEvidenceVerifier:
    """Verify file bytes within configured roots; return bound, reproducible receipts.

    Roots are resolved at construction and are explicitly supplied by the trusted caller.
    Symlinks, path traversal, non-regular files, empty allowlists, oversized files and
    mismatched digests fail closed. Network URLs require a separate pinned fetch adapter.
    """

    def __init__(self, *, verifier_id: str, trust_root_digest: str,
                 allowed_roots: list[str | os.PathLike[str]], max_bytes: int = _MAX_BYTES):
        if not isinstance(verifier_id, str) or not _VERIFIER_ID.fullmatch(verifier_id):
            raise EvidenceVerificationError("EVIDENCE_VERIFIER_ID_INVALID")
        if not isinstance(trust_root_digest, str) or not _SHA256.fullmatch(trust_root_digest):
            raise EvidenceVerificationError("EVIDENCE_TRUST_ROOT_DIGEST_INVALID")
        if not isinstance(allowed_roots, list) or not allowed_roots or len(allowed_roots) > 64:
            raise EvidenceVerificationError("EVIDENCE_ALLOWED_ROOTS_INVALID")
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not 1 <= max_bytes <= _MAX_BYTES:
            raise EvidenceVerificationError("EVIDENCE_MAX_BYTES_INVALID")
        roots = []
        for item in allowed_roots:
            if not isinstance(item, (str, os.PathLike)) or not os.fspath(item):
                raise EvidenceVerificationError("EVIDENCE_ALLOWED_ROOT_INVALID")
            supplied = Path(item)
            if supplied.is_symlink():
                raise EvidenceVerificationError("EVIDENCE_ALLOWED_ROOT_SYMLINK_BLOCKED")
            resolved = supplied.resolve(strict=True)
            if not resolved.is_dir():
                raise EvidenceVerificationError("EVIDENCE_ALLOWED_ROOT_NOT_DIRECTORY")
            roots.append(resolved)
        if len(set(roots)) != len(roots):
            raise EvidenceVerificationError("EVIDENCE_ALLOWED_ROOT_DUPLICATE")
        self.verifier_id = verifier_id
        self.trust_root_digest = trust_root_digest
        self.allowed_roots = tuple(sorted(roots, key=lambda path: str(path)))
        self.max_bytes = max_bytes

    def _resolve_reference(self, reference: str) -> Path:
        if not isinstance(reference, str) or not reference.startswith(_REFERENCE_SCHEMES):
            raise EvidenceVerificationError("EVIDENCE_REFERENCE_SCHEME_UNSUPPORTED")
        relative = reference.split(":", 1)[1]
        if not relative or relative.startswith(("/", "\\")) or "\x00" in relative:
            raise EvidenceVerificationError("EVIDENCE_REFERENCE_PATH_INVALID")
        candidate_text = Path(relative)
        if candidate_text.is_absolute() or any(part in {".", ".."} for part in candidate_text.parts):
            raise EvidenceVerificationError("EVIDENCE_REFERENCE_TRAVERSAL_BLOCKED")
        matches = []
        for root in self.allowed_roots:
            candidate = root / candidate_text
            try:
                resolved = candidate.resolve(strict=True)
                if os.path.commonpath((str(root), str(resolved))) != str(root):
                    continue
                # Do not follow a symlink for the final target or any intermediate component.
                current = root
                unsafe = False
                for part in candidate_text.parts:
                    current = current / part
                    if current.is_symlink():
                        unsafe = True
                        break
                if unsafe:
                    continue
                matches.append(resolved)
            except (OSError, ValueError):
                continue
        unique = list(dict.fromkeys(matches))
        if len(unique) != 1:
            raise EvidenceVerificationError(
                "EVIDENCE_REFERENCE_NOT_FOUND" if not unique else "EVIDENCE_REFERENCE_AMBIGUOUS"
            )
        return unique[0]

    def verify_reference(self, reference: str, expected_sha256: str | None = None) -> dict[str, Any]:
        path = self._resolve_reference(reference)
        try:
            info = path.stat(follow_symlinks=False)
        except OSError as exc:
            raise EvidenceVerificationError("EVIDENCE_STAT_FAILED") from exc
        if not stat.S_ISREG(info.st_mode):
            raise EvidenceVerificationError("EVIDENCE_NOT_REGULAR_FILE")
        if info.st_size < 0 or info.st_size > self.max_bytes:
            raise EvidenceVerificationError("EVIDENCE_SIZE_LIMIT_EXCEEDED")
        digest = hashlib.sha256()
        size = 0
        try:
            # Open without following a final symlink where O_NOFOLLOW is available.
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(path, flags)
            try:
                opened = os.fstat(fd)
                if not stat.S_ISREG(opened.st_mode) or opened.st_ino != info.st_ino or opened.st_dev != info.st_dev:
                    raise EvidenceVerificationError("EVIDENCE_CHANGED_DURING_OPEN")
                with os.fdopen(fd, "rb", closefd=False) as handle:
                    while True:
                        block = handle.read(1024 * 1024)
                        if not block:
                            break
                        size += len(block)
                        if size > self.max_bytes:
                            raise EvidenceVerificationError("EVIDENCE_SIZE_LIMIT_EXCEEDED")
                        digest.update(block)
            finally:
                os.close(fd)
        except EvidenceVerificationError:
            raise
        except OSError as exc:
            raise EvidenceVerificationError("EVIDENCE_READ_FAILED") from exc
        actual = digest.hexdigest()
        if size != info.st_size:
            raise EvidenceVerificationError("EVIDENCE_CHANGED_DURING_READ")
        if expected_sha256 is not None:
            if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
                raise EvidenceVerificationError("EVIDENCE_EXPECTED_DIGEST_INVALID")
            if actual != expected_sha256:
                raise EvidenceVerificationError("EVIDENCE_DIGEST_MISMATCH")
        receipt = {
            "schema_version": "HG_EVIDENCE_VERIFICATION_V1",
            "verifier_id": self.verifier_id,
            "trust_root_digest": self.trust_root_digest,
            "reference": reference,
            "resolved_path": str(path),
            "sha256": actual,
            "size_bytes": size,
            "result": "BYTES_MATCHED",
            "semantic_truth_verified": False,
        }
        receipt["receipt_digest"] = hashlib.sha256(canonical_json(receipt).encode("utf-8")).hexdigest()
        return receipt

    def verify_reference_decision(self, reference: str) -> tuple[bool, str]:
        """Verify a reference embedding the expected SHA-256.

        Reference form: evidence:<sha256>/<relative-path> or
        path:<sha256>/<relative-path>. A bare path is insufficient for this trusted
        callback because hashing bytes without a pinned expected digest is observation,
        not verification against a declared artifact.
        """
        if not isinstance(reference, str) or not reference.startswith(_REFERENCE_SCHEMES):
            return False, "EVIDENCE_REFERENCE_SCHEME_UNSUPPORTED"
        scheme, payload = reference.split(":", 1)
        expected, separator, relative = payload.partition("/")
        if not separator or not _SHA256.fullmatch(expected) or not relative:
            return False, "EVIDENCE_REFERENCE_EXPECTED_DIGEST_REQUIRED"
        try:
            receipt = self.verify_reference(scheme + ":" + relative, expected_sha256=expected)
        except EvidenceVerificationError as exc:
            return False, exc.code
        return True, "receipt:" + receipt["receipt_digest"]
