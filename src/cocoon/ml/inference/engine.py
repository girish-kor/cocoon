"""Inference Engine. DOCUMENT.md §F11, §7.1, §12.

Loads a registered model artifact (via the content-hashed registry) and
serves P(up) on live feature vectors. Never fits (§12). Feature vectors are
aligned to the model's declared `feature_names` so a feature-order mismatch
fails loudly rather than silently scrambling inputs.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cocoon.core.errors.exceptions import ModelError
from cocoon.core.interfaces.model_adapter import ModelAdapter
from cocoon.core.logging.setup import get_logger
from cocoon.ml.registry.mlflow_client import ModelRegistry

_logger = get_logger(__name__)


@dataclass(frozen=True)
class InferenceResult:
    probability_up: float
    model_version_hash: str


class InferenceEngine:
    def __init__(
        self,
        *,
        model: ModelAdapter,
        model_version_hash: str,
    ) -> None:
        self._model = model
        self._hash = model_version_hash

    @classmethod
    def from_registry(
        cls, registry: ModelRegistry, run_id: str
    ) -> "InferenceEngine":
        entry = registry.get(run_id)
        if entry is None:
            raise ModelError(
                "Cannot load inference model: unknown run_id",
                context={"run_id": run_id},
            )
        model = registry.load_model(run_id)
        return cls(model=model, model_version_hash=entry.artifact_hash)

    @property
    def model_version_hash(self) -> str:
        return self._hash

    @property
    def feature_names(self) -> list[str]:
        return self._model.feature_names

    def _vectorize(self, features: dict[str, float]) -> np.ndarray:
        names = self._model.feature_names
        missing = [n for n in names if n not in features]
        if missing:
            raise ModelError(
                "Feature vector missing model features",
                context={"missing": missing},
            )
        row = [float(features[n]) for n in names]
        return np.asarray([row], dtype=np.float64)

    def predict_one(self, features: dict[str, float]) -> InferenceResult:
        X = self._vectorize(features)
        proba = float(self._model.predict_proba(X)[0])
        return InferenceResult(probability_up=proba, model_version_hash=self._hash)

    def predict_batch(self, feature_rows: list[dict[str, float]]) -> list[InferenceResult]:
        if not feature_rows:
            return []
        names = self._model.feature_names
        matrix = np.asarray(
            [[float(r[n]) for n in names] for r in feature_rows], dtype=np.float64
        )
        proba = self._model.predict_proba(matrix)
        return [
            InferenceResult(probability_up=float(p), model_version_hash=self._hash)
            for p in proba
        ]
