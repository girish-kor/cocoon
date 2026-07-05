"""XGBoost adapter. DOCUMENT.md §5, §F6.

Independent GBM implementation (ensemble diversity vs two LightGBM
variants, §5). Binary directional classifier: P(up).
"""

from __future__ import annotations

from typing import Any

import joblib
import numpy as np

from cocoon.core.interfaces.model_adapter import ModelAdapter


class XGBoostModel(ModelAdapter):
    def __init__(
        self,
        *,
        feature_names: list[str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        self._feature_names = feature_names or []
        self._params = dict(params or {})
        self._model = None

    @property
    def model_name(self) -> str:
        return "xgboost"

    @property
    def feature_names(self) -> list[str]:
        return self._feature_names

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        *,
        eval_set: tuple[np.ndarray, np.ndarray] | None = None,
        sample_weight: np.ndarray | None = None,
    ) -> "XGBoostModel":
        from xgboost import XGBClassifier

        defaults: dict[str, Any] = {
            "n_estimators": 300,
            "learning_rate": 0.05,
            "max_depth": 6,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "tree_method": "hist",
            "random_state": 42,
            "n_jobs": -1,
            "eval_metric": "logloss",
        }
        defaults.update(self._params)
        self._model = XGBClassifier(**defaults)
        fit_kwargs: dict[str, Any] = {}
        if eval_set is not None:
            fit_kwargs["eval_set"] = [eval_set]
            fit_kwargs["verbose"] = False
        if sample_weight is not None:
            fit_kwargs["sample_weight"] = sample_weight
        self._model.fit(X, y, **fit_kwargs)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("XGBoostModel.predict_proba called before fit/load")
        proba = self._model.predict_proba(X)
        classes = list(self._model.classes_)
        if 1 in classes:
            return proba[:, classes.index(1)]
        return np.zeros(proba.shape[0])

    def save(self, path: str) -> str:
        joblib.dump(
            {
                "model": self._model,
                "feature_names": self._feature_names,
                "params": self._params,
            },
            path,
        )
        from cocoon.ml.registry.artifact_hash import hash_file

        return hash_file(path)

    @classmethod
    def load(cls, path: str) -> "XGBoostModel":
        payload = joblib.load(path)
        obj = cls(feature_names=payload["feature_names"], params=payload["params"])
        obj._model = payload["model"]
        return obj

    def get_params(self) -> dict[str, Any]:
        return dict(self._params)
