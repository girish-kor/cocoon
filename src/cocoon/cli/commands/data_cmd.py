"""data command group. DOCUMENT.md §10, §F1."""

from __future__ import annotations

from pathlib import Path

import typer

from cocoon.cli import get_context, guard, output_obj, output_rows
from cocoon.core.errors.exceptions import DataError
from cocoon.data.market_data.mt5_fetcher import MT5Fetcher, to_datetime_utc

app = typer.Typer(help="Market data ingestion & cache", no_args_is_help=True)
cache_app = typer.Typer(help="Cache management", no_args_is_help=True)
app.add_typer(cache_app, name="cache")

_TS_FULL_ALIASES = ("ts_unix_ms", "timestamp", "datetime", "date_time", "time_msc")
_COL_ALIASES = {
    "open": ("open", "o", "<open>"),
    "high": ("high", "h", "<high>"),
    "low": ("low", "l", "<low>"),
    "close": ("close", "c", "<close>"),
    "volume": ("volume", "vol", "v", "tick_volume", "tickvol", "<tickvol>", "<vol>"),
}


def _normalize_ohlcv(path: Path):
    """Read a CSV/Parquet file and normalize it to the BAR_SCHEMA frame the
    cache expects: ts_unix_ms(int), open, high, low, close, volume(float).

    Accepts common column spellings (MT5 exports, generic OHLCV). The
    timestamp column may already be unix-ms, or a parseable date/datetime;
    a separate `date` + `time` pair is combined.
    """
    import polars as pl

    from cocoon.data.market_data.ring_buffer import BAR_SCHEMA

    if path.suffix.lower() == ".parquet":
        raw = pl.read_parquet(path)
    else:
        raw = pl.read_csv(path, try_parse_dates=False)

    lower = {c.lower().strip().strip("<>").strip(): c for c in raw.columns}

    def pick(aliases: tuple[str, ...]) -> str | None:
        for a in aliases:
            if a in lower:
                return lower[a]
        return None

    ohlc = {k: pick(v) for k, v in _COL_ALIASES.items()}
    missing = [k for k in ("open", "high", "low", "close") if ohlc[k] is None]
    if missing:
        raise DataError(
            "Import file is missing required OHLC columns",
            context={"missing": missing, "found": raw.columns, "path": str(path)},
        )

    ts_full = pick(_TS_FULL_ALIASES)
    has_date = "date" in lower
    has_time = "time" in lower
    if ts_full is not None and "ts_unix_ms" in lower and lower["ts_unix_ms"] == ts_full:
        ts_expr = pl.col(ts_full).cast(pl.Int64)
    elif ts_full is not None:
        ts_expr = _parse_ts(raw, ts_full)
    elif has_date and has_time:
        combined = raw[lower["date"]].cast(pl.Utf8) + " " + raw[lower["time"]].cast(pl.Utf8)
        raw = raw.with_columns(combined.alias("_dt"))
        ts_expr = _parse_ts(raw, "_dt")
    elif has_date:
        ts_expr = _parse_ts(raw, lower["date"])
    else:
        raise DataError(
            "Import file has no recognizable timestamp column",
            context={
                "looked_for": [*_TS_FULL_ALIASES, "date+time"],
                "found": raw.columns,
            },
        )

    vol_col = ohlc["volume"]
    vol_expr = pl.col(vol_col).cast(pl.Float64) if vol_col else pl.lit(0.0)

    frame = raw.select(
        ts_expr.alias("ts_unix_ms"),
        pl.col(ohlc["open"]).cast(pl.Float64).alias("open"),
        pl.col(ohlc["high"]).cast(pl.Float64).alias("high"),
        pl.col(ohlc["low"]).cast(pl.Float64).alias("low"),
        pl.col(ohlc["close"]).cast(pl.Float64).alias("close"),
        vol_expr.alias("volume"),
    ).drop_nulls(subset=["ts_unix_ms"])
    return frame.select(list(BAR_SCHEMA.keys()))


