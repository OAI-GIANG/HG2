"""Canonical phone-local memory service backed by HG's hash-chained event log.

No network or model calls occur here. Callers and grants are supplied by trusted
server-side code; request bodies must never be allowed to choose their own grants.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import unicodedata
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
        aliases = record.get("aliases", [])
        if not isinstance(aliases, list) or len(aliases) > 32:
            raise MemoryValidationError("aliases must be a list containing at most 32 strings")
        normalized_aliases = []
        for alias in aliases:
            if not isinstance(alias, str) or not alias.strip() or len(alias) > 300:
                raise MemoryValidationError("each alias must be a non-empty string up to 300 characters")
            normalized_aliases.append(unicodedata.normalize("NFC", alias.strip()))
        normalized_aliases = sorted(set(normalized_aliases), key=str.casefold)
        provenance_metadata = record.get("provenance_metadata")
        if provenance_metadata is not None:
            if type(provenance_metadata) is not dict:
                raise MemoryValidationError("provenance_metadata must be an object")
            from .provenance_memory import memory_freshness
            if provenance_metadata.get("schema_version") != "hg.provenance-memory.v1":
                raise MemoryValidationError("unsupported provenance_metadata schema")
            freshness = memory_freshness(provenance_metadata)
            if "MEMORY_RECORD_DIGEST_MISMATCH" in freshness["reasons"]:
                raise MemoryValidationError("provenance_metadata digest mismatch")

        with self._lock, self.store._lock:
            active, keys = self._projection()
            normalized = {"id": rec_id, "type": kind, "title": title.strip(), "content": content,
                          "scope_id": scope_id, "owner_id": principal_id,
                          "source": str(record.get("source", "user"))[:256],
                          "provenance": str(record.get("provenance", "phone-runtime"))[:1000],
                          "status": "active"}
            if normalized_aliases:
                normalized["aliases"] = normalized_aliases
            if provenance_metadata is not None:
                normalized["provenance_metadata"] = dict(provenance_metadata)
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

    def retrieve(self, query: str, *, grants, limit: int = 10) -> dict[str, Any]:
        """Deterministic lexical retrieval after ACL filtering; no model call."""
        if not isinstance(query, str) or not query.strip() or len(query) > 4000:
            raise MemoryValidationError("query must contain 1..4000 characters")
        if not isinstance(limit, int) or not 1 <= limit <= 50:
            raise MemoryValidationError("limit must be 1..50")
        # NFC around casefold makes canonically equivalent Vietnamese forms match.
        # This is lexical retrieval; it does not claim semantic paraphrase support.
        stop_words = {
            "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
            "for", "from", "how", "i", "in", "is", "it", "me", "of", "on", "or",
            "please", "tell", "that", "the", "this", "to", "was", "what", "when",
            "where", "which", "who", "why", "with", "you", "your", "one", "s",
        }

        def tokens(value: str) -> set[str]:
            folded = unicodedata.normalize("NFC", unicodedata.normalize("NFC", value).casefold())
            return {term for term in re.findall(r"[^\W_]+", folded, flags=re.UNICODE)
                    if term not in stop_words}

        terms = tokens(query)
        if not terms:
            raise MemoryValidationError("query must contain at least one searchable token")
        visible = self.list_active(grants=grants, limit=500)
        provenance_records = [rec["provenance_metadata"] for rec in visible
                              if isinstance(rec.get("provenance_metadata"), dict)]
        conflict_keys = set()
        if provenance_records:
            from .provenance_memory import detect_memory_conflicts
            conflict_keys = {(item["source_ref"], item["memory_key"])
                             for item in detect_memory_conflicts(provenance_records)}
        matches = []
        for rec in visible:
            # If optional provenance metadata is supplied by a newer or imported record,
            # never return stale/unknown items as if current. V1 MemoryStore records without
            # provenance remain supported and are visibly classified as freshness unknown.
            provenance = rec.get("provenance_metadata")
            freshness_status = "FRESHNESS_UNKNOWN"
            if isinstance(provenance, dict):
                from .provenance_memory import memory_freshness
                freshness = memory_freshness(provenance)
                freshness_status = freshness["status"]
                if not freshness["usable"]:
                    continue
            searchable = [str(rec.get("title", "")), str(rec.get("content", ""))]
            aliases = rec.get("aliases", [])
            if isinstance(aliases, list):
                searchable.extend(item for item in aliases if isinstance(item, str))
            text = unicodedata.normalize("NFC", " ".join(searchable))
            words = tokens(text)
            overlap = terms & words
            if not overlap:
                continue
            score = len(overlap) / len(terms)
            # Minimum overlap threshold suppresses records matching only incidental terms.
            if score <= 0.5:
                continue
            conflict_key = (
                provenance.get("source_ref"), provenance.get("memory_key")
            ) if isinstance(provenance, dict) else None
            conflict_status = "CONFLICT_UNRESOLVED" if conflict_key in conflict_keys else "NO_KNOWN_CONFLICT"
            matches.append({**rec, "score": round(score, 6),
                            "retrieval_method": "unicode_normalized_lexical_overlap",
                            "query_term_coverage": round(score, 6),
                            "matched_terms": sorted(overlap),
                            "freshness_status": freshness_status,
                            "memory_conflict_status": conflict_status})
        matches.sort(key=lambda x: (-x["score"], x["id"]))
        matches = matches[:limit]
        query_id = _sha({"query": query, "state_head": self.store.audit_export()["head_hash"]})
        manifest = {"schema_version": 1, "operation": "memory_retrieve", "query_id": query_id,
                    "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
                    "source_head_hash": self.store.audit_export()["head_hash"],
                    "selected": [{"id": r["id"], "version": r["version"], "scope_id": r["scope_id"],
                                  "checksum": r["checksum"], "score": r["score"]} for r in matches],
                    "visible_record_count": len(visible), "match_count": len(matches), "model_called": False}
        manifest["manifest_sha256"] = _sha(manifest)
        return {"query_id": query_id, "matches": matches, "manifest": manifest}

    def build_context(self, query: str, *, grants, limit: int = 10, max_chars: int = 12000) -> dict[str, Any]:
        if not isinstance(max_chars, int) or not 256 <= max_chars <= 100000:
            raise MemoryValidationError("max_chars must be 256..100000")
        result = self.retrieve(query, grants=grants, limit=limit)
        blocks = []; used = 0
        for rec in result["matches"]:
            provenance = rec.get("provenance_metadata")
            from .provenance_memory import effective_memory_trust
            trust_status = effective_memory_trust(provenance) if isinstance(provenance, dict) else "UNVERIFIED"
            block = {"source_id": rec["id"], "version": rec["version"], "scope_id": rec["scope_id"],
                     "checksum": rec["checksum"], "title": rec["title"], "content": rec["content"],
                     "freshness_status": rec.get("freshness_status", "FRESHNESS_UNKNOWN"),
                     "trust_status": trust_status,
                     "memory_conflict_status": rec.get("memory_conflict_status", "NO_KNOWN_CONFLICT"),
                     "content_is_untrusted_data": True}
            size = len(block["title"]) + len(block["content"])
            if used + size > max_chars:
                remaining = max_chars - used
                if remaining <= 0: break
                block["content"] = block["content"][:remaining]
                block["truncated"] = True
                blocks.append(block); used += remaining; break
            block["truncated"] = False
            blocks.append(block); used += size
        manifest = dict(result["manifest"])
        manifest.update({"operation": "memory_context", "context_record_ids": [b["source_id"] for b in blocks],
                         "context_char_count": used, "max_chars": max_chars, "model_called": False})
        manifest["manifest_sha256"] = _sha({k:v for k,v in manifest.items() if k != "manifest_sha256"})
        return {"query_id": result["query_id"], "context": blocks, "manifest": manifest}
