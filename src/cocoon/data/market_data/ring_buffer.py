"""In-memory bar ring buffer. DOCUMENT.md §F1, §7.1.

BAR_SCHEMA is the single canonical bar layout: every frame that crosses a
module boundary (cache parquet, fetcher output, feature input) uses exactly
these columns in exactly this order, so schema drift is impossible to
introduce silently.
"""

from __future__ import annotations

from collections import deque

import polars as pl

from cocoon.core.interfaces.broker_adapter import Bar

BAR_SCHEMA: dict[str, pl.DataType] = {
    "ts_unix_ms": pl.Int64(),
    "open": pl.Float64(),
    "high": pl.Float64(),
    "low": pl.Float64(),
    "close": pl.Float64(),
    "volume": pl.Float64(),
}


def empty_bar_frame() -> pl.DataFrame:
    return pl.DataFrame(schema=BAR_SCHEMA)


class RingBuffer:
    """Fixed-capacity, append-only window of the most recent bars for one
    (symbol, timeframe) stream. Re-ingesting the current bar (same
    timestamp, e.g. an intrabar update) replaces the last entry instead of
    appending, so the buffer never holds two rows for one bar."""

    def __init__(self, capacity: int = 1000) -> None:
        if capacity <= 0:
            raise ValueError(f"RingBuffer capacity must be positive, got {capacity}")
        self._capacity = capacity
        self._rows: deque[tuple[int, float, float, float, float, float]] = deque(
            maxlen=capacity
        )

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        return len(self._rows)

    def append(self, bar: Bar) -> None:
        row = (
            int(bar.ts_unix_ms),
            float(bar.open),
            float(bar.high),
            float(bar.low),
            float(bar.close),
            float(bar.volume),
        )
        if self._rows and self._rows[-1][0] == row[0]:
            self._rows[-1] = row
        else:
            self._rows.append(row)

    def extend_from_frame(self, frame: pl.DataFrame) -> None:
        for row in frame.select(list(BAR_SCHEMA.keys())).iter_rows():
            ts, o, h, lo, c, v = row
            if self._rows and self._rows[-1][0] == int(ts):
                self._rows[-1] = (int(ts), o, h, lo, c, v)
            else:
                self._rows.append((int(ts), o, h, lo, c, v))

    def to_frame(self, last_n: int | None = None) -> pl.DataFrame:
        rows = list(self._rows)
        if last_n is not None:
            rows = rows[-last_n:]
        if not rows:
            return empty_bar_frame()
        return pl.DataFrame(
            rows, schema=BAR_SCHEMA, orient="row"
        )
