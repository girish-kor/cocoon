"""Fair Value Gap. DOCUMENT.md §F3 (SMC catalogue)."""

from __future__ import annotations

import polars as pl

from cocoon.core.interfaces.feature_fn import FeatureParams
from cocoon.data.feature_eng.base import ExprFeature


class FairValueGap(ExprFeature):
    """Three-candle imbalance completed at the current bar: +1 when the
    current low gaps above the high two bars back (bullish FVG), -1 for
    the bearish mirror, else 0."""

    @property
    def name(self) -> str:
        return "fvg"

    def expr(self, params: FeatureParams) -> pl.Expr:
        bull = pl.col("low") > pl.col("high").shift(2)
        bear = pl.col("high") < pl.col("low").shift(2)
        return pl.when(bull).then(1.0).when(bear).then(-1.0).otherwise(0.0)
