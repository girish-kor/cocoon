"""Idempotency. DOCUMENT.md §9.5.

`idempotency_key = sha256(symbol + direction + signal_ts + model_version_hash)`.
A TTL-bounded local set of recently-submitted keys short-circuits a retry
with a duplicate key to a no-op returning the cached result — this, not the
retry-count limit alone, is what prevents the ambiguous-network-failure
double-order.
"""

from __future__ import annotations

import hashlib
import threading
import time
from typing import Callable

from cocoon.core.interfaces.broker_adapter import OrderDirection, OrderResult


def make_idempotency_key(
    *, symbol: str, direction: OrderDirection, signal_ts_unix_ms: int, model_version_hash: str
) -> str:
    raw = f"{symbol}|{direction.value}|{signal_ts_unix_ms}|{model_version_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _default_clock() -> float:
    return time.time()


class IdempotencyCache:
    def __init__(
        self, *, ttl_sec: int, clock: Callable[[], float] = _default_clock
    ) -> None:
        self._ttl = ttl_sec
        self._clock = clock
        self._lock = threading.RLock()
        self._entries: dict[str, tuple[float, OrderResult]] = {}

    def _evict(self, now: float) -> None:
        expired = [k for k, (ts, _) in self._entries.items() if now - ts > self._ttl]
        for k in expired:
            del self._entries[k]

    def get(self, key: str) -> OrderResult | None:
        with self._lock:
            now = self._clock()
            self._evict(now)
            entry = self._entries.get(key)
            return entry[1] if entry else None

    def put(self, key: str, result: OrderResult) -> None:
        with self._lock:
            self._entries[key] = (self._clock(), result)

    def contains(self, key: str) -> bool:
        return self.get(key) is not None

    def __len__(self) -> int:
        with self._lock:
            self._evict(self._clock())
            return len(self._entries)
