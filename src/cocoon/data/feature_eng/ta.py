"""Technical-analysis features. DOCUMENT.md §F3 (TA catalogue).

All ratios are price-relative (divided by close) so features are
comparable across symbols with different price scales — the model never
sees absolute price levels.
"""

from __future__ import annotations

import polars as pl

from cocoon.core.interfaces.feature_fn import FeatureParams
from cocoon.data.feature_eng.base import ExprFeature

_EPS = 1e-12


class EmaDeviation(ExprFeature):
    """(close - EMA(period)) / close — signed relative distance from the
    exponential moving average."""

    def __init__(self, period: int, params: FeatureParams | None = None) -> None:
        super().__init__(params)
        self._period = period

    @property
    def name(self) -> str:
        return f"ema_dev_{self._period}"

    def expr(self, params: FeatureParams) -> pl.Expr:
        close = pl.col("close")
        ema = close.ewm_mean(span=self._period, adjust=False)
        return (close - ema) / close


class Rsi14(ExprFeature):
    @property
    def name(self) -> str:
        return "rsi_14"

    def expr(self, params: FeatureParams) -> pl.Expr:
        delta = pl.col("close").diff().fill_null(0.0)
        avg_gain = delta.clip(lower_bound=0).ewm_mean(alpha=1 / 14, adjust=False)
        avg_loss = (-delta).clip(lower_bound=0).ewm_mean(alpha=1 / 14, adjust=False)
        rs = avg_gain / (avg_loss + _EPS)
        return 100.0 - 100.0 / (1.0 + rs)


class Atr14Rel(ExprFeature):
    """Wilder ATR(14) divided by close. Multiplying by close recovers the
    ATR in price units — the trading layer relies on exactly that
    (`atr_price = feats["atr_14_rel"] * close`)."""

    @property
    def name(self) -> str:
        return "atr_14_rel"

    def expr(self, params: FeatureParams) -> pl.Expr:
        high, low, close = pl.col("high"), pl.col("low"), pl.col("close")
        prev_close = close.shift(1)
        true_range = pl.max_horizontal(
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ).fill_null(high - low)
        atr = true_range.ewm_mean(alpha=1 / 14, adjust=False)
        return atr / close


class BbPctB20(ExprFeature):
    """Bollinger %B over 20 bars: 0 at the lower band, 1 at the upper.
    0.5 (mid) when the band width is zero (flat price)."""

    @property
    def name(self) -> str:
        return "bb_pct_b_20"

    def expr(self, params: FeatureParams) -> pl.Expr:
        close = pl.col("close")
        mean = close.rolling_mean(20, min_periods=1)
        std = close.rolling_std(20, min_periods=2).fill_null(0.0)
        lower = mean - 2.0 * std
        return (
            pl.when(std > 0)
            .then((close - lower) / (4.0 * std))
            .otherwise(0.5)
        )


class MacdHistRel(ExprFeature):
    """MACD(12,26,9) histogram divided by close."""

    @property
    def name(self) -> str:
        return "macd_hist_rel"

    def expr(self, params: FeatureParams) -> pl.Expr:
        close = pl.col("close")
        macd = close.ewm_mean(span=12, adjust=False) - close.ewm_mean(
            span=26, adjust=False
        )
        signal = macd.ewm_mean(span=9, adjust=False)
        return (macd - signal) / close
