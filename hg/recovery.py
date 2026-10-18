"""Verified SQLite backup and restore helpers; source is read-only and targets are never overwritten."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
import uuid
from typing import Any

from .contracts import SCHEMA_VERSION, canonical_json, parse_json_no_duplicate_keys
from .policy import authorize_service_mutation, issue_mutation_permit, consume_mutation_permit
from .auth import AuthenticatedPrincipal
from .sqlite_state import SQLiteStateError, SQLiteStateStore

_DATABASE = "hg2-state.sqlite3"
_BACKUP_MANIFEST = "backup-manifest.json"
_RESTORE_MANIFEST = "restore-manifest.json"
_BACKUP_SCHEMA = "HG2_STATE_BACKUP_V1"


class RecoveryError(RuntimeError):
    """Raised when backup/restore safety or integrity checks fail."""


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _separate_paths(source: str, target: str) -> None:
    common = os.path.commonpath((source, target))
    if common == source or common == target:
        raise RecoveryError("SOURCE_AND_TARGET_MUST_BE_SEPARATE")


def _target_ready(target: str) -> tuple[bool, bool]:
    """Return (directory_existed, target_created_by_call); never accept nonempty target."""
    if os.path.lexists(target):
        if os.path.islink(target) or not os.path.isdir(target) or os.listdir(target):
            raise RecoveryError("TARGET_MUST_BE_EMPTY_DIRECTORY")
        return True, False
    return False, True


def _cleanup_created_target(target: str, existed: bool) -> None:
    if not os.path.isdir(target) or os.path.islink(target):
        return
    for name in (_DATABASE, _DATABASE + "-wal", _DATABASE + "-shm", _DATABASE + "-journal", _BACKUP_MANIFEST, _BACKUP_MANIFEST + ".tmp", _RESTORE_MANIFEST, _RESTORE_MANIFEST + ".tmp"):
        path = os.path.join(target, name)
        if os.path.isfile(path) and not os.path.islink(path):
            try:
                os.remove(path)
            except OSError:
                pass
    if not existed:
        try:
            os.rmdir(target)
        except OSError:
            pass


def _write_manifest(path: str, value: dict[str, Any]) -> None:
    temporary = path + ".tmp"
    encoded = (canonical_json(value) + "\n").encode("utf-8")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(os.path.dirname(path), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise


def _copy_database_read_only(source_path: str, target_path: str) -> None:
    uri = "file:" + source_path.replace("?", "%3f").replace("#", "%23") + "?mode=ro"
    source = sqlite3.connect(uri, uri=True, timeout=5.0)
    target = sqlite3.connect(target_path, timeout=5.0)
    try:
        source.execute("PRAGMA query_only=ON")
        target.execute("PRAGMA synchronous=FULL")
        source.backup(target)
        target.commit()
    finally:
        target.close()
        source.close()


def backup_state(source_dir: str, backup_dir: str, *, principal: AuthenticatedPrincipal | None = None, clock=time.time) -> dict[str, Any]:
    source = os.path.abspath(str(source_dir))
    target = os.path.abspath(str(backup_dir))
    _separate_paths(source, target)
    if os.path.islink(source) or not os.path.isdir(source):
        raise RecoveryError("SOURCE_DIRECTORY_INVALID")
    source_db = os.path.join(source, _DATABASE)
    if os.path.islink(source_db) or not os.path.isfile(source_db):
        raise RecoveryError("SOURCE_DATABASE_MISSING")
    target_existed, _ = _target_ready(target)
    source_hash_before = _sha256(source_db)
    action = "state.backup"
    decision = authorize_service_mutation(action, principal)
    if not decision.allowed:
        raise RecoveryError("BACKUP_AUTHORIZATION_" + decision.reason)
    actor_id = principal.principal_id
    authority_context = {"principal": actor_id, "scope": action}
    operation_payload = {
        "source_database_sha256": source_hash_before,
        "target_path_sha256": hashlib.sha256(target.encode("utf-8")).hexdigest(),
    }
    correlation_id = "backup:" + source_hash_before
    permit = issue_mutation_permit(
        action, principal, event_type=action, actor_id=actor_id, payload=operation_payload,
        correlation_id=correlation_id, authority_context=authority_context,
    )
    if not consume_mutation_permit(
        permit, event_type=action, actor_id=actor_id, payload=operation_payload,
        correlation_id=correlation_id, authority_context=authority_context,
    ):
        raise RecoveryError("BACKUP_AUTHORIZATION_INVALID")
    try:
        os.makedirs(target, exist_ok=True)
        target_db = os.path.join(target, _DATABASE)
        _copy_database_read_only(source_db, target_db)
        with SQLiteStateStore(target) as store:
            audit = store.audit_export()
            if not audit["verify"]["ok"]:
                raise RecoveryError("BACKUP_VERIFY_FAILED")
        source_hash_after = _sha256(source_db)
        if source_hash_before != source_hash_after:
            raise RecoveryError("SOURCE_DATABASE_CHANGED_DURING_BACKUP")
        report = {
            "schema": _BACKUP_SCHEMA,
            "status": "BACKUP_VERIFIED",
            "backup_id": uuid.uuid4().hex,
            "database_name": _DATABASE,
            "database_sha256": _sha256(target_db),
            "source_database_sha256": source_hash_before,
            "source_directory_name": os.path.basename(source),
            "runtime_id": audit["runtime_id"],
            "events": audit["events"],
            "last_seq": audit["last_seq"],
            "head_digest": audit["head_digest"],
            "last_ack_cursor": audit["last_ack_cursor"],
            "created_at": float(clock()),
            "verification": audit["verify"],
        }
        _write_manifest(os.path.join(target, _BACKUP_MANIFEST), report)
        return report
    except RecoveryError:
        _cleanup_created_target(target, target_existed)
        raise
    except (OSError, sqlite3.DatabaseError, SQLiteStateError, ValueError, TypeError) as exc:
        _cleanup_created_target(target, target_existed)
        raise RecoveryError("BACKUP_FAILED") from exc


def restore_state(backup_dir: str, target_dir: str, *, principal: AuthenticatedPrincipal | None = None) -> dict[str, Any]:
    backup = os.path.abspath(str(backup_dir))
    target = os.path.abspath(str(target_dir))
    _separate_paths(backup, target)
    if os.path.islink(backup) or not os.path.isdir(backup):
        raise RecoveryError("BACKUP_DIRECTORY_INVALID")
    backup_db = os.path.join(backup, _DATABASE)
    manifest_path = os.path.join(backup, _BACKUP_MANIFEST)
    if os.path.islink(backup_db) or not os.path.isfile(backup_db) or os.path.islink(manifest_path) or not os.path.isfile(manifest_path):
        raise RecoveryError("BACKUP_ARTIFACT_MISSING")
    try:
        with open(manifest_path, encoding="utf-8") as stream:
            manifest = parse_json_no_duplicate_keys(stream.read())
    except Exception as exc:
        raise RecoveryError("BACKUP_MANIFEST_INVALID") from exc
    required = {
        "schema", "status", "backup_id", "database_name", "database_sha256",
        "source_database_sha256", "source_directory_name", "runtime_id", "events",
        "last_seq", "head_digest", "last_ack_cursor", "created_at", "verification",
    }
    if not isinstance(manifest, dict) or set(manifest) != required:
        raise RecoveryError("BACKUP_MANIFEST_SCHEMA_INVALID")
    if manifest["schema"] != _BACKUP_SCHEMA or manifest["status"] != "BACKUP_VERIFIED" or manifest["database_name"] != _DATABASE:
        raise RecoveryError("BACKUP_MANIFEST_STATUS_INVALID")
    if _sha256(backup_db) != manifest["database_sha256"]:
        raise RecoveryError("BACKUP_DATABASE_HASH_MISMATCH")
    target_existed, _ = _target_ready(target)
    action = "state.restore"
    decision = authorize_service_mutation(action, principal)
    if not decision.allowed:
        raise RecoveryError("RESTORE_AUTHORIZATION_" + decision.reason)
    actor_id = principal.principal_id
    authority_context = {"principal": actor_id, "scope": action}
    operation_payload = {
        "backup_database_sha256": manifest["database_sha256"],
        "target_path_sha256": hashlib.sha256(target.encode("utf-8")).hexdigest(),
    }
    correlation_id = "restore:" + manifest["database_sha256"]
    permit = issue_mutation_permit(
        action, principal, event_type=action, actor_id=actor_id, payload=operation_payload,
        correlation_id=correlation_id, authority_context=authority_context,
    )
    if not consume_mutation_permit(
        permit, event_type=action, actor_id=actor_id, payload=operation_payload,
        correlation_id=correlation_id, authority_context=authority_context,
    ):
        raise RecoveryError("RESTORE_AUTHORIZATION_INVALID")
    try:
        os.makedirs(target, exist_ok=True)
        target_db = os.path.join(target, _DATABASE)
        _copy_database_read_only(backup_db, target_db)
        with SQLiteStateStore(target) as store:
            audit = store.audit_export()
            if not audit["verify"]["ok"]:
                raise RecoveryError("RESTORE_VERIFY_FAILED")
            if (
                audit["runtime_id"] != manifest["runtime_id"]
                or audit["events"] != manifest["events"]
                or audit["head_digest"] != manifest["head_digest"]
                or audit["last_ack_cursor"] != manifest["last_ack_cursor"]
            ):
                raise RecoveryError("RESTORE_STATE_MISMATCH")
        report = {
            "schema": _BACKUP_SCHEMA,
            "status": "RESTORE_VERIFIED",
            "backup_id": manifest["backup_id"],
            "backup_database_sha256": manifest["database_sha256"],
            "restored_database_sha256": _sha256(target_db),
            "runtime_id": audit["runtime_id"],
            "events": audit["events"],
            "last_seq": audit["last_seq"],
            "head_digest": audit["head_digest"],
            "last_ack_cursor": audit["last_ack_cursor"],
            "verification": audit["verify"],
        }
        _write_manifest(os.path.join(target, _RESTORE_MANIFEST), report)
        return report
    except RecoveryError:
        _cleanup_created_target(target, target_existed)
        raise
    except (OSError, sqlite3.DatabaseError, SQLiteStateError, ValueError, TypeError) as exc:
        _cleanup_created_target(target, target_existed)
        raise RecoveryError("RESTORE_FAILED") from exc
