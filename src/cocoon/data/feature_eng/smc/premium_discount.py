"""Premium/Discount zone. DOCUMENT.md §F3 (SMC catalogue)."""

from __future__ import annotations

import polars as pl

from cocoon.core.interfaces.feature_fn import FeatureParams
from cocoon.data.feature_eng.base import (
    ExprFeature,
    _smc,
    swing_high_expr,
    swing_low_expr,
)


class PremiumDiscountZone(ExprFeature):
    """Position of the close within the current dealing range (last
    confirmed swing low → swing high), rescaled to [-1, +1]: +1 at the
    top of the range (premium), -1 at the bottom (discount), 0 at
    equilibrium or when no range exists yet."""

    @property
    def name(self) -> str:
        return "premium_discount_zone"

    def expr(self, params: FeatureParams) -> pl.Expr:
        smc = _smc(params)
        high_level = swing_high_expr(smc.fractal_n)
        low_level = swing_low_expr(smc.fractal_n)
        range_ = high_level - low_level
        position = ((pl.col("close") - low_level) / range_ - 0.5) * 2.0
        return (
            pl.when(range_ > 0)
            .then(position.clip(-1.0, 1.0))
            .otherwise(0.0)
        )
