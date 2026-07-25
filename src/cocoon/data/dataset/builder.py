"""Dataset builder. DOCUMENT.md §F5, §15.1.

A dataset is features + forward-return labels for one or more symbols,
content-hashed into a deterministic `ds_<hash16>` id: the id is computed
from the build descriptor plus a canonical serialisation of the rows, so
the same cache contents and parameters always produce byte-identical ids
(§15.1 reproducibility). Metadata lives beside the parquet as
`<id>.json` so `list`/`describe` never need to read the data itself.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import polars as pl

from cocoon.core.errors.exceptions import DatasetIntegrityError
from cocoon.core.logging.setup import get_logger
from cocoon.data.feature_eng.engine import FeatureEngine, build_feature_catalogue
from cocoon.data.labeling import forward_return_labels
from cocoon.data.market_data.manager import MarketDataManager

_logger = get_logger(__name__)


@dataclass(frozen=True)
class DatasetMeta:
    dataset_id: str
    symbols: list[str] = field(default_factory=list)
    timeframe: str = "M5"
    label_horizon: int = 5
    deadband_bps: float = 0.0
    n_rows: int = 0
    feature_names: list[str] = field(default_factory=list)
    path: str = ""


class DatasetBuilder:
    def __init__(
        self,
        *,
        market_data: MarketDataManager,
        fe_config,
        data_dir: str,
    ) -> None:
        self._md = market_data
        self._fe_config = fe_config
        self._datasets_dir = Path(data_dir) / "datasets"

    def _meta_path(self, dataset_id: str) -> Path:
        return self._datasets_dir / f"{dataset_id}.json"

    def _parquet_path(self, dataset_id: str) -> Path:
        return self._datasets_dir / f"{dataset_id}.parquet"

    def build(
        self,
        *,
        symbols: list[str],
        timeframe: str,
        label_horizon: int,
        deadband_bps: float = 0.0,
    ) -> DatasetMeta:
        if not symbols:
            raise DatasetIntegrityError(
                "Dataset build requires at least one symbol",
                context={"symbols": symbols},
            )
        engine = FeatureEngine()
        engine.register_all(build_feature_catalogue(self._fe_config))
        feature_names = engine.feature_names

        parts: list[pl.DataFrame] = []
        for symbol in sorted(symbols):
            bars = self._md.load_cache(symbol, timeframe)
            if bars.height == 0:
                raise DatasetIntegrityError(
                    "No cached bars for symbol; run `cocoon data fetch` or "
                    "`cocoon data import` first",
                    context={"symbol": symbol, "timeframe": timeframe},
                )
            featured = engine.compute_frame(bars)
            labelled = forward_return_labels(
                featured, label_horizon=label_horizon, deadband_bps=deadband_bps
            )
            if labelled.height == 0:
                raise DatasetIntegrityError(
                    "Symbol has fewer bars than the label horizon",
                    context={
                        "symbol": symbol,
                        "bars": bars.height,
                        "label_horizon": label_horizon,
                    },
                )
            parts.append(
                labelled.select(
                    pl.lit(symbol).alias("symbol"),
                    pl.col("ts_unix_ms"),
                    *[pl.col(name) for name in feature_names],
                    pl.col("label"),
                )
            )

        frame = pl.concat(parts, how="vertical").sort(["symbol", "ts_unix_ms"])

        descriptor = {
            "symbols": sorted(symbols),
            "timeframe": timeframe,
            "label_horizon": label_horizon,
            "deadband_bps": deadband_bps,
            "feature_names": feature_names,
        }
        digest = hashlib.sha256()
        digest.update(json.dumps(descriptor, sort_keys=True).encode("utf-8"))
        digest.update(frame.write_csv().encode("utf-8"))
        dataset_id = f"ds_{digest.hexdigest()[:16]}"

        self._datasets_dir.mkdir(parents=True, exist_ok=True)
        parquet_path = self._parquet_path(dataset_id)
        frame.write_parquet(parquet_path)
        meta = DatasetMeta(
            dataset_id=dataset_id,
            symbols=sorted(symbols),
            timeframe=timeframe,
            label_horizon=label_horizon,
            deadband_bps=deadband_bps,
            n_rows=frame.height,
            feature_names=feature_names,
            path=str(parquet_path),
        )
        self._meta_path(dataset_id).write_text(
            json.dumps(asdict(meta), indent=2), encoding="utf-8"
        )
        _logger.info(
            "dataset_built",
            dataset_id=dataset_id,
            rows=frame.height,
            symbols=meta.symbols,
        )
        return meta

    def list_datasets(self) -> list[DatasetMeta]:
        if not self._datasets_dir.exists():
            return []
        metas = []
        for path in sorted(self._datasets_dir.glob("ds_*.json")):
            metas.append(DatasetMeta(**json.loads(path.read_text(encoding="utf-8"))))
        return metas

    def describe(self, dataset_id: str) -> DatasetMeta:
        path = self._meta_path(dataset_id)
        if not path.exists():
            raise DatasetIntegrityError(
                "Unknown dataset id",
                context={"dataset_id": dataset_id, "looked_in": str(self._datasets_dir)},
            )
        return DatasetMeta(**json.loads(path.read_text(encoding="utf-8")))

    def load(self, dataset_id: str) -> pl.DataFrame:
        path = self._parquet_path(dataset_id)
        if not path.exists():
            raise DatasetIntegrityError(
                "Dataset parquet missing",
                context={"dataset_id": dataset_id, "expected_path": str(path)},
            )
        return pl.read_parquet(path)
