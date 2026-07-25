"""dataset command group. DOCUMENT.md §10, §F5."""

from __future__ import annotations

from dataclasses import asdict

import typer

from cocoon.cli import get_context, guard, output_obj, output_rows

app = typer.Typer(help="Dataset construction", no_args_is_help=True)


@app.command()
@guard
def build(
    ctx: typer.Context,
    symbols: str = typer.Option(..., "--symbols", help="Comma-separated, e.g. EURUSD,GBPUSD"),
    tf: str = typer.Option("M5", "--tf", help="Timeframe of the cached bars to build from"),
    label_horizon: int = typer.Option(..., "--label-horizon", help="Bars ahead for the forward-return label, e.g. 5"),
    deadband_bps: float = typer.Option(0.0, "--deadband-bps", help="Neutral band in basis points; returns within ±band are labelled 0"),
) -> None:
    app_ctx = get_context(ctx)
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    meta = app_ctx.dataset_builder().build(
        symbols=symbol_list,
        timeframe=tf,
        label_horizon=label_horizon,
        deadband_bps=deadband_bps,
    )
    output_obj(
        ctx,
        {"dataset_id": meta.dataset_id, "rows": meta.n_rows, "features": len(meta.feature_names), "path": meta.path},
        title="dataset built",
    )


@app.command(name="list")
@guard
def list_datasets(ctx: typer.Context) -> None:
    app_ctx = get_context(ctx)
    rows = [
        {"dataset_id": m.dataset_id, "symbols": ",".join(m.symbols), "tf": m.timeframe, "rows": m.n_rows, "horizon": m.label_horizon}
        for m in app_ctx.dataset_builder().list_datasets()
    ]
    output_rows(ctx, rows, title="datasets")


@app.command()
@guard
def describe(
    ctx: typer.Context,
    dataset_id: str = typer.Argument(..., help="ds_* id, as shown by `cocoon dataset list`"),
) -> None:
    app_ctx = get_context(ctx)
    meta = app_ctx.dataset_builder().describe(dataset_id)
    output_obj(ctx, asdict(meta), title=f"dataset {dataset_id}")
