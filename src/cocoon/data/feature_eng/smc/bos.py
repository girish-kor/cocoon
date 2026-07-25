"""Break of Structure. DOCUMENT.md §F3 (SMC catalogue)."""

from __future__ import annotations

import polars as pl

from cocoon.core.interfaces.feature_fn import FeatureParams
from cocoon.data.feature_eng.base import ExprFeature, _smc, bos_expr


class BreakOfStructure(ExprFeature):
    """+1 when close breaks above the last confirmed fractal swing high,
    -1 when it breaks below the last swing low, else 0."""

    @property
    def name(self) -> str:
        return "bos"

    def expr(self, params: FeatureParams) -> pl.Expr:
        return bos_expr(_smc(params).fractal_n)
