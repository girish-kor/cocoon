"""Forward-return labelling. DOCUMENT.md §F5, §7.3.

This is the ONLY place in the data layer allowed to look forward: labels
are the training target, so a negative shift here is the point, not a
leak. The §7.3 no-negative-shift rule is scoped to `data/feature_eng/`
precisely so labelling can live outside it. Rows whose label window runs
past the end of the frame are dropped, never zero-filled — a partial
window would be a silently wrong label.
"""

from __future__ import annotations

import polars as pl


def forward_return_labels(
    frame: pl.DataFrame,
    *,
    label_horizon: int,
    deadband_bps: float = 0.0,
) -> pl.DataFrame:
    """Append `fwd_return` and `label` (+1 / -1 / 0) columns and drop the
    trailing rows without a full `label_horizon`-bar window. Returns
    within ±deadband_bps (basis points) of zero are labelled 0
    (neutral); the training layer drops those rows."""
    if label_horizon <= 0:
        raise ValueError(f"label_horizon must be positive, got {label_horizon}")
    close = pl.col("close")
    fwd_return = (close.shift(-label_horizon) / close) - 1.0
    deadband = deadband_bps * 1e-4
    label = (
        pl.when(fwd_return.abs() <= deadband)
        .then(0)
        .otherwise(fwd_return.sign().cast(pl.Int64))
        .cast(pl.Int64)
    )
    labelled = frame.with_columns(
        fwd_return.alias("fwd_return"),
        label.alias("label"),
    )
    return labelled.filter(pl.col("fwd_return").is_not_null())
