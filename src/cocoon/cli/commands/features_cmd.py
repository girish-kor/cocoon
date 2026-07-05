"""features command group. DOCUMENT.md §10, §F3/F4."""

from __future__ import annotations

import typer

from cocoon.cli import console, get_context, guard, output_obj, output_rows
from cocoon.data.feature_eng.engine import FeatureEngine, build_feature_catalogue

app = typer.Typer(help="Feature engineering", no_args_is_help=True)


@app.command()
@guard
def build(
    ctx: typer.Context,
    symbol: str = typer.Option(..., "--symbol"),
    tf: str = typer.Option(..., "--tf"),
    from_date: str = typer.Option(None, "--from"),
    to_date: str = typer.Option(None, "--to"),
) -> None:
    app_ctx = get_context(ctx)
    md = app_ctx.market_data()
    frame = md.load_cache(symbol, tf)
    if frame.height == 0:
        console.print(f"[yellow]no cached bars for {symbol} {tf}[/]")
        raise typer.Exit(0)
    engine = FeatureEngine()
    engine.register_all(build_feature_catalogue(app_ctx.config.feature_engineering))
    featured = engine.compute_frame(frame)
    out_dir = app_ctx.data_dir / "features" / symbol
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{tf}.parquet"
    featured.write_parquet(out_path)
    output_obj(
        ctx,
        {"symbol": symbol, "tf": tf, "rows": featured.height, "features": len(engine.feature_names), "path": str(out_path)},
        title="features built",
    )


@app.command(name="list")
@guard
def list_features(ctx: typer.Context) -> None:
    app_ctx = get_context(ctx)
    engine = FeatureEngine()
    engine.register_all(build_feature_catalogue(app_ctx.config.feature_engineering))
    rows = [{"name": n} for n in engine.feature_names]
    output_rows(ctx, rows, title="registered FeatureFn catalogue")
