"""Order Block. DOCUMENT.md §F3 (SMC catalogue)."""

from __future__ import annotations

import polars as pl

from cocoon.core.interfaces.feature_fn import FeatureParams
from cocoon.data.feature_eng.base import ExprFeature, _smc, bos_expr


class OrderBlock(ExprFeature):
    """+1 while the close sits inside the body of the last opposing
    (bearish) candle that preceded the most recent bullish break of
    structure — the bullish order block — and -1 inside the bearish
    mirror. 0 when outside both zones or when the zones overlap
    ambiguously."""

    @property
    def name(self) -> str:
        return "order_block"

    def expr(self, params: FeatureParams) -> pl.Expr:
        open_ = pl.col("open")
        close = pl.col("close")
        bos = bos_expr(_smc(params).fractal_n)

        down_body_low = pl.when(close < open_).then(
            pl.min_horizontal(open_, close)
        ).forward_fill()
        down_body_high = pl.when(close < open_).then(
            pl.max_horizontal(open_, close)
        ).forward_fill()
        up_body_low = pl.when(close > open_).then(
            pl.min_horizontal(open_, close)
        ).forward_fill()
        up_body_high = pl.when(close > open_).then(
            pl.max_horizontal(open_, close)
        ).forward_fill()

        bull_ob_low = pl.when(bos == 1.0).then(down_body_low.shift(1)).forward_fill()
        bull_ob_high = pl.when(bos == 1.0).then(down_body_high.shift(1)).forward_fill()
        bear_ob_low = pl.when(bos == -1.0).then(up_body_low.shift(1)).forward_fill()
        bear_ob_high = pl.when(bos == -1.0).then(up_body_high.shift(1)).forward_fill()

        in_bull = (close >= bull_ob_low) & (close <= bull_ob_high)
        in_bear = (close >= bear_ob_low) & (close <= bear_ob_high)
        return (
            pl.when(in_bull & ~in_bear.fill_null(False))
            .then(1.0)
            .when(in_bear & ~in_bull.fill_null(False))
            .then(-1.0)
            .otherwise(0.0)
        )
