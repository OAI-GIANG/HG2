"""Verified, non-destructive migration from HG_STATE_V1 files into SQLite state.

The source is read-only. The target must be a separate empty directory.
"""
from __future__ import annotations

import hashlib
import math
import os
from typing import Any

from .contracts import ContractError, ZERO_DIGEST, canonical_digest, canonical_json, create_event, parse_json_no_duplicate_keys
from .history import PRODUCT_ID, SCHEMA
from .sqlite_state import SQLiteStateError, SQLiteStateStore, _apply_approval_event, _apply_task_event
from .policy import PolicyError


class MigrationError(RuntimeError):
    """Raised when legacy state cannot be proven safe to migrate."""


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_legacy_state(source_dir: str) -> dict[str, Any]:
    """Read and verify HG_STATE_V1 files without opening StateStore or writing anything."""
    source = os.path.abspath(str(source_dir))
    if os.path.islink(source) or not os.path.isdir(source):
        raise MigrationError("SOURCE_DIRECTORY_INVALID")
    paths = {
        "log": os.path.join(source, "history.jsonl"),
        "head": os.path.join(source, "head.json"),
        "state": os.path.join(source, "state.json"),
        "runtime_id": os.path.join(source, "runtime_id"),
    }
    for label, path in paths.items():
        if os.path.islink(path) or not os.path.isfile(path):
            raise MigrationError("SOURCE_FILE_MISSING_OR_UNSAFE_" + label.upper())

    try:
        with open(paths["runtime_id"], encoding="utf-8") as stream:
            runtime_id = stream.read().strip()
        if not runtime_id:
            raise MigrationError("SOURCE_RUNTIME_ID_EMPTY")

        events = []
        previous = ZERO_DIGEST
        seen_ids = set()
        sessions: dict[str, dict[str, Any]] = {}
        counters: dict[str, int] = {}
        with open(paths["log"], encoding="utf-8") as stream:
            for line_number, raw in enumerate(stream, 1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    record = parse_json_no_duplicate_keys(line)
                except ContractError as exc:
                    raise MigrationError("SOURCE_LOG_INVALID_LINE_%d" % line_number) from exc
                if not isinstance(record, dict):
                    raise MigrationError("SOURCE_RECORD_NOT_OBJECT_LINE_%d" % line_number)
                required = {
                    "seq", "event_id", "event_type", "recorded_at", "correlation_id",
                    "causation_id", "product_id", "runtime_id", "schema", "payload",
                    "prev_hash", "record_hash",
                }
                if set(record) != required:
                    raise MigrationError("SOURCE_RECORD_SCHEMA_MISMATCH_LINE_%d" % line_number)
                if isinstance(record["seq"], bool) or not isinstance(record["seq"], int) or record["seq"] != len(events) + 1:
                    raise MigrationError("SOURCE_SEQUENCE_INVALID_LINE_%d" % line_number)
                if not isinstance(record["event_id"], str) or not record["event_id"]:
                    raise MigrationError("SOURCE_EVENT_ID_INVALID_LINE_%d" % line_number)
                if record["event_id"] in seen_ids:
                    raise MigrationError("SOURCE_DUPLICATE_EVENT_ID_LINE_%d" % line_number)
                if not isinstance(record["event_type"], str) or not record["event_type"]:
                    raise MigrationError("SOURCE_EVENT_TYPE_INVALID_LINE_%d" % line_number)
                timestamp = record["recorded_at"]
                if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp):
                    raise MigrationError("SOURCE_TIMESTAMP_INVALID_LINE_%d" % line_number)
                if record["product_id"] != PRODUCT_ID or record["schema"] != SCHEMA:
                    raise MigrationError("SOURCE_PRODUCT_OR_SCHEMA_MISMATCH_LINE_%d" % line_number)
                if record["runtime_id"] != runtime_id:
                    raise MigrationError("SOURCE_RUNTIME_ID_MISMATCH_LINE_%d" % line_number)
                if not isinstance(record["payload"], dict):
                    raise MigrationError("SOURCE_PAYLOAD_NOT_OBJECT_LINE_%d" % line_number)
                core = {key: value for key, value in record.items() if key != "record_hash"}
                if not isinstance(record["record_hash"], str) or canonical_digest(core) != record["record_hash"]:
                    raise MigrationError("SOURCE_RECORD_HASH_MISMATCH_LINE_%d" % line_number)
                if record["prev_hash"] != previous:
                    raise MigrationError("SOURCE_CHAIN_BREAK_LINE_%d" % line_number)
                previous = record["record_hash"]
                seen_ids.add(record["event_id"])
                events.append(record)
                counters[record["event_type"]] = counters.get(record["event_type"], 0) + 1
                if record["event_type"] == "session.created" and "session_id" in record["payload"]:
                    sessions[record["payload"]["session_id"]] = dict(record["payload"])

        if not events or events[0]["event_type"] != "hg.genesis":
            raise MigrationError("SOURCE_GENESIS_MISSING")
        with open(paths["head"], encoding="utf-8") as stream:
            head = parse_json_no_duplicate_keys(stream.read())
        if not isinstance(head, dict) or set(head) != {"seq", "head_hash"}:
            raise MigrationError("SOURCE_HEAD_SCHEMA_INVALID")
        if head["seq"] != len(events) or head["head_hash"] != previous:
            raise MigrationError("SOURCE_HEAD_MISMATCH")

        with open(paths["state"], encoding="utf-8") as stream:
            state = parse_json_no_duplicate_keys(stream.read())
        expected_state = {
            "schema": SCHEMA,
            "product_id": PRODUCT_ID,
            "runtime_id": runtime_id,
            "last_seq": len(events),
            "head_hash": previous,
            "sessions": sessions,
            "counters": counters,
        }
        if not isinstance(state, dict) or canonical_json(state) != canonical_json(expected_state):
            raise MigrationError("SOURCE_STATE_PROJECTION_MISMATCH")

        return {
            "source_dir": source,
            "source_runtime_id": runtime_id,
            "source_event_count": len(events),
            "source_head_hash": previous,
            "source_log_sha256": _sha256(paths["log"]),
            "source_head_sha256": _sha256(paths["head"]),
            "source_state_sha256": _sha256(paths["state"]),
            "source_runtime_id_sha256": _sha256(paths["runtime_id"]),
            "events": events,
            "sessions": sessions,
            "counters": counters,
        }
    except MigrationError:
        raise
    except (OSError, UnicodeError, ContractError, TypeError, ValueError, KeyError) as exc:
        raise MigrationError("SOURCE_STATE_UNREADABLE") from exc


