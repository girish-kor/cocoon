"""FeatureEngine + catalogue. DOCUMENT.md §7.3, §F3/F4.

The leakage-prevention guarantee is an argument-passing guarantee
(core/interfaces/feature_fn.py): `compute_point` slices the frame to
`[0, t_index]` BEFORE any FeatureFn runs, so a conforming FeatureFn
physically cannot read a future row. `compute_frame` exploits the same
causality in the other direction — because every feature is causal, one
full-frame pass produces at row i exactly what a per-slice compute at
t_index=i would, in O(n) instead of O(n²).

Warmup rows (rolling windows not yet filled) are neutral-filled with 0.0
rather than dropped: frame length in must equal frame length out, and 0
is the "no signal" value for every feature in the catalogue.
"""

from __future__ import annotations

from typing import Iterable

import polars as pl

from cocoon.core.errors.exceptions import FeatureLeakageGuardError
from cocoon.core.interfaces.feature_fn import FeatureFn, FeatureParams
from cocoon.data.feature_eng.base import SmcParams
from cocoon.data.feature_eng.context import DAY_NAMES, DayOfWeekFlag, SessionFlag
from cocoon.data.feature_eng.smc import (
    BreakOfStructure,
    ChangeOfCharacter,
    FairValueGap,
    LiquiditySweep,
    OrderBlock,
    PremiumDiscountZone,
)
from cocoon.data.feature_eng.ta import (
    Atr14Rel,
    BbPctB20,
    EmaDeviation,
    MacdHistRel,
    Rsi14,
)

EMA_DEVIATION_PERIODS = (20, 50, 100, 200)


def build_feature_catalogue(fe_config) -> list[FeatureFn]:
    """The 25 point-in-time-safe features, in catalogue order: 6 SMC,
    4 EMA deviations, 4 oscillators, 4 session flags, 7 day-of-week
    flags. `fe_config` is the resolved `feature_engineering` config
    section (FeatureEngineeringConfig)."""
    smc_params = SmcParams(
        fractal_n=fe_config.fractal_n,
        eq_tol_pips=fe_config.eq_tol_pips,
        sweep_confirm_bars=fe_config.sweep_confirm_bars,
        lookback_bars=fe_config.lookback_bars,
    )
    catalogue: list[FeatureFn] = [
        BreakOfStructure(smc_params),
        ChangeOfCharacter(smc_params),
        OrderBlock(smc_params),
        FairValueGap(smc_params),
        LiquiditySweep(smc_params),
        PremiumDiscountZone(smc_params),
        *(EmaDeviation(period) for period in EMA_DEVIATION_PERIODS),
        Rsi14(),
        Atr14Rel(),
        BbPctB20(),
        MacdHistRel(),
        *(SessionFlag(session) for session in ("sydney", "tokyo", "london", "newyork")),
        *(DayOfWeekFlag(i) for i in range(len(DAY_NAMES))),
    ]
    return catalogue


class FeatureEngine:
    def __init__(self) -> None:
        self._registered: list[tuple[FeatureFn, FeatureParams]] = []

    def register(self, fn: FeatureFn, params: FeatureParams | None = None) -> None:
        if not isinstance(fn, FeatureFn):
            raise TypeError(
                f"FeatureEngine.register expects a FeatureFn, got {type(fn).__name__}"
            )
        # Registration-time enforcement of the §7.3 causality declaration —
        # a misbehaving FeatureFn fails here, not at first use.
        if fn.max_forward_shift > 0:
            raise FeatureLeakageGuardError(
                "FeatureFn declares a positive forward shift",
                context={"feature": fn.name, "max_forward_shift": fn.max_forward_shift},
            )
        if fn.name in self.feature_names:
            raise ValueError(f"Feature '{fn.name}' is already registered")
        resolved: FeatureParams = (
            params
            if params is not None
            else getattr(fn, "params", None) or FeatureParams()
        )
        self._registered.append((fn, resolved))

    def register_all(self, fns: Iterable[FeatureFn]) -> None:
        for fn in fns:
            self.register(fn)

    @property
    def feature_names(self) -> list[str]:
        return [fn.name for fn, _ in self._registered]

    def compute_frame(self, frame: pl.DataFrame) -> pl.DataFrame:
        """Append all registered feature columns to `frame` in one causal
        full-frame pass."""
        if frame.height == 0:
            return frame.with_columns(
                [pl.lit(0.0).alias(name) for name in self.feature_names]
            )
        t_index = frame.height - 1
        lazy = frame.lazy()
        columns: list[pl.Series] = []
        for fn, params in self._registered:
            series = fn.compute(lazy, t_index, params)
            self._assert_length(fn, series, t_index)
            columns.append(
                series.rename(fn.name).fill_nan(0.0).fill_null(0.0)
            )
        return frame.with_columns(columns)

    def compute_point(self, window: pl.DataFrame, t_index: int) -> dict[str, float]:
        """Features for the single row `t_index`. The frame is sliced to
        `[0, t_index]` BEFORE any FeatureFn sees it (§7.3)."""
        if not 0 <= t_index < window.height:
            raise IndexError(
                f"t_index {t_index} out of range for window of {window.height} rows"
            )
        sliced = window.slice(0, t_index + 1)
        lazy = sliced.lazy()
        point: dict[str, float] = {}
        for fn, params in self._registered:
            series = fn.compute(lazy, t_index, params)
            self._assert_length(fn, series, t_index)
            value = series[-1]
            if value is None or (isinstance(value, float) and value != value):
                value = 0.0
            point[fn.name] = float(value)
        return point

    @staticmethod
    def _assert_length(fn: FeatureFn, series: pl.Series, t_index: int) -> None:
        if series.len() != t_index + 1:
            raise FeatureLeakageGuardError(
                "FeatureFn returned a series not aligned to its input slice",
                context={
                    "feature": fn.name,
                    "expected_len": t_index + 1,
                    "actual_len": series.len(),
                },
            )
