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


_SMC_FEATURES = frozenset(
    {"bos", "choch", "order_block", "fvg", "liquidity_sweep", "premium_discount_zone"}
)
_OSCILLATOR_FEATURES = frozenset({"rsi_14", "atr_14_rel", "bb_pct_b_20", "macd_hist_rel"})


def _feature_category(name: str) -> str:
    if name in _SMC_FEATURES:
        return "smart money concepts"
    if name.startswith("ema_dev_"):
        return "trend"
    if name in _OSCILLATOR_FEATURES:
        return "oscillator"
    if name.startswith("session_"):
        return "session flag"
    if name.startswith("dow_"):
        return "day-of-week flag"
    return "plugin"


@app.command(name="list")
@guard
def list_features(ctx: typer.Context) -> None:
    app_ctx = get_context(ctx)
    engine = FeatureEngine()
    engine.register_all(build_feature_catalogue(app_ctx.config.feature_engineering))
    # Catalogue order is the registration order — the exact column order of
    # every dataset and model feature vector — so it is preserved, not
    # re-sorted; the index column makes that ordinal explicit.
    rows = [
        {"#": i, "name": name, "category": _feature_category(name)}
        for i, name in enumerate(engine.feature_names, start=1)
    ]
    output_rows(ctx, rows, title="registered FeatureFn catalogue")
