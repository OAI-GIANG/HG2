"""Fail-closed bootstrap for candidate authenticated HG sync.

Only non-secret peer/checkpoint metadata is accepted here. Key bytes are obtained
through the injected KeyManagementInterface and are never read from config/files/env.
This module does not start a listener or create a second StateStore.
"""
from __future__ import annotations

import os
from typing import Mapping

from .phone_runtime import PhoneRuntime
from .sync_auth import AuthenticatedBatchGate, CursorAnchorInterface, KeyManagementInterface, PeerAuthError


class _RestrictedKeyProvider:
    """Enforce bootstrap's explicit peer->key_id allowlist before key lookup."""
    def __init__(self, delegate: KeyManagementInterface, allowed: Mapping[str, str]):
        self._delegate = delegate
        self._allowed = dict(allowed)

    def get_peer_key(self, peer_id: str, key_id: str) -> bytes | None:
        if self._allowed.get(peer_id) != key_id:
            return None
        return self._delegate.get_peer_key(peer_id, key_id)


def create_authenticated_runtime(*, state_dir: str, spool_dir: str,
                                 cursor_path: str, config: Mapping,
                                 key_provider: KeyManagementInterface,
                                 cursor_anchor: CursorAnchorInterface) -> PhoneRuntime:
    """Create a new runtime with authenticated sync configured, or fail closed.

    Required non-secret config:
      {"context_id": str, "trusted_peers": [
        {"peer_id": str, "key_id": str, "checkpoint": {"seq": int, "hash": str}}
      ]}
    `cursor_path` is receiver-owned durable metadata and must be outside state_dir.
    """
    if not isinstance(config, Mapping):
        raise ValueError("sync bootstrap config must be a mapping")
    context_id = config.get("context_id")
    peers = config.get("trusted_peers")
    if not isinstance(context_id, str) or not context_id.strip():
        raise ValueError("sync bootstrap context_id required")
    if not isinstance(peers, list) or not peers:
        raise ValueError("trusted_peers required; fail closed")
    if not callable(getattr(key_provider, "get_peer_key", None)):
        raise PeerAuthError("KeyManagementInterface required; fail closed")
    if not isinstance(state_dir, str) or not state_dir or not isinstance(spool_dir, str) or not spool_dir:
        raise ValueError("state_dir and spool_dir required")
    if not isinstance(cursor_path, str) or not cursor_path:
        raise ValueError("cursor_path required")

    checkpoints = {}
    allowed_keys = {}
    seen = set()
    for entry in peers:
        if not isinstance(entry, Mapping):
            raise ValueError("trusted peer entry must be a mapping")
        peer_id, key_id, checkpoint = entry.get("peer_id"), entry.get("key_id"), entry.get("checkpoint")
        if not isinstance(peer_id, str) or not peer_id.strip() or not isinstance(key_id, str) or not key_id.strip():
            raise ValueError("trusted peer_id and key_id required")
        if peer_id in seen:
            raise ValueError("duplicate trusted peer")
        if not isinstance(checkpoint, Mapping):
            raise ValueError("trusted checkpoint required")
        checkpoints[peer_id] = dict(checkpoint)
        allowed_keys[peer_id] = key_id
        seen.add(peer_id)

    state_real = os.path.realpath(state_dir)
    cursor_real = os.path.realpath(cursor_path)
    try:
        inside = os.path.commonpath((state_real, cursor_real)) == state_real
    except ValueError:
        inside = False
    if inside:
        raise ValueError("cursor_path must be outside StateStore directory")

    restricted_provider = _RestrictedKeyProvider(key_provider, allowed_keys)
    gate = AuthenticatedBatchGate(key_provider=restricted_provider, checkpoints=checkpoints,
                                  cursor_path=cursor_real, cursor_anchor=cursor_anchor)
    # Runtime is created only after non-secret trust metadata has passed validation.
    runtime = PhoneRuntime(state_dir=state_dir, sync_context_id=context_id,
                           sync_spool_dir=spool_dir, authenticated_sync_gate=gate)
    if runtime.sync_context is None or runtime.authenticated_sync_gate is not gate:
        raise RuntimeError("authenticated sync bootstrap invariant failed")
    if runtime.sync_context.store is not runtime.store:
        raise RuntimeError("bootstrap created more than one StateStore")
    if os.path.realpath(runtime.store.dir) != state_real:
        raise RuntimeError("runtime StateStore directory mismatch")
    return runtime