def _prepare_import_events(records, runtime_id: str) -> list[dict[str, Any]]:
    imported = []
    previous = ZERO_DIGEST
    task_projection: dict[str, dict[str, Any]] = {}
    approval_projection: dict[str, dict[str, Any]] = {}
    for record in records:
        event_id = "legacy-" + hashlib.sha256(record["event_id"].encode("utf-8")).hexdigest()
        authority = {
            "migration": SCHEMA,
            "source_runtime_id": record["runtime_id"],
            "source_sequence": record["seq"],
            "source_event_id": record["event_id"],
        }
        try:
            event = create_event(
                event_type=record["event_type"],
                sequence=record["seq"],
                actor_id="legacy-migration",
                authority_context=authority,
                runtime_id=runtime_id,
                state_owner_id="phone",
                payload=record["payload"],
                previous_digest=previous,
                correlation_id=record["correlation_id"] if isinstance(record["correlation_id"], str) and record["correlation_id"] else "legacy-correlation-" + str(record["seq"]),
                causation_id=record["causation_id"] if isinstance(record["causation_id"], str) else None,
                evidence_refs=[record["record_hash"]],
                event_id=event_id,
                recorded_at=record["recorded_at"],
            )
            task_projection = _apply_task_event(event, task_projection)
            approval_projection = _apply_approval_event(event, approval_projection)
        except (ContractError, PolicyError, ValueError, TypeError, KeyError) as exc:
            raise MigrationError("LEGACY_EVENT_NOT_COMPATIBLE_WITH_TARGET_SCHEMA") from exc
        imported.append(event)
        previous = event["record_digest"]
    return imported


def migrate_legacy_state(source_dir: str, target_dir: str, *, clock=None) -> dict[str, Any]:
    """Verify source, preflight all transformed events, then import atomically into an empty target."""
    source = os.path.abspath(str(source_dir))
    target = os.path.abspath(str(target_dir))
    common = os.path.commonpath((source, target))
    if common == source or common == target:
        raise MigrationError("SOURCE_AND_TARGET_MUST_BE_SEPARATE")
    if os.path.exists(target):
        if os.path.islink(target) or not os.path.isdir(target) or os.listdir(target):
            raise MigrationError("TARGET_MUST_BE_EMPTY_DIRECTORY")
    report = inspect_legacy_state(source)
    _prepare_import_events(report["events"], "migration-preflight")

    from time import time as current_time
    store_clock = current_time if clock is None else clock
    try:
        with SQLiteStateStore(target, clock=store_clock) as store:
            imported = _prepare_import_events(report["events"], store.runtime_id)
            metadata = {
                "source_runtime_id": report["source_runtime_id"],
                "source_head_hash": report["source_head_hash"],
                "source_event_count": report["source_event_count"],
                "source_log_sha256": report["source_log_sha256"],
                "source_head_sha256": report["source_head_sha256"],
                "source_state_sha256": report["source_state_sha256"],
                "source_runtime_id_sha256": report["source_runtime_id_sha256"],
            }
            store.import_verified_events(imported, metadata)
            verification = store.verify()
            if not verification["ok"]:
                raise MigrationError("TARGET_VERIFY_FAILED")
            return {
                "status": "MIGRATED_VERIFIED",
                "source_runtime_id": report["source_runtime_id"],
                "source_event_count": report["source_event_count"],
                "source_head_hash": report["source_head_hash"],
                "source_log_sha256": report["source_log_sha256"],
                "target_runtime_id": store.runtime_id,
                "target_event_count": verification["events"],
                "target_head_digest": verification["head_digest"],
                "target_path": target,
                "verification": verification,
            }
    except MigrationError:
        raise
    except (SQLiteStateError, ContractError, OSError, ValueError, TypeError) as exc:
        raise MigrationError("TARGET_MIGRATION_FAILED") from exc
