"""Bounded in-process request limiting for the loopback HG API."""
from __future__ import annotations

import math
import threading
import time


class FixedWindowRateLimiter:
    """Thread-safe fixed-window limiter with bounded per-client state."""

    def __init__(self, limit: int, window_seconds: float, max_clients: int = 1024):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        if isinstance(window_seconds, bool) or not isinstance(window_seconds, (int, float)) or window_seconds < 1:
            raise ValueError("window_seconds must be at least one second")
        if isinstance(max_clients, bool) or not isinstance(max_clients, int) or max_clients < 1:
            raise ValueError("max_clients must be a positive integer")
        self.limit = limit
        self.window_seconds = float(window_seconds)
        self.max_clients = max_clients
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[float, int]] = {}

    def allow(self, client_key: str) -> tuple[bool, int]:
        now = time.monotonic()
        key = str(client_key)
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None or now - bucket[0] >= self.window_seconds:
                if bucket is None and len(self._buckets) >= self.max_clients:
                    expired = [k for k, (start, _) in self._buckets.items()
                               if now - start >= self.window_seconds]
                    for old_key in expired:
                        self._buckets.pop(old_key, None)
                    if len(self._buckets) >= self.max_clients:
                        oldest = min(self._buckets, key=lambda k: self._buckets[k][0])
                        self._buckets.pop(oldest, None)
                self._buckets[key] = (now, 1)
                return True, 0
            start, count = bucket
            if count >= self.limit:
                return False, max(1, math.ceil(self.window_seconds - (now - start)))
            self._buckets[key] = (start, count + 1)
            return True, 0
