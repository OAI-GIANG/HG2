"""Experimental authenticated batch gate for HG sync.

Keys and trust anchors are injected by the caller; this module never loads secrets
from files or environment. It is candidate-only and is not wired into PhoneRuntime.
"""
from __future__ import annotations
import hashlib, hmac, json, os, tempfile
from typing import Mapping, Protocol
from .history import canonical

AUTH_SCHEMA = "HG_SYNC_AUTH_V1"
class PeerAuthError(ValueError):
    pass

class KeyManagementInterface(Protocol):
    """Trusted key service boundary; callers own storage, rotation and revocation."""
    def get_peer_key(self, peer_id: str, key_id: str) -> bytes | None: ...

class CursorAnchorInterface(Protocol):
    """Independent monotonic anchor, backed by a separately protected authority.

    Implementations must provide atomic compare-and-advance semantics and must not
    permit rollback by restoring the ordinary application filesystem. A file beside
    cursor_path is NOT an adequate production implementation of this interface.
    """
    def read_anchor(self, peer_id: str) -> dict | None: ...
    def initialize_anchor(self, peer_id: str, checkpoint: dict) -> None: ...
    def advance_anchor(self, peer_id: str, expected: dict, proposed: dict) -> None: ...

def _sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)

def sign_batch(batch: dict, *, peer_id: str, key_id: str,
               key_provider: KeyManagementInterface) -> dict:
    """Return a signed copy using key material obtained only via the key interface."""
    if not callable(getattr(key_provider, "get_peer_key", None)):
        raise PeerAuthError("key management interface required")
    key = key_provider.get_peer_key(peer_id, key_id)
    if not isinstance(key, bytes) or len(key) < 32:
        raise PeerAuthError("peer key must contain at least 256 bits")
    if not peer_id or not key_id:
        raise PeerAuthError("peer and key identifiers are required")
    unsigned = dict(batch)
    unsigned.pop("auth", None)
    mac = hmac.new(key, canonical(unsigned).encode("utf-8"), hashlib.sha256).hexdigest()
    return {**unsigned, "auth": {"schema": AUTH_SCHEMA, "peer_id": peer_id,
                                "key_id": key_id, "algorithm": "HMAC-SHA256", "mac": mac}}

