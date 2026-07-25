"""Context flag features. DOCUMENT.md §F3 (context catalogue).

Session windows are fixed UTC approximations (DST is intentionally
ignored — a fixed mapping is deterministic and reproducible, §15.1):
Sydney 21:00–06:00, Tokyo 00:00–09:00, London 07:00–16:00,
New York 12:00–21:00. Day-of-week is derived from the epoch day index
(1970-01-01 was a Thursday), Monday = 0.
"""

from __future__ import annotations

import polars as pl

from cocoon.core.interfaces.feature_fn import FeatureParams
from cocoon.data.feature_eng.base import ExprFeature

_MS_PER_HOUR = 3_600_000
_MS_PER_DAY = 86_400_000

SESSION_WINDOWS_UTC: dict[str, tuple[int, int]] = {
    "sydney": (21, 6),
    "tokyo": (0, 9),
    "london": (7, 16),
    "newyork": (12, 21),
}

DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _hour_utc() -> pl.Expr:
    return (pl.col("ts_unix_ms") // _MS_PER_HOUR) % 24


class SessionFlag(ExprFeature):
    def __init__(self, session: str, params: FeatureParams | None = None) -> None:
        super().__init__(params)
        if session not in SESSION_WINDOWS_UTC:
            raise ValueError(f"Unknown session '{session}'")
        self._session = session

    @property
    def name(self) -> str:
        return f"session_{self._session}"

    def expr(self, params: FeatureParams) -> pl.Expr:
        start, end = SESSION_WINDOWS_UTC[self._session]
        hour = _hour_utc()
        if start < end:
            in_session = (hour >= start) & (hour < end)
        else:  # window wraps midnight (Sydney)
            in_session = (hour >= start) | (hour < end)
        return in_session.cast(pl.Float64)


class DayOfWeekFlag(ExprFeature):
    def __init__(self, day_index: int, params: FeatureParams | None = None) -> None:
        super().__init__(params)
        if not 0 <= day_index <= 6:
            raise ValueError(f"day_index must be 0..6 (Mon..Sun), got {day_index}")
        self._day_index = day_index

    @property
    def name(self) -> str:
        return f"dow_{DAY_NAMES[self._day_index]}"

    def expr(self, params: FeatureParams) -> pl.Expr:
        # epoch day 0 (1970-01-01) was a Thursday; +3 rebases to Monday=0.
        dow = ((pl.col("ts_unix_ms") // _MS_PER_DAY) + 3) % 7
        return (dow == self._day_index).cast(pl.Float64)
