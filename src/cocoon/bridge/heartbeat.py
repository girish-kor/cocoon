"""Heartbeat monitor. DOCUMENT.md §13.4, §7.2.

Tracks the last-received EA heartbeat; `heartbeat_miss_threshold`
consecutive misses (each `heartbeat_interval_ms` wide) is what triggers the
SAFE_HALT transition (§7.2). Pure bookkeeping — the transition itself is
fired by whoever owns the state machine.
"""

from __future__ import annotations

import threading
import time
from typing import Callable


def _default_clock() -> int:
    return int(time.time() * 1000)


class HeartbeatMonitor:
    def __init__(
        self,
        *,
        interval_ms: int,
        miss_threshold: int,
        clock: Callable[[], int] = _default_clock,
    ) -> None:
        self._interval = interval_ms
        self._threshold = miss_threshold
        self._clock = clock
        self._lock = threading.RLock()
        self._last_ms: int | None = None

    def on_heartbeat(self, ts_unix_ms: int | None = None) -> None:
        with self._lock:
            self._last_ms = ts_unix_ms if ts_unix_ms is not None else self._clock()

    @property
    def last_heartbeat_ms(self) -> int | None:
        with self._lock:
            return self._last_ms

    def missed_count(self) -> int:
        with self._lock:
            if self._last_ms is None:
                return 0
            elapsed = self._clock() - self._last_ms
            if elapsed <= 0:
                return 0
            return int(elapsed // self._interval)

    def is_stale(self) -> bool:
        return self.missed_count() >= self._threshold
