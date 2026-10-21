"""Fail-closed verification of signed HG2 semantic runner receipts.

The allowed-signers file is a trust anchor and MUST be provisioned outside the
candidate repository by an administrator. Local hashes alone do not authenticate
the runner or prove semantic truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA = "HG2_SEMANTIC_RUNNER_RECEIPT_V1"
NAMESPACE = "hg2-runner-receipt"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_UNITTEST_SUMMARY = re.compile(r"(?m)^Ran\s+(\d+)\s+tests?\s+in\s+[0-9.]+s\s*$")
_TOP_KEYS = {"schema_version", "repository", "runner", "source", "suite", "environment", "execution"}
_RUNNER_KEYS = {"id", "signer", "image_digest"}
_SOURCE_KEYS = {"commit", "tree", "working_tree_clean"}
_SUITE_KEYS = {"id", "command", "suite_sha256"}
_ENV_KEYS = {"os", "architecture", "python"}
_EXEC_KEYS = {"started_at", "finished_at", "exit_code", "stdout", "stderr", "test_summary"}
_SUMMARY_KEYS = {"total", "failures", "errors"}
_LOG_KEYS = {"path", "sha256", "bytes"}


class RunnerReceiptError(ValueError):
    """A semantic runner receipt was absent, malformed, untrusted, or mismatched."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RunnerReceiptError("RECEIPT_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _exact_keys(value: Any, keys: set[str], code: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise RunnerReceiptError(code)
    return value


def _timestamp(value: Any, code: str) -> datetime:
    if not isinstance(value, str):
        raise RunnerReceiptError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RunnerReceiptError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RunnerReceiptError(code)
    return parsed


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _validate_trust_root(path: Path, repository_root: Path) -> Path:
    if not path.is_absolute():
        raise RunnerReceiptError("TRUST_ROOT_PATH_MUST_BE_ABSOLUTE")
    if path.is_symlink():
        raise RunnerReceiptError("TRUST_ROOT_SYMLINK_BLOCKED")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise RunnerReceiptError("TRUST_ROOT_NOT_PROVISIONED") from exc
    if not resolved.is_file():
        raise RunnerReceiptError("TRUST_ROOT_NOT_PROVISIONED")
    try:
        common = os.path.commonpath((str(repository_root.resolve()), str(resolved)))
    except ValueError as exc:
        raise RunnerReceiptError("TRUST_ROOT_PATH_INVALID") from exc
    if common == str(repository_root.resolve()):
        raise RunnerReceiptError("TRUST_ROOT_MUST_BE_OUTSIDE_REPOSITORY")
    mode = stat.S_IMODE(resolved.stat().st_mode)
    if mode & 0o022:
        raise RunnerReceiptError("TRUST_ROOT_WRITABLE_BY_GROUP_OR_OTHER")
    if resolved.stat().st_size < 1 or resolved.stat().st_size > 1024 * 1024:
        raise RunnerReceiptError("TRUST_ROOT_SIZE_INVALID")
    return resolved


def _verify_signature(payload: bytes, signature_path: Path, trusted_signers: Path, signer: str) -> None:
    if not isinstance(signer, str) or not signer or len(signer) > 256 or any(c.isspace() for c in signer):
        raise RunnerReceiptError("RUNNER_SIGNER_INVALID")
    if signature_path.is_symlink() or not signature_path.is_file():
        raise RunnerReceiptError("RUNNER_SIGNATURE_MISSING_OR_UNSAFE")
    try:
        result = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", str(trusted_signers),
             "-I", signer, "-n", NAMESPACE, "-s", str(signature_path)],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RunnerReceiptError("SSH_KEYGEN_UNAVAILABLE") from exc
    except subprocess.TimeoutExpired as exc:
        raise RunnerReceiptError("RUNNER_SIGNATURE_VERIFY_TIMEOUT") from exc
    if result.returncode != 0:
        raise RunnerReceiptError("RUNNER_SIGNATURE_INVALID_OR_UNTRUSTED")


