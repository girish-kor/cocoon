"""Change of Character. DOCUMENT.md §F3 (SMC catalogue)."""

from __future__ import annotations

import polars as pl

from cocoon.core.interfaces.feature_fn import FeatureParams
from cocoon.data.feature_eng.base import ExprFeature, _smc, bos_expr


class ChangeOfCharacter(ExprFeature):
    """A break of structure AGAINST the prevailing structure direction:
    +1 when a bullish break follows a bearish structure, -1 for the
    mirror. Plain with-trend breaks stay 0 (those are `bos`)."""

    @property
    def name(self) -> str:
        return "choch"

    def expr(self, params: FeatureParams) -> pl.Expr:
        bos = bos_expr(_smc(params).fractal_n)
        prev_direction = (
            pl.when(bos != 0.0).then(bos).otherwise(None).forward_fill().shift(1)
        )
        return (
            pl.when((bos == 1.0) & (prev_direction == -1.0))
            .then(1.0)
            .when((bos == -1.0) & (prev_direction == 1.0))
            .then(-1.0)
            .otherwise(0.0)
        )
