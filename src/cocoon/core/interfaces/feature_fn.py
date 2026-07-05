"""FeatureFn interface. Authoritative source: DOCUMENT.md §7.3, §12, §18.

The leakage-prevention guarantee is an argument-passing guarantee, not a
lint rule: `FeatureEngine.compute()` (data/feature_eng/engine.py, L1)
slices the frame to `frame.slice(0, t_index + 1)` BEFORE calling
`FeatureFn.compute`. A conforming FeatureFn physically cannot read rows
beyond `t_index` because they do not exist in the object it receives.

This interface lives in core/interfaces (L0) — per §18, every
core/interfaces/*.py defines an abc.ABC, and concrete implementations
(data/feature_eng/smc/bos.py etc.) are wired only at the composition
root, never imported directly by consumers above L1.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import polars as pl


@dataclass(frozen=True)
class FeatureParams:
    """Base class for per-feature parameter bundles. Concrete FeatureFns
    subclass this with their own frozen dataclass, e.g.:

        @dataclass(frozen=True)
        class BosParams(FeatureParams):
            fractal_n: int = 5
    """

    extra: dict[str, Any] = field(default_factory=dict)


class FeatureFn(ABC):
    """`(frame: pl.LazyFrame, t_index: int, params: FeatureParams) -> pl.Series`

    Contract:
      - `frame` is ALREADY sliced to `[0, t_index]` inclusive by the
        caller (FeatureEngine). Implementations must not assume they
        can request more rows.
      - `frame` must never be indexed with a negative `.shift()`
        argument, and no `.shift()` with a negative argument is
        permitted anywhere under `data/feature_eng/` (§7.3, enforced by
        the static rule referenced there; this interface additionally
        raises at runtime if a subclass reports a negative shift via
        `max_forward_shift`, as a second, independent enforcement
        layer).
      - Output `pl.Series` must have length `t_index + 1` (one value per
        row up to and including `t_index`), aligned index-for-index with
        the input slice.
    """

    #: Must be 0 for every conforming FeatureFn. Exists as an explicit,
    #: introspectable declaration (rather than relying purely on the
    #: slicing guarantee) so FeatureEngine can assert it before ever
    #: calling `compute`, catching a misbehaving FeatureFn at
    #: registration time instead of at first use.
    max_forward_shift: int = 0

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def compute(
        self, frame: pl.LazyFrame, t_index: int, params: FeatureParams
    ) -> pl.Series:
        ...

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.max_forward_shift > 0:
            raise TypeError(
                f"{cls.__name__}.max_forward_shift must be <= 0; "
                f"positive forward shift violates the point-in-time-safe "
                f"guarantee in DOCUMENT.md §7.3"
            )