class AuthenticatedBatchGate:
    """Verify peer identity and anchored per-origin chain before any state import.

    key_provider: KeyManagementInterface; the gate never loads or stores key material.
    checkpoints: peer_id -> {"seq": nonnegative int, "hash": SHA256}
    cursor_path: durable receiver-owned cursor JSON path, separate from app state.
    A checkpoint of seq=0 must use 64 zeroes as hash.
    """
    def __init__(self, *, key_provider: KeyManagementInterface,
                 checkpoints: Mapping[str, dict], cursor_path: str,
                 cursor_anchor: CursorAnchorInterface):
        if not callable(getattr(key_provider, "get_peer_key", None)):
            raise PeerAuthError("key management interface required")
        if not callable(getattr(cursor_anchor, "read_anchor", None)) or not callable(getattr(cursor_anchor, "initialize_anchor", None)) or not callable(getattr(cursor_anchor, "advance_anchor", None)):
            raise PeerAuthError("independent monotonic cursor anchor required; fail closed")
        self.key_provider = key_provider
        self.cursor_anchor = cursor_anchor
        self.checkpoints = {p: dict(cp) for p, cp in checkpoints.items()}
        self.cursor_path = os.path.abspath(cursor_path)
        self.cursor_recovered_from_anchor = False
        for peer, cp in self.checkpoints.items():
            seq, head = cp.get("seq"), cp.get("hash")
            if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0 or not _sha(head):
                raise PeerAuthError("invalid trusted checkpoint")
            if seq == 0 and head != "0" * 64:
                raise PeerAuthError("genesis checkpoint must use zero hash")
        self._cursors = self._load_cursors()

    def _load_cursors(self):
        try:
            with open(self.cursor_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise PeerAuthError("cursor file corrupt or unreadable") from exc
        if not isinstance(data, dict):
            raise PeerAuthError("invalid cursor file")
        for peer, cur in data.items():
            if (peer not in self.checkpoints or not isinstance(cur, dict)
                    or not isinstance(cur.get("seq"), int) or isinstance(cur.get("seq"), bool)
                    or cur["seq"] < self.checkpoints[peer]["seq"]
                    or not _sha(cur.get("hash"))):
                raise PeerAuthError("cursor is not anchored to trusted peer checkpoint")
        # The independent anchor is authoritative. A cursor that is behind the
        # monotonic anchor is a detected rollback/stale-file condition and is repaired
        # from the anchor (event imports are committed before anchor advancement).
        # A cursor ahead of the anchor is never accepted.
        reconciled = dict(data)
        for peer, cp in self.checkpoints.items():
            local = data.get(peer)
            anchor = self.cursor_anchor.read_anchor(peer)
            if anchor is None:
                if local is not None:
                    raise PeerAuthError("independent cursor anchor missing while cursor exists")
                self.cursor_anchor.initialize_anchor(peer, dict(cp))
                anchor = self.cursor_anchor.read_anchor(peer)
            if (not isinstance(anchor, dict) or not isinstance(anchor.get("seq"), int)
                    or isinstance(anchor.get("seq"), bool) or anchor["seq"] < cp["seq"]
                    or not _sha(anchor.get("hash"))):
                raise PeerAuthError("independent cursor anchor invalid or rolled back")
            if anchor["seq"] == cp["seq"] and anchor["hash"] != cp["hash"]:
                raise PeerAuthError("independent anchor hash does not match trusted checkpoint")
            if local is not None:
                if local["seq"] > anchor["seq"]:
                    raise PeerAuthError("cursor is ahead of independent monotonic anchor")
                if local["seq"] == anchor["seq"] and local["hash"] != anchor["hash"]:
                    raise PeerAuthError("cursor hash differs from independent monotonic anchor")
            if local is None or local["seq"] < anchor["seq"]:
                reconciled[peer] = dict(anchor)
                self.cursor_recovered_from_anchor = True
        if reconciled != data:
            self._persist(reconciled)
        return reconciled

    def _persist(self, data):
        parent = os.path.dirname(self.cursor_path)
        os.makedirs(parent, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".cursor-", dir=parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.cursor_path)
            dfd = os.open(parent, os.O_RDONLY)
            try: os.fsync(dfd)
            finally: os.close(dfd)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)

    def verify(self, batch: dict) -> dict:
        """Validate signature and chain; returns proposed cursor without persisting it."""
        if not isinstance(batch, dict) or not isinstance(batch.get("auth"), dict):
            raise PeerAuthError("missing peer authentication")
        auth = batch["auth"]
        if auth.get("schema") != AUTH_SCHEMA or auth.get("algorithm") != "HMAC-SHA256":
            raise PeerAuthError("unsupported authentication scheme")
        peer, key_id, mac = auth.get("peer_id"), auth.get("key_id"), auth.get("mac")
        if not isinstance(peer, str) or not isinstance(key_id, str):
            raise PeerAuthError("untrusted peer or key")
        key = self.key_provider.get_peer_key(peer, key_id)
        if key is None:
            raise PeerAuthError("untrusted peer or key")
        if not isinstance(key, bytes) or len(key) < 32:
            raise PeerAuthError("trusted peer key is invalid")
        unsigned = dict(batch)
        unsigned.pop("auth", None)
        expected = hmac.new(key, canonical(unsigned).encode("utf-8"), hashlib.sha256).hexdigest()
        if not isinstance(mac, str) or not hmac.compare_digest(mac, expected):
            raise PeerAuthError("authentication failed")
        if unsigned.get("schema") != "HG_SYNC_BATCH_V2" or unsigned.get("context_id") != peer:
            raise PeerAuthError("signed peer does not match batch origin")
        events = unsigned.get("events")
        if not isinstance(events, list) or not events:
            raise PeerAuthError("empty event batch")
        cp = self.checkpoints.get(peer)
        if cp is None:
            raise PeerAuthError("peer has no trusted origin checkpoint")
        cur = self._cursors.get(peer, cp)
        # Idempotent re-delivery is accepted only when the signed batch ends at the
        # exact already-committed cursor. SyncContext still checks every event against
        # the receiver's durable event index and rejects conflicting provenance.
        last = events[-1] if events else None
        duplicate = (isinstance(last, dict) and last.get("origin_seq") == cur["seq"]
                     and last.get("origin_hash") == cur["hash"])
        if duplicate:
            expected_seq = events[0].get("origin_seq") if isinstance(events[0], dict) else None
            if not isinstance(expected_seq, int) or isinstance(expected_seq, bool):
                raise PeerAuthError("invalid event sequence")
            expected_prev = events[0].get("origin_prev_hash")
            for ev in events:
                if not isinstance(ev, dict): raise PeerAuthError("invalid event")
                seq, prev, head = ev.get("origin_seq"), ev.get("origin_prev_hash"), ev.get("origin_hash")
                if not isinstance(seq, int) or isinstance(seq, bool) or seq != expected_seq:
                    raise PeerAuthError("replay or sequence gap")
                if prev != expected_prev or not _sha(head):
                    raise PeerAuthError("origin fork or invalid hash")
                expected_seq, expected_prev = seq + 1, head
            if expected_seq - 1 != cur["seq"] or expected_prev != cur["hash"]:
                raise PeerAuthError("duplicate batch does not match committed cursor")
            return {"peer_id": peer, "seq": cur["seq"], "hash": cur["hash"],
                    "previous_seq": cur["seq"], "previous_hash": cur["hash"], "duplicate": True}
        expected_seq, expected_prev = cur["seq"] + 1, cur["hash"]
        for ev in events:
            if not isinstance(ev, dict): raise PeerAuthError("invalid event")
            seq, prev, head = ev.get("origin_seq"), ev.get("origin_prev_hash"), ev.get("origin_hash")
            if not isinstance(seq, int) or isinstance(seq, bool) or seq != expected_seq:
                raise PeerAuthError("replay or sequence gap")
            if prev != expected_prev or not _sha(head):
                raise PeerAuthError("origin fork or invalid hash")
            expected_seq, expected_prev = seq + 1, head
        return {"peer_id": peer, "seq": expected_seq - 1, "hash": expected_prev,
                "previous_seq": cur["seq"], "previous_hash": cur["hash"], "duplicate": False}

    def commit(self, proposal: dict) -> None:
        """Persist a verified cursor only after caller's import transaction succeeds."""
        peer = proposal.get("peer_id")
        current = self._cursors.get(peer, self.checkpoints.get(peer))
        if current is None or current.get("seq") != proposal.get("previous_seq") or current.get("hash") != proposal.get("previous_hash"):
            # Repeated delivery of the exact committed batch is a successful no-op.
            if (proposal.get("duplicate") is True and current is not None
                    and current.get("seq") == proposal.get("seq")
                    and current.get("hash") == proposal.get("hash")):
                return
            raise PeerAuthError("cursor changed; re-verify batch")
        if proposal.get("duplicate") is True:
            return
        data = dict(self._cursors)
        next_anchor = {"seq": proposal["seq"], "hash": proposal["hash"]}
        expected_anchor = {"seq": proposal["previous_seq"], "hash": proposal["previous_hash"]}
        # Advance the independent anti-rollback authority first. If local cursor
        # persistence then fails, startup repairs the stale cursor from this anchor.
        self.cursor_anchor.advance_anchor(peer, expected_anchor, next_anchor)
        data[peer] = next_anchor
        self._persist(data)
        self._cursors = data
