"""Read-only reconciliation audit between legacy JSON memory and backend SQLite.

The report contains aggregate counts, identifiers' hashes, and checksums only;
memory claims and other user content are never emitted.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sqlite3
from pathlib import Path


def _sha_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _artifact_snapshot(path: Path):
    artifacts = {}
    for suffix in ("", "-wal", "-shm"):
        item = Path(str(path) + suffix)
        if not item.is_file():
            continue
        artifacts[suffix or "main"] = {
            "size": item.stat().st_size,
            "sha256": _sha_file(item),
        }
    return artifacts


def reconcile(state_path: Path, database_path: Path) -> dict:
    state_path = state_path.resolve(strict=True)
    database_path = database_path.resolve(strict=True)
    state_raw = state_path.read_bytes()
    state = json.loads(state_raw)
    if not isinstance(state, dict):
        raise ValueError("state root must be an object")
    state_memories = state.get("memory", [])
    if not isinstance(state_memories, list):
        raise ValueError("state memory must be a list")
    state_by_id = {}
    duplicate_state_ids = 0
    for record in state_memories:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"]:
            continue
        if record["id"] in state_by_id:
            duplicate_state_ids += 1
        else:
            state_by_id[record["id"]] = record

    state_sha_before = hashlib.sha256(state_raw).hexdigest()
    state_stat_before = state_path.stat()
    artifacts_before = _artifact_snapshot(database_path)
    database_sha_before = _sha_file(database_path)
    database_stat_before = database_path.stat()
    uri = database_path.as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=3, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    try:
        integrity_rows = [row[0] for row in connection.execute("PRAGMA quick_check")]
        if integrity_rows != ["ok"]:
            raise ValueError("backend database quick_check failed")
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "memory" not in tables:
            raise ValueError("backend database has no memory table")
        memory_columns = {row[1] for row in connection.execute("PRAGMA table_info(memory)")}
        required = {"memory_id", "version", "claim", "checksum"}
        if not required.issubset(memory_columns):
            raise ValueError("backend memory schema is missing required fields")
        columns = ["memory_id", "version", "claim", "checksum"]
        if "updated_at" in memory_columns:
            columns.append("updated_at")
        query = "SELECT " + ",".join('"' + c + '"' for c in columns) + " FROM memory"
        backend_rows = [dict(row) for row in connection.execute(query)]
        table_counts = {}
        for table in sorted(tables):
            escaped = '"' + table.replace('"', '""') + '"'
            table_counts[table] = int(connection.execute(
                "SELECT COUNT(*) FROM " + escaped).fetchone()[0])
        operation_summary = {"available": "operations" in tables, "row_count": 0,
                             "kinds": {}, "result_categories": {}}
        if "operations" in tables:
            operation_columns = {row[1] for row in connection.execute("PRAGMA table_info(operations)")}
            if {"kind", "result_json"}.issubset(operation_columns):
                kinds = collections.Counter()
                categories = collections.Counter()
                for row in connection.execute("SELECT kind,result_json FROM operations"):
                    kinds[str(row["kind"] or "UNSPECIFIED")] += 1
                    try:
                        result = json.loads(row["result_json"] or "{}")
                    except (ValueError, TypeError):
                        categories["INVALID_RESULT_JSON"] += 1
                        continue
                    if not isinstance(result, dict):
                        categories["NON_OBJECT_RESULT"] += 1
                    elif result.get("ok") is True:
                        if result.get("noop") is True:
                            categories["SUCCESS_NOOP"] += 1
                        else:
                            categories["SUCCESS"] += 1
                    else:
                        error = result.get("error")
                        code = error.get("code") if isinstance(error, dict) else None
                        categories["FAIL_" + str(code or "UNKNOWN")] += 1
                operation_summary = {
                    "available": True,
                    "row_count": sum(kinds.values()),
                    "kinds": dict(sorted(kinds.items())),
                    "result_categories": dict(sorted(categories.items())),
                }
        db_by_id = {}
        duplicate_db_ids = 0
        for row in backend_rows:
            memory_id = str(row.get("memory_id") or "")
            if not memory_id:
                continue
            if memory_id in db_by_id:
                duplicate_db_ids += 1
            else:
                db_by_id[memory_id] = row

        overlap = set(state_by_id).intersection(db_by_id)
        json_only = set(state_by_id) - set(db_by_id)
        db_only = set(db_by_id) - set(state_by_id)
        version_matches = claim_matches = exact_matches = conflict_count = 0
        conflict_version_count = conflict_claim_count = 0
        db_only_checksums = collections.Counter()
        overlap_detail = []
        for memory_id in sorted(overlap):
            legacy = state_by_id[memory_id]
            backend = db_by_id[memory_id]
            vmatch = legacy.get("version") == backend.get("version")
            content = legacy.get("content")
            cmatch = isinstance(content, str) and content == backend.get("claim")
            if vmatch: version_matches += 1
            else: conflict_version_count += 1
            if cmatch: claim_matches += 1
            else: conflict_claim_count += 1
            if vmatch and cmatch:
                exact_matches += 1
                disposition = "DUPLICATE_MATCH"
            else:
                conflict_count += 1
                disposition = "QUARANTINE_VERSION_OR_CONTENT_CONFLICT"
            overlap_detail.append({
                "memory_id_sha256": hashlib.sha256(memory_id.encode("utf-8")).hexdigest(),
                "state_version": legacy.get("version"),
                "backend_version": backend.get("version"),
                "version_match": vmatch,
                "content_match": cmatch,
                "disposition": disposition,
                "state_scope": legacy.get("scope") if legacy.get("scope") in ("global", "HG") else "UNSCOPED",
                "backend_has_scope_column": "scope_id" in memory_columns,
            })
        for memory_id in db_only:
            checksum = str(db_by_id[memory_id].get("checksum") or "")
            category = "SHA256_HEX64" if len(checksum) == 64 and all(c in "0123456789abcdef" for c in checksum) else (
                "SHA1_HEX40" if len(checksum) == 40 and all(c in "0123456789abcdef" for c in checksum) else "OTHER_OR_INVALID")
            db_only_checksums[category] += 1
        artifacts_after = _artifact_snapshot(database_path)
        counts = {
            "state_memory_rows": len(state_memories),
            "state_unique_id_rows": len(state_by_id),
            "state_duplicate_ids": duplicate_state_ids,
            "backend_memory_rows": len(backend_rows),
            "backend_unique_id_rows": len(db_by_id),
            "backend_duplicate_ids": duplicate_db_ids,
            "overlap_count": len(overlap),
            "overlap_version_matches": version_matches,
            "overlap_content_matches": claim_matches,
            "exact_duplicate_matches": exact_matches,
            "overlap_conflicts": conflict_count,
            "overlap_version_conflicts": conflict_version_count,
            "overlap_content_conflicts": conflict_claim_count,
            "state_only_count": len(json_only),
            "backend_only_count": len(db_only),
            "backend_only_checksum_categories": dict(sorted(db_only_checksums.items())),
            "backend_scope_column_present": "scope_id" in memory_columns,
        }
        database_stat_after = database_path.stat()
        database_sha_after = _sha_file(database_path)
        stable = (
            artifacts_before == artifacts_after
            and database_sha_before == database_sha_after
            and database_stat_before.st_size == database_stat_after.st_size
            and database_stat_before.st_mtime_ns == database_stat_after.st_mtime_ns
        )
        state_stat_after = state_path.stat()
        state_sha_after = _sha_file(state_path)
        state_stable = (
            state_sha_before == state_sha_after
            and state_stat_before.st_size == state_stat_after.st_size
            and state_stat_before.st_mtime_ns == state_stat_after.st_mtime_ns
        )
        return {
            "schema": "HG2_LEGACY_BACKEND_RECONCILIATION_V1",
            "status": "READ_ONLY_AUDIT",
            "state_source": {"path": str(state_path), "sha256": state_sha_before,
                             "sha256_after": state_sha_after, "bytes": len(state_raw),
                             "stable_during_audit": state_stable},
            "backend_source": {"path": str(database_path), "database_sha256": database_sha_before,
                               "database_sha256_after": database_sha_after,
                               "bytes": database_stat_before.st_size,
                               "artifacts_before": artifacts_before, "artifacts_after": artifacts_after,
                               "stable_during_audit": stable,
                               "sqlite_quick_check": integrity_rows[0]},
            "tables": table_counts,
            "memory_reconciliation": counts,
            "operations": operation_summary,
            "overlap": overlap_detail,
            "backend_only_memory_id_sha256": sorted(hashlib.sha256(x.encode("utf-8")).hexdigest() for x in db_only),
            "state_only_memory_id_sha256": sorted(hashlib.sha256(x.encode("utf-8")).hexdigest() for x in json_only),
            "scope_disposition": {
                "json_scoped_values": dict(sorted(collections.Counter(
                    str(x.get("scope")) if x.get("scope") in ("global", "HG") else "UNSCOPED"
                    for x in state_memories if isinstance(x, dict)).items())),
                "backend_rows_are_not_scope_authoritative": True,
                "backend_only_records_must_remain_quarantined": True,
                "overlap_conflicts_must_not_be_activated": True,
            },
            "cutover_ready": False,
            "cutover_blockers": [
                "The JSON state and SQLite backend have separate source files and no shared atomic snapshot/cursor.",
                "The backend memory schema has no scope_id; database-only records cannot safely enter active memory.",
                "Only exact id+version+claim matches may be considered duplicates; conflicts require quarantine and resolution.",
                "The active backend writer may add data after the read-only audit; repeat the audit at migration freeze.",
            ],
        }
    finally:
        connection.rollback()
        connection.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = reconcile(args.state, args.database)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
