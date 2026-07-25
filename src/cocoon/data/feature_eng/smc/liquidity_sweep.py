"""Liquidity Sweep. DOCUMENT.md §F3 (SMC catalogue)."""

from __future__ import annotations

import polars as pl

from cocoon.core.interfaces.feature_fn import FeatureParams
from cocoon.data.feature_eng.base import (
    ExprFeature,
    _smc,
    swing_high_expr,
    swing_low_expr,
)

_PIP = 0.0001


class LiquiditySweep(ExprFeature):
    """Wick through resting liquidity followed by a close back inside:
    -1 when the high reaches the last swing high (within eq_tol_pips)
    but the bar closes back below it (buy-side liquidity swept, bearish),
    +1 for the sell-side mirror. The signal persists for
    `sweep_confirm_bars` bars so the model sees the sweep during its
    reaction window, not only on the single sweep bar."""

    @property
    def name(self) -> str:
        return "liquidity_sweep"

    def expr(self, params: FeatureParams) -> pl.Expr:
        smc = _smc(params)
        tol = smc.eq_tol_pips * _PIP
        high_level = swing_high_expr(smc.fractal_n)
        low_level = swing_low_expr(smc.fractal_n)
        swept_highs = (pl.col("high") >= high_level - tol) & (
            pl.col("close") < high_level
        )
        swept_lows = (pl.col("low") <= low_level + tol) & (
            pl.col("close") > low_level
        )
        window = smc.sweep_confirm_bars
        recent_high_sweep = (
            swept_highs.cast(pl.Float64).fill_null(0.0).rolling_max(window, min_periods=1)
        )
        recent_low_sweep = (
            swept_lows.cast(pl.Float64).fill_null(0.0).rolling_max(window, min_periods=1)
        )
        return recent_low_sweep - recent_high_sweep
