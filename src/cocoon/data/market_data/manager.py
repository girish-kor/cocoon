"""Market data cache manager. DOCUMENT.md §F1, §7.1.

Owns the on-disk parquet cache (`data/raw/<symbol>/<tf>.parquet`) and the
in-memory per-stream ring buffers the live loop reads windows from. Stored
frames are deduplicated on timestamp (last write wins) and kept sorted, so
every consumer can assume strictly increasing `ts_unix_ms`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from cocoon.core.interfaces.broker_adapter import Bar
from cocoon.core.logging.setup import get_logger
from cocoon.data.market_data.ring_buffer import (
    BAR_SCHEMA,
    RingBuffer,
    empty_bar_frame,
)

_logger = get_logger(__name__)


def _iso_utc(ts_unix_ms: int) -> str:
    return datetime.fromtimestamp(ts_unix_ms / 1000.0, tz=timezone.utc).isoformat()


class MarketDataManager:
    def __init__(self, *, data_dir: str, buffer_capacity: int = 1000) -> None:
        self._data_dir = Path(data_dir)
        self._raw_dir = self._data_dir / "raw"
        self._buffer_capacity = buffer_capacity
        self._buffers: dict[tuple[str, str], RingBuffer] = {}

    def _cache_path(self, symbol: str, timeframe: str) -> Path:
        return self._raw_dir / symbol / f"{timeframe}.parquet"

    # -- persistent cache ---------------------------------------------------

    def store_frame(self, symbol: str, timeframe: str, frame: pl.DataFrame) -> Path:
        incoming = frame.select(
            [pl.col(name).cast(dtype) for name, dtype in BAR_SCHEMA.items()]
        )
        path = self._cache_path(symbol, timeframe)
        if path.exists():
            existing = pl.read_parquet(path)
            incoming = pl.concat([existing, incoming], how="vertical")
        merged = (
            incoming.unique(subset=["ts_unix_ms"], keep="last")
            .sort("ts_unix_ms")
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        merged.write_parquet(path)
        _logger.info(
            "cache_stored", symbol=symbol, timeframe=timeframe, bars=merged.height
        )
        return path

    def load_cache(self, symbol: str, timeframe: str) -> pl.DataFrame:
        path = self._cache_path(symbol, timeframe)
        if not path.exists():
            return empty_bar_frame()
        return pl.read_parquet(path).sort("ts_unix_ms")

    def coverage_status(self) -> list[dict]:
        rows: list[dict] = []
        if not self._raw_dir.exists():
            return rows
        for path in sorted(self._raw_dir.glob("*/*.parquet")):
            frame = pl.read_parquet(path, columns=["ts_unix_ms"])
            first_ts = int(frame["ts_unix_ms"].min()) if frame.height else None
            last_ts = int(frame["ts_unix_ms"].max()) if frame.height else None
            rows.append(
                {
                    "symbol": path.parent.name,
                    "tf": path.stem,
                    "bars": frame.height,
                    "first": _iso_utc(first_ts) if first_ts is not None else "",
                    "last": _iso_utc(last_ts) if last_ts is not None else "",
                }
            )
        return rows

    def clear_cache(self, symbol: str | None = None) -> int:
        if not self._raw_dir.exists():
            return 0
        pattern = f"{symbol}/*.parquet" if symbol else "*/*.parquet"
        removed = 0
        for path in list(self._raw_dir.glob(pattern)):
            path.unlink()
            removed += 1
        return removed

    def cache_stats(self) -> dict:
        files = list(self._raw_dir.glob("*/*.parquet")) if self._raw_dir.exists() else []
        return {
            "files": len(files),
            "total_bytes": sum(p.stat().st_size for p in files),
            "root": str(self._raw_dir),
        }

    # -- live window --------------------------------------------------------

    def _buffer(self, symbol: str, timeframe: str) -> RingBuffer:
        key = (symbol, timeframe)
        buffer = self._buffers.get(key)
        if buffer is None:
            buffer = RingBuffer(capacity=self._buffer_capacity)
            # Seed from the persistent cache so the live loop has feature
            # lookback from the first ingested bar, not after `capacity` bars.
            cached = self.load_cache(symbol, timeframe)
            if cached.height:
                buffer.extend_from_frame(cached.tail(self._buffer_capacity))
            self._buffers[key] = buffer
        return buffer

    def ingest_bar(self, bar: Bar, *, persist: bool = False) -> None:
        buffer = self._buffer(bar.symbol, bar.timeframe)
        buffer.append(bar)
        if persist:
            self.store_frame(bar.symbol, bar.timeframe, buffer.to_frame(last_n=1))

    def get_window(self, symbol: str, timeframe: str, lookback: int) -> pl.DataFrame:
        return self._buffer(symbol, timeframe).to_frame(last_n=lookback)
