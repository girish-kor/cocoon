"""backtest command group. DOCUMENT.md §10, §15."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import typer

from cocoon.cli import console, get_context, guard, output_obj

app = typer.Typer(help="Backtesting", no_args_is_help=True)


def _backtests_dir(app_ctx) -> Path:
    d = app_ctx.data_dir / "backtests"
    d.mkdir(parents=True, exist_ok=True)
    return d


@app.command()
@guard
def run(
    ctx: typer.Context,
    model_version: str = typer.Option(..., "--model-version"),
    symbols: str = typer.Option(..., "--symbols"),
    tf: str = typer.Option("M5", "--tf"),
    from_date: str = typer.Option(None, "--from"),
    to_date: str = typer.Option(None, "--to"),
    starting_equity: float = typer.Option(10_000.0, "--equity"),
) -> None:
    import polars as pl

    from cocoon.data.feature_eng.engine import FeatureEngine, build_feature_catalogue
    from cocoon.ml.inference.engine import InferenceEngine
    from cocoon.trading.backtest.event_engine import BacktestEventEngine

    app_ctx = get_context(ctx)
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    registry = app_ctx.registry()
    inference = InferenceEngine.from_registry(registry, model_version)
    fe = FeatureEngine()
    fe.register_all(build_feature_catalogue(app_ctx.config.feature_engineering))
    md = app_ctx.market_data()

    per_symbol = []
    all_pnls: list[float] = []
    for symbol in symbol_list:
        frame = md.load_cache(symbol, tf)
        if from_date:
            from cocoon.data.market_data.mt5_fetcher import to_datetime_utc

            lo = int(to_datetime_utc(from_date).timestamp() * 1000)
            frame = frame.filter(pl.col("ts_unix_ms") >= lo)
        if to_date:
            from cocoon.data.market_data.mt5_fetcher import to_datetime_utc

            hi = int(to_datetime_utc(to_date).timestamp() * 1000)
            frame = frame.filter(pl.col("ts_unix_ms") <= hi)
        if frame.height < 300:
            console.print(f"[yellow]skipping {symbol}: too few bars[/]")
            continue
        engine = BacktestEventEngine(
            feature_engine=fe,
            inference_engine=inference,
            risk_config=app_ctx.config.risk,
            order_config=app_ctx.config.order,
            starting_equity=starting_equity,
            slippage_pips=app_ctx.config.order.default_slippage_pips,
        )
        result = engine.run(symbol, frame)
        all_pnls.extend(result.trade_pnls)
        per_symbol.append({"symbol": symbol, **result.metrics.to_dict(), "signals": result.signals, "rejected": result.rejected})

    payload = {
        "model_version": model_version,
        "symbols": symbol_list,
        "timeframe": tf,
        "per_symbol": per_symbol,
        "total_trades": sum(p["n_trades"] for p in per_symbol),
        "total_pnl": sum(all_pnls),
    }
    bt_id = "bt_" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    payload["backtest_id"] = bt_id
    (_backtests_dir(app_ctx) / f"{bt_id}.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    output_obj(ctx, {"backtest_id": bt_id, "total_trades": payload["total_trades"], "total_pnl": payload["total_pnl"]}, title="backtest complete")


@app.command()
@guard
def report(
    ctx: typer.Context,
    backtest_id: str = typer.Argument(...),
    export: str = typer.Option(None, "--export", help="csv|json"),
) -> None:
    app_ctx = get_context(ctx)
    path = _backtests_dir(app_ctx) / f"{backtest_id}.json"
    if not path.exists():
        console.print(f"[yellow]no such backtest[/] {backtest_id}")
        raise typer.Exit(0)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if export == "json":
        console.print_json(json.dumps(payload, default=str))
        return
    if export == "csv":
        import csv
        import io

        buf = io.StringIO()
        rows = payload["per_symbol"]
        if rows:
            writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        console.print(buf.getvalue())
        return
    output_obj(ctx, {k: v for k, v in payload.items() if k != "per_symbol"}, title=f"backtest {backtest_id}")
    from cocoon.cli import output_rows

    output_rows(ctx, payload["per_symbol"], title="per-symbol metrics")
