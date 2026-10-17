"""Canonical phone-local memory service backed by HG's hash-chained event log.

No network or model calls occur here. Callers and grants are supplied by trusted
server-side code; request bodies must never be allowed to choose their own grants.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from typing import Any

from .history import StateStore, canonical

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
VALID_TYPES = frozenset({"fact", "preference", "rule", "project", "event", "other"})


class MemoryErrorBase(Exception):
    code = "MEMORY_ERROR"


class MemoryDenied(MemoryErrorBase):
    code = "MEMORY_SCOPE_DENIED"


class MemoryConflict(MemoryErrorBase):
    code = "VERSION_CONFLICT"


class MemoryValidationError(MemoryErrorBase):
    code = "INVALID_MEMORY"


class MemoryIdempotencyConflict(MemoryErrorBase):
    code = "IDEMPOTENCY_CONFLICT"


def _sha(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


class MemoryStore:
    """Event-sourced memory projection over the same canonical StateStore as HG."""

    def __init__(self, store: StateStore):
        self.store = store
        self._lock = threading.RLock()

    @staticmethod
    def _scope_allowed(grants, scope_id: str) -> bool:
        # Wildcards are intentionally unsupported; explicit scope grants only.
        return isinstance(grants, (set, frozenset, list, tuple)) and scope_id in grants

    def _projection(self):
        active: dict[str, dict[str, Any]] = {}
        idempotency: dict[str, tuple[str, dict[str, Any]]] = {}
        for event in self.store.replay():
            typ, p = event.get("event_type"), event.get("payload", {})
            if typ == "memory.mutated" and isinstance(p, dict):
                rec = p.get("record")
                if isinstance(rec, dict):
                    active[rec["id"]] = rec
                key = p.get("idempotency_key")
                fp = p.get("request_fingerprint")
                if key and fp:
                    idempotency[key] = (fp, p.get("result", {}))
            elif typ == "memory.tombstoned" and isinstance(p, dict):
                rec = p.get("record")
                if isinstance(rec, dict):
                    active[rec["id"]] = rec
                key = p.get("idempotency_key")
                fp = p.get("request_fingerprint")
                if key and fp:
                    idempotency[key] = (fp, p.get("result", {}))
        return active, idempotency

    def remember(self, record: dict[str, Any], *, principal_id: str, grants,
                 idempotency_key: str, expected_version: int | None = None,
                 correlation_id: str | None = None) -> dict[str, Any]:
        if not principal_id or not isinstance(record, dict) or not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise MemoryValidationError("principal, record and idempotency_key are required")
        rec_id = record.get("id")
        if not isinstance(rec_id, str) or not ID_RE.fullmatch(rec_id):
            raise MemoryValidationError("invalid id")
        title, content = record.get("title"), record.get("content")
        scope_id, kind = record.get("scope_id"), record.get("type", "fact")
        if not isinstance(title, str) or not title.strip() or len(title) > 300:
            raise MemoryValidationError("invalid title")
        if not isinstance(content, str) or not content.strip() or len(content) > 100_000:
            raise MemoryValidationError("invalid content")
        if not isinstance(scope_id, str) or not scope_id or len(scope_id) > 128 or not self._scope_allowed(grants, scope_id):
            raise MemoryDenied("scope not granted")
        if kind not in VALID_TYPES:
            raise MemoryValidationError("invalid type")
        with self._lock, self.store._lock:
            active, keys = self._projection()
            normalized = {"id": rec_id, "type": kind, "title": title.strip(), "content": content,
                          "scope_id": scope_id, "owner_id": principal_id,
                          "source": str(record.get("source", "user"))[:256],
                          "provenance": str(record.get("provenance", "phone-runtime"))[:1000],
                          "status": "active"}
            fingerprint = _sha({"op": "remember", "record": normalized, "expected_version": expected_version,
                                "principal_id": principal_id})
            if idempotency_key in keys:
                old_fp, result = keys[idempotency_key]
                if old_fp != fingerprint:
                    raise MemoryIdempotencyConflict("idempotency key reused with different request")
                return dict(result)
            prior = active.get(rec_id)
            if prior and prior.get("status") == "tombstoned":
                raise MemoryConflict("tombstoned IDs cannot be resurrected")
            if prior:
                if expected_version is None or expected_version != prior.get("version"):
                    raise MemoryConflict("exact expected_version required for update")
                version = int(expected_version) + 1
            else:
                if expected_version not in (None, 0):
                    raise MemoryConflict("new record expects version 0")
                version = 1
            normalized["version"] = version
            normalized["checksum"] = _sha(normalized)
            result = dict(normalized)
            self.store.emit("memory.mutated", {"record": normalized, "principal_id": principal_id,
                             "idempotency_key": idempotency_key, "request_fingerprint": fingerprint,
                             "result": result}, correlation_id=correlation_id, event_id="memory:" + _sha(idempotency_key))
            return result

    def get(self, record_id: str, *, grants) -> dict[str, Any] | None:
        if not isinstance(record_id, str) or not ID_RE.fullmatch(record_id):
            raise MemoryValidationError("invalid id")
        with self._lock, self.store._lock:
            active, _ = self._projection()
            rec = active.get(record_id)
            if rec is None:
                return None
            if not self._scope_allowed(grants, str(rec.get("scope_id", ""))):
                raise MemoryDenied("scope not granted")
            if rec.get("status") != "active":
                return None
            check = dict(rec); got = check.pop("checksum", None)
            if got != _sha(check):
                raise MemoryValidationError("memory checksum mismatch")
            return dict(rec)

    def delete(self, record_id: str, *, principal_id: str, grants, expected_version: int,
               idempotency_key: str, correlation_id: str | None = None) -> dict[str, Any]:
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise MemoryValidationError("idempotency_key required")
        with self._lock, self.store._lock:
            active, keys = self._projection()
            prior = active.get(record_id)
            if prior is None:
                raise MemoryValidationError("memory not found")
            if not self._scope_allowed(grants, str(prior.get("scope_id", ""))):
                raise MemoryDenied("scope not granted")
            fingerprint = _sha({"op": "delete", "id": record_id, "expected_version": expected_version,
                                "principal_id": principal_id})
            if idempotency_key in keys:
                old_fp, result = keys[idempotency_key]
                if old_fp != fingerprint:
                    raise MemoryIdempotencyConflict("idempotency key reused with different request")
                return dict(result)
            if prior.get("status") != "active" or prior.get("version") != expected_version:
                raise MemoryConflict("stale or already deleted memory")
            tombstone = dict(prior)
            tombstone["version"] = int(expected_version) + 1
            tombstone["status"] = "tombstoned"
            tombstone["content"] = ""
            tombstone["checksum"] = _sha({k: v for k, v in tombstone.items() if k != "checksum"})
            result = {"id": record_id, "version": tombstone["version"], "status": "tombstoned", "checksum": tombstone["checksum"]}
            self.store.emit("memory.tombstoned", {"record": tombstone, "principal_id": principal_id,
                             "idempotency_key": idempotency_key, "request_fingerprint": fingerprint,
                             "result": result}, correlation_id=correlation_id, event_id="memory:" + _sha(idempotency_key))
            return result

    def list_active(self, *, grants, limit: int = 100) -> list[dict[str, Any]]:
        if not isinstance(limit, int) or not 1 <= limit <= 500:
            raise MemoryValidationError("limit must be 1..500")
        with self._lock, self.store._lock:
            active, _ = self._projection()
            visible = []
            for rec in active.values():
                if rec.get("status") != "active" or not self._scope_allowed(grants, str(rec.get("scope_id", ""))):
                    continue
                check = dict(rec); got = check.pop("checksum", None)
                if got != _sha(check):
                    raise MemoryValidationError("memory checksum mismatch")
                visible.append(dict(rec))
            visible.sort(key=lambda x: (x.get("id", ""), x.get("version", 0)))
            return visible[:limit]