def _parse_ts(frame, col: str):
    import polars as pl

    dtype = frame.schema[col]
    if dtype.is_integer():
        s = frame[col]
        # heuristic: seconds vs milliseconds since epoch
        scale = 1 if int(s.max() or 0) > 10_000_000_000 else 1000
        return (pl.col(col).cast(pl.Int64) * scale).cast(pl.Int64)
    parsed = (
        pl.col(col)
        .cast(pl.Utf8)
        .str.replace_all(r"\.", "-")
        .str.to_datetime(strict=False, time_unit="ms")
    )
    return parsed.dt.epoch(time_unit="ms").cast(pl.Int64)


@app.command()
@guard
def fetch(
    ctx: typer.Context,
    symbol: str = typer.Option(..., "--symbol", help="e.g. EURUSD"),
    tf: str = typer.Option(..., "--tf", help="Timeframe: M1|M5|M15|M30|H1|H4|D1"),
    from_date: str = typer.Option(..., "--from", help="Start date (UTC), e.g. 2024-01-01"),
    to_date: str = typer.Option(..., "--to", help="End date (UTC), e.g. 2024-06-01"),
) -> None:
    app_ctx = get_context(ctx)
    if app_ctx.options.dry_run:
        output_obj(ctx, {"dry_run": True, "action": "fetch", "symbol": symbol, "tf": tf, "from": from_date, "to": to_date}, title="data fetch")
        return
    fetcher = MT5Fetcher(terminal_path=app_ctx.config.mt5.terminal_path)
    frame = fetcher.fetch(symbol, tf, to_datetime_utc(from_date), to_datetime_utc(to_date))
    path = app_ctx.market_data().store_frame(symbol, tf, frame)
    fetcher.shutdown()
    output_obj(ctx, {"symbol": symbol, "tf": tf, "bars": frame.height, "path": str(path)}, title="fetched")


@app.command(name="import")
@guard
def import_file(
    ctx: typer.Context,
    symbol: str = typer.Option(..., "--symbol", help="Symbol to file the bars under, e.g. EURUSD"),
    tf: str = typer.Option(..., "--tf", help="Timeframe to file the bars under, e.g. M5"),
    file: str = typer.Option(..., "--file", help="CSV or Parquet with OHLCV columns"),
) -> None:
    """Import OHLCV bars from a local CSV/Parquet file into the cache.

    Use this to seed data when MetaTrader5 live fetch is not available.
    """
    app_ctx = get_context(ctx)
    path = Path(file)
    if not path.exists():
        raise DataError("Import file not found", context={"path": str(path)})
    frame = _normalize_ohlcv(path)
    if frame.height == 0:
        raise DataError(
            "Import file produced zero usable rows", context={"path": str(path)}
        )
    if app_ctx.options.dry_run:
        output_obj(ctx, {"dry_run": True, "action": "import", "symbol": symbol, "tf": tf, "bars": frame.height}, title="data import")
        return
    stored = app_ctx.market_data().store_frame(symbol, tf, frame)
    output_obj(
        ctx,
        {"symbol": symbol, "tf": tf, "bars": frame.height, "path": str(stored)},
        title="imported",
    )


@app.command()
@guard
def status(ctx: typer.Context) -> None:
    app_ctx = get_context(ctx)
    rows = app_ctx.market_data().coverage_status()
    output_rows(ctx, rows, title="data coverage")


@cache_app.command("clear")
@guard
def cache_clear(
    ctx: typer.Context,
    symbol: str = typer.Option(None, "--symbol", help="Only this symbol; omit to clear everything"),
) -> None:
    app_ctx = get_context(ctx)
    removed = app_ctx.market_data().clear_cache(symbol)
    output_obj(ctx, {"symbol": symbol or "all", "files_removed": removed}, title="cache clear")


@cache_app.command("stats")
@guard
def cache_stats(ctx: typer.Context) -> None:
    app_ctx = get_context(ctx)
    output_obj(ctx, app_ctx.market_data().cache_stats(), title="cache stats")
