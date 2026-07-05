"""ModelAdapter interface. Authoritative source: DOCUMENT.md §5, §6, §12.

Needed for "pipeline uniformity across the 3-model ensemble" (§5,
pytorch-tabnet justification) — `ml/models/{lightgbm,xgboost,tabnet}_model.py`
each implement this identically-shaped contract so
`ml/models/ensemble.py` and `ml/inference/engine.py` never branch on
concrete model type.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np


class ModelAdapter(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        ...

    @property
    @abstractmethod
    def feature_names(self) -> list[str]:
        ...

    @abstractmethod
    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        *,
        eval_set: tuple[np.ndarray, np.ndarray] | None = None,
        sample_weight: np.ndarray | None = None,
    ) -> "ModelAdapter":
        ...

    @abstractmethod
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Returns shape (n_samples,) of P(positive class) — a single
        directional probability, matching Signal Engine's consumption
        contract (§9.1: 'raw probability + confidence')."""
        ...

    @abstractmethod
    def save(self, path: str) -> str:
        """Persists the model artifact; returns the artifact's content
        hash (consumed by ml/registry/artifact_hash.py, §9's model
        registry requirement)."""
        ...

    @classmethod
    @abstractmethod
    def load(cls, path: str) -> "ModelAdapter":
        ...

    @abstractmethod
    def get_params(self) -> dict[str, Any]:
        """Hyperparameters in effect — required for the audit trail
        (§3: reconstructable-from-logs-alone) and for MLflow run
        logging (§9)."""
        ...
