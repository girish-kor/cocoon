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
    model_version: str = typer.Option(..., "--model-version", help="Registry run_id, e.g. lightgbm_0e80d8aeb573"),
    symbols: str = typer.Option(..., "--symbols", help="Comma-separated, e.g. EURUSD,GBPUSD"),
    tf: str = typer.Option("M5", "--tf", help="Timeframe: M1|M5|M15|M30|H1|H4|D1"),
    from_date: str = typer.Option(None, "--from", help="Start date (UTC), e.g. 2024-03-01"),
    to_date: str = typer.Option(None, "--to", help="End date (UTC), e.g. 2024-05-01"),
    starting_equity: float = typer.Option(10_000.0, "--equity", help="Starting account equity"),
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
    skipped: list[str] = []
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
            skipped.append(symbol)
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
    result_row = {"backtest_id": bt_id, "total_trades": payload["total_trades"], "total_pnl": payload["total_pnl"]}
    if skipped:
        result_row["skipped (too few bars)"] = skipped
    output_obj(ctx, result_row, title="backtest complete")


# (csv_key, table label, format) in reading order: activity → result → risk.
_METRIC_ROWS = (
    ("n_trades", "trades", "int"),
    ("win_rate", "win rate", "pct1"),
    ("profit_factor", "profit factor", "2f"),
    ("avg_win", "avg win", "money"),
    ("avg_loss", "avg loss", "money"),
    ("gross_profit", "gross profit", "money"),
    ("gross_loss", "gross loss", "money"),
    ("expectancy", "expectancy / trade", "money"),
    ("total_pnl", "total pnl", "money"),
    ("final_equity", "final equity", "money"),
    ("max_drawdown", "max drawdown", "pct2"),
    ("sharpe", "sharpe", "2f"),
    ("signals", "signals", "int"),
    ("rejected", "rejected by risk", "int"),
)


def _fmt_metric(value, kind: str) -> str:
    if kind == "pct1":
        return f"{value * 100:.1f}%"
    if kind == "pct2":
        return f"{value * 100:.2f}%"
    if kind == "2f":
        return f"{value:.2f}"
    if kind == "money":
        return f"{value:,.2f}"
    return f"{value:,}" if abs(value) >= 10_000 else str(value)


def _detail_table(per_symbol: list[dict]):
    """Every metric for every symbol, transposed — metrics as rows, one
    column per symbol — so full detail fits any terminal width."""
    from rich.table import Table

    table = Table(
        box=None, show_edge=False, pad_edge=False,
        padding=(0, 2, 0, 0), header_style="dim cyan",
    )
    table.add_column("METRIC", style="dim cyan")
    ordered = sorted(per_symbol, key=lambda r: r["symbol"])
    for row in ordered:
        table.add_column(row["symbol"], justify="right")
    for key, label, kind in _METRIC_ROWS:
        table.add_row(label, *[_fmt_metric(row[key], kind) for row in ordered])
    return table


def _summary_rows(per_symbol: list[dict]) -> list[dict]:
    """Curated per-symbol view: scannable units (percentages, 2-dp money),
    ordered result → risk → activity, sized to fit an 80-column terminal.
    Full precision and every metric stay available via `--export csv|json`."""
    return [
        {
            "symbol": r["symbol"],
            "trades": r["n_trades"],
            "win %": round(r["win_rate"] * 100, 1),
            "PF": round(r["profit_factor"], 2),
            "pnl": round(r["total_pnl"], 2),
            "dd %": round(r["max_drawdown"] * 100, 2),
            "sharpe": round(r["sharpe"], 2),
            "sig": r["signals"],
            "rej": r["rejected"],
        }
        for r in sorted(per_symbol, key=lambda r: r["symbol"])
    ]


@app.command()
@guard
def report(
    ctx: typer.Context,
    backtest_id: str = typer.Argument(
        ..., help="bt_* id printed by `cocoon backtest run`"
    ),
    export: str = typer.Option(
        None,
        "--export",
        help="csv|json — full-precision export; csv shows a table on a "
        "terminal and raw CSV when redirected",
    ),
) -> None:
    app_ctx = get_context(ctx)
    path = _backtests_dir(app_ctx) / f"{backtest_id}.json"
    if not path.exists():
        output_obj(ctx, {"backtest_id": backtest_id, "found": False}, title="backtest report")
        raise typer.Exit(0)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if export == "json":
        console.print_json(json.dumps(payload, default=str))
        return
    if export == "csv":
        import csv
        import io
        import sys

        if sys.stdout.isatty():
            # Interactive terminal: a wrapped CSV dump is unreadable, so
            # render the same full detail as a table. Redirects and pipes
            # (`> report.csv`, `| jq`) still get raw CSV below.
            from rich.padding import Padding
            from rich.text import Text

            console.print(Text("backtest metrics — full detail", style="bold cyan"))
            console.print(Padding(_detail_table(payload["per_symbol"]), (0, 0, 0, 2)))
            return

        buf = io.StringIO()
        rows = payload["per_symbol"]
        if rows:
            # 6 significant digits: still machine-parseable, no 16-digit noise.
            trimmed = [
                {
                    k: (format(v, ".6g") if isinstance(v, float) else v)
                    for k, v in row.items()
                }
                for row in rows
            ]
            writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(trimmed)
        # print(), not console.print(): rich wraps at terminal width, which
        # corrupts CSV lines when the output is redirected to a file.
        print(buf.getvalue(), end="")
        return
    if app_ctx.options.output == "json":
        console.print_json(json.dumps(payload, default=str))
        return
    output_obj(
        ctx,
        {k: v for k, v in payload.items() if k != "per_symbol"},
        title=f"backtest {backtest_id}",
    )
    from cocoon.cli import output_rows

    output_rows(ctx, _summary_rows(payload["per_symbol"]), title="per-symbol metrics")