def verify_receipt(
    receipt_path: str | Path,
    signature_path: str | Path,
    trusted_signers_path: str | Path,
    *,
    repository_root: str | Path,
    expected_repository: str = "OAI-GIANG/HG2",
    expected_commit: str,
    expected_tree: str,
    expected_suite_id: str,
    expected_suite_command: list[str],
    expected_suite_sha256: str,
    expected_environment: dict[str, str],
    expected_runner_image_digest: str,
    expected_trust_root_sha256: str,
    expected_runner_id: str | None = None,
) -> dict:
    """Verify receipt signature, claim binding, actual log bytes and successful exit.

    This verifies a signed runner claim. It is not, by itself, a proof that source
    code is correct; trust depends on the independently provisioned runner key.
    """
    receipt_file = Path(receipt_path)
    signature_file = Path(signature_path)
    repo_root = Path(repository_root).resolve(strict=True)
    if not receipt_file.is_file() or receipt_file.is_symlink():
        raise RunnerReceiptError("RECEIPT_MISSING_OR_UNSAFE")
    try:
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RunnerReceiptError("RECEIPT_JSON_INVALID") from exc

    _exact_keys(receipt, _TOP_KEYS, "RECEIPT_SCHEMA_KEYS_INVALID")
    if receipt["schema_version"] != SCHEMA or receipt["repository"] != expected_repository:
        raise RunnerReceiptError("RECEIPT_SCHEMA_OR_REPOSITORY_MISMATCH")

    runner = _exact_keys(receipt["runner"], _RUNNER_KEYS, "RECEIPT_RUNNER_SCHEMA_INVALID")
    if (not isinstance(runner["id"], str) or not runner["id"].strip()
            or not isinstance(runner["signer"], str) or not runner["signer"].strip()
            or not isinstance(runner["image_digest"], str) or not _SHA256.fullmatch(runner["image_digest"])):
        raise RunnerReceiptError("RECEIPT_RUNNER_IDENTITY_INVALID")
    if expected_runner_id is not None and runner["id"] != expected_runner_id:
        raise RunnerReceiptError("RECEIPT_RUNNER_ID_MISMATCH")
    if (not isinstance(expected_runner_image_digest, str)
            or not _SHA256.fullmatch(expected_runner_image_digest)
            or runner["image_digest"] != expected_runner_image_digest):
        raise RunnerReceiptError("RECEIPT_RUNNER_IMAGE_MISMATCH")

    source = _exact_keys(receipt["source"], _SOURCE_KEYS, "RECEIPT_SOURCE_SCHEMA_INVALID")
    if (not isinstance(source["commit"], str) or not _GIT_SHA.fullmatch(source["commit"])
            or source["commit"] != expected_commit
            or not isinstance(source["tree"], str) or not _GIT_SHA.fullmatch(source["tree"])
            or source["working_tree_clean"] is not True):
        raise RunnerReceiptError("RECEIPT_SOURCE_IDENTITY_OR_CLEANLINESS_INVALID")
    if not isinstance(expected_tree, str) or not _GIT_SHA.fullmatch(expected_tree):
        raise RunnerReceiptError("EXPECTED_TREE_PIN_REQUIRED")
    if source["tree"] != expected_tree:
        raise RunnerReceiptError("RECEIPT_TREE_MISMATCH")

    suite = _exact_keys(receipt["suite"], _SUITE_KEYS, "RECEIPT_SUITE_SCHEMA_INVALID")
    if (suite["id"] != expected_suite_id or not isinstance(suite["command"], list)
            or not suite["command"] or any(not isinstance(token, str) or not token for token in suite["command"])
            or suite["command"] != expected_suite_command
            or not isinstance(expected_suite_command, list)
            or not isinstance(suite["suite_sha256"], str)
            or not _SHA256.fullmatch(suite["suite_sha256"])
            or suite["suite_sha256"] != expected_suite_sha256):
        raise RunnerReceiptError("RECEIPT_SUITE_ID_COMMAND_OR_DIGEST_INVALID")

    environment = _exact_keys(receipt["environment"], _ENV_KEYS, "RECEIPT_ENVIRONMENT_SCHEMA_INVALID")
    if (any(not isinstance(v, str) or not v.strip() for v in environment.values())
            or environment != expected_environment):
        raise RunnerReceiptError("RECEIPT_ENVIRONMENT_MISMATCH")

    execution = _exact_keys(receipt["execution"], _EXEC_KEYS, "RECEIPT_EXECUTION_SCHEMA_INVALID")
    started = _timestamp(execution["started_at"], "RECEIPT_START_TIME_INVALID")
    finished = _timestamp(execution["finished_at"], "RECEIPT_FINISH_TIME_INVALID")
    if finished < started:
        raise RunnerReceiptError("RECEIPT_TIME_ORDER_INVALID")
    exit_code = execution["exit_code"]
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise RunnerReceiptError("RECEIPT_EXIT_CODE_INVALID")
    if exit_code != 0:
        raise RunnerReceiptError("RUNNER_EXIT_CODE_NOT_ZERO")

    summary = _exact_keys(execution["test_summary"], _SUMMARY_KEYS, "RECEIPT_TEST_SUMMARY_SCHEMA_INVALID")
    for key in ("total", "failures", "errors"):
        value = summary[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RunnerReceiptError("RECEIPT_TEST_SUMMARY_VALUE_INVALID")
    if summary["total"] < 1:
        raise RunnerReceiptError("SEMANTIC_TEST_COUNT_MUST_BE_POSITIVE")
    if summary["failures"] != 0 or summary["errors"] != 0:
        raise RunnerReceiptError("SEMANTIC_TEST_FAILURES_OR_ERRORS_NONZERO")

    bundle_root = receipt_file.parent.resolve(strict=True)
    log_text = []
    for stream_name in ("stdout", "stderr"):
        log_ref = _exact_keys(execution[stream_name], _LOG_KEYS, "RECEIPT_LOG_SCHEMA_INVALID")
        rel = log_ref["path"]
        if (not isinstance(rel, str) or not rel or Path(rel).is_absolute()
                or "\\" in rel or any(part in ("", ".", "..") for part in rel.split("/"))):
            raise RunnerReceiptError("RECEIPT_LOG_PATH_INVALID")
        log_path = bundle_root.joinpath(*rel.split("/"))
        if log_path.is_symlink() or not log_path.is_file():
            raise RunnerReceiptError("RECEIPT_LOG_MISSING_OR_UNSAFE")
        if log_path.stat().st_size > 32 * 1024 * 1024:
            raise RunnerReceiptError("RECEIPT_LOG_SIZE_LIMIT_EXCEEDED")
        try:
            if os.path.commonpath((str(bundle_root), str(log_path.resolve(strict=True)))) != str(bundle_root):
                raise RunnerReceiptError("RECEIPT_LOG_PATH_ESCAPE")
        except ValueError as exc:
            raise RunnerReceiptError("RECEIPT_LOG_PATH_ESCAPE") from exc
        digest, byte_count = _hash_file(log_path)
        if byte_count > 32 * 1024 * 1024:
            raise RunnerReceiptError("RECEIPT_LOG_SIZE_LIMIT_EXCEEDED")
        if (not isinstance(log_ref["sha256"], str) or not _SHA256.fullmatch(log_ref["sha256"])
                or not isinstance(log_ref["bytes"], int) or isinstance(log_ref["bytes"], bool)
                or log_ref["bytes"] < 0 or digest != log_ref["sha256"] or byte_count != log_ref["bytes"]):
            raise RunnerReceiptError("RECEIPT_LOG_BINDING_MISMATCH_" + stream_name.upper())
        try:
            log_text.append(log_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            raise RunnerReceiptError("RECEIPT_LOG_NOT_UTF8") from exc

    combined_log = "\n".join(log_text)
    found_summaries = list(_UNITTEST_SUMMARY.finditer(combined_log))
    if len(found_summaries) != 1 or int(found_summaries[0].group(1)) != summary["total"]:
        raise RunnerReceiptError("SEMANTIC_UNITTEST_SUMMARY_MISMATCH")
    if not re.search(r"(?m)^OK\s*$", combined_log) or re.search(r"(?m)^FAILED(?:\s|$)", combined_log):
        raise RunnerReceiptError("SEMANTIC_UNITTEST_LOG_NOT_SUCCESSFUL")

    trust_root = _validate_trust_root(Path(trusted_signers_path), repo_root)
    if not isinstance(expected_trust_root_sha256, str) or not _SHA256.fullmatch(expected_trust_root_sha256):
        raise RunnerReceiptError("TRUST_ROOT_PIN_REQUIRED")
    trust_root_sha256, _ = _hash_file(trust_root)
    if trust_root_sha256 != expected_trust_root_sha256:
        raise RunnerReceiptError("TRUST_ROOT_DIGEST_MISMATCH")
    _verify_signature(_canonical(receipt), signature_file, trust_root, runner["signer"])
    receipt_digest = hashlib.sha256(_canonical(receipt)).hexdigest()
    return {
        "schema_version": "HG2_RUNNER_RECEIPT_VERIFICATION_V1",
        "status": "VERIFIED",
        "runner_claim_verified": True,
        "test_summary_semantically_consistent": True,
        "semantic_truth_verified": False,
        "repository": expected_repository,
        "commit": source["commit"],
        "tree": source["tree"],
        "suite_id": suite["id"],
        "suite_sha256": suite["suite_sha256"],
        "runner_id": runner["id"],
        "signer": runner["signer"],
        "exit_code": exit_code,
        "receipt_sha256": receipt_digest,
        "trust_root_sha256": trust_root_sha256,
        "trust_root_external_to_repository": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--signature", required=True, type=Path)
    parser.add_argument("--trusted-signers", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-tree", required=True)
    parser.add_argument("--expected-suite-id", required=True)
    parser.add_argument("--expected-suite-command-json", required=True,
                        help="JSON list of exact argv tokens")
    parser.add_argument("--expected-suite-sha256", required=True)
    parser.add_argument("--expected-runner-image-digest", required=True)
    parser.add_argument("--expected-trust-root-sha256", required=True,
                        help="SHA-256 provisioned through an independent channel")
    parser.add_argument("--expected-environment-json", required=True,
                        help='JSON object with exactly "os", "architecture", "python"')
    parser.add_argument("--expected-runner-id")
    args = parser.parse_args()
    try:
        expected_environment = json.loads(args.expected_environment_json)
        expected_suite_command = json.loads(args.expected_suite_command_json)
        if not isinstance(expected_environment, dict):
            raise RunnerReceiptError("EXPECTED_ENVIRONMENT_INVALID")
        if not isinstance(expected_suite_command, list):
            raise RunnerReceiptError("EXPECTED_SUITE_COMMAND_INVALID")
        result = verify_receipt(
            args.receipt, args.signature, args.trusted_signers,
            repository_root=args.repository_root, expected_commit=args.expected_commit,
            expected_tree=args.expected_tree, expected_suite_id=args.expected_suite_id,
            expected_suite_command=expected_suite_command,
            expected_suite_sha256=args.expected_suite_sha256,
            expected_environment=expected_environment,
            expected_runner_image_digest=args.expected_runner_image_digest,
            expected_trust_root_sha256=args.expected_trust_root_sha256,
            expected_runner_id=args.expected_runner_id,
        )
    except (RunnerReceiptError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
