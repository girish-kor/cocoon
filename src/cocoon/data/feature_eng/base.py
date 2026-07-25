"""Shared FeatureFn machinery. DOCUMENT.md §7.3, §F3.

Every concrete feature in this package is an `ExprFeature`: it declares a
single causal polars expression over the BAR_SCHEMA columns. Causality is
structural — the §7.3 rule that no negative `.shift()` may appear anywhere
under `data/feature_eng/` means every expression only ever references the
current row and rows before it, so one full-frame evaluation yields, at
each row i, exactly what a per-slice evaluation at t_index=i would.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass

import polars as pl

from cocoon.core.errors.exceptions import FeatureLeakageGuardError
from cocoon.core.interfaces.feature_fn import FeatureFn, FeatureParams


@dataclass(frozen=True)
class SmcParams(FeatureParams):
    """Parameter bundle for the Smart-Money-Concepts features, sourced
    from `feature_engineering` in the resolved config."""

    fractal_n: int = 5
    eq_tol_pips: float = 2.0
    sweep_confirm_bars: int = 3
    lookback_bars: int = 500


class ExprFeature(FeatureFn):
    def __init__(self, params: FeatureParams | None = None) -> None:
        self.params: FeatureParams = params if params is not None else FeatureParams()

    @abstractmethod
    def expr(self, params: FeatureParams) -> pl.Expr:
        ...

    def compute(
        self, frame: pl.LazyFrame, t_index: int, params: FeatureParams
    ) -> pl.Series:
        lazy = frame if isinstance(frame, pl.LazyFrame) else frame.lazy()
        series = (
            lazy.select(self.expr(params).cast(pl.Float64).alias(self.name))
            .collect()
            .to_series()
        )
        if series.len() != t_index + 1:
            raise FeatureLeakageGuardError(
                "FeatureFn output length does not match its input slice",
                context={
                    "feature": self.name,
                    "expected_len": t_index + 1,
                    "actual_len": series.len(),
                },
            )
        return series


def swing_high_expr(fractal_n: int) -> pl.Expr:
    """Most recent CONFIRMED fractal swing high as of each row. A pivot at
    bar t-n only exists once n bars have printed after it, so the value
    forward-filled here is knowable at row t — no lookahead."""
    window = 2 * fractal_n + 1
    pivot = pl.when(
        pl.col("high").shift(fractal_n) == pl.col("high").rolling_max(window)
    ).then(pl.col("high").shift(fractal_n))
    return pivot.forward_fill()


def swing_low_expr(fractal_n: int) -> pl.Expr:
    window = 2 * fractal_n + 1
    pivot = pl.when(
        pl.col("low").shift(fractal_n) == pl.col("low").rolling_min(window)
    ).then(pl.col("low").shift(fractal_n))
    return pivot.forward_fill()


def bos_expr(fractal_n: int) -> pl.Expr:
    """+1 the bar close first breaks above the last confirmed swing high,
    -1 on the mirrored break below the last swing low, else 0."""
    high_level = swing_high_expr(fractal_n)
    low_level = swing_low_expr(fractal_n)
    close = pl.col("close")
    bull = (close > high_level) & (close.shift(1) <= high_level.shift(1))
    bear = (close < low_level) & (close.shift(1) >= low_level.shift(1))
    return pl.when(bull).then(1.0).when(bear).then(-1.0).otherwise(0.0)


def _smc(params: FeatureParams) -> SmcParams:
    return params if isinstance(params, SmcParams) else SmcParams()
