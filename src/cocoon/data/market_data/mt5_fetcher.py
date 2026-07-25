"""MetaTrader 5 history fetcher. DOCUMENT.md §F1, §13.

The `MetaTrader5` Python package is Windows-only and intentionally NOT a
declared dependency (pyproject) — the offline path (`cocoon data import`)
must work without it. It is imported lazily inside `MT5Fetcher.connect`
so that merely importing this module (for `to_datetime_utc` or
`TIMEFRAME_SECONDS`) never requires a terminal install.
"""

from __future__ import annotations

from datetime import datetime, timezone

import polars as pl

from cocoon.core.errors.exceptions import DataError, MT5ConnectTimeoutError
from cocoon.data.market_data.ring_buffer import BAR_SCHEMA

TIMEFRAME_SECONDS: dict[str, int] = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
    "W1": 604800,
    "MN1": 2592000,
}

_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d",
)


def to_datetime_utc(value: str) -> datetime:
    """Parse a CLI date/datetime string to a tz-aware UTC datetime.

    Accepts ISO-style dates ("2024-01-01", "2024-01-01 12:30") and the
    MetaTrader dotted form ("2024.01.01")."""
    text = str(value).strip().replace(".", "-")
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise DataError(
        "Unparseable date/datetime string",
        context={"value": value, "accepted": list(_DATETIME_FORMATS)},
    )


class MT5Fetcher:
    """Thin wrapper over MetaTrader5.copy_rates_range that emits
    BAR_SCHEMA frames. Connects lazily on first fetch."""

    def __init__(self, *, terminal_path: str | None = None) -> None:
        self._terminal_path = terminal_path
        self._mt5 = None

    def _ensure_connected(self):
        if self._mt5 is not None:
            return self._mt5
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise DataError(
                "MetaTrader5 package is not installed; use "
                "`cocoon data import` to seed the cache from a file instead",
                context={"hint": "pip install MetaTrader5 (Windows only)"},
            ) from exc
        kwargs = {}
        if self._terminal_path:
            kwargs["path"] = self._terminal_path
        if not mt5.initialize(**kwargs):
            code, message = mt5.last_error()
            raise MT5ConnectTimeoutError(
                "MetaTrader5 terminal initialisation failed",
                context={
                    "terminal_path": self._terminal_path,
                    "mt5_error_code": code,
                    "mt5_error": message,
                },
            )
        self._mt5 = mt5
        return mt5

    def fetch(
        self,
        symbol: str,
        timeframe: str,
        from_dt: datetime,
        to_dt: datetime,
    ) -> pl.DataFrame:
        if timeframe not in TIMEFRAME_SECONDS:
            raise DataError(
                "Unknown timeframe",
                context={"timeframe": timeframe, "known": list(TIMEFRAME_SECONDS)},
            )
        mt5 = self._ensure_connected()
        tf_const = getattr(mt5, f"TIMEFRAME_{timeframe}")
        rates = mt5.copy_rates_range(symbol, tf_const, from_dt, to_dt)
        if rates is None:
            code, message = mt5.last_error()
            raise DataError(
                "MetaTrader5 returned no data for range",
                context={
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "from": from_dt.isoformat(),
                    "to": to_dt.isoformat(),
                    "mt5_error_code": code,
                    "mt5_error": message,
                },
            )
        raw = pl.from_numpy(rates)
        return raw.select(
            (pl.col("time").cast(pl.Int64) * 1000).alias("ts_unix_ms"),
            pl.col("open").cast(pl.Float64),
            pl.col("high").cast(pl.Float64),
            pl.col("low").cast(pl.Float64),
            pl.col("close").cast(pl.Float64),
            pl.col("tick_volume").cast(pl.Float64).alias("volume"),
        ).select(list(BAR_SCHEMA.keys()))

    def shutdown(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()
            self._mt5 = None
