"""TabNet adapter. DOCUMENT.md §5, §F6.

Deep-tabular member of the 3-model ensemble. Wraps pytorch-tabnet's
sklearn-compatible classifier behind the L0 ModelAdapter contract.
"""

from __future__ import annotations

from typing import Any

import joblib
import numpy as np

from cocoon.core.interfaces.model_adapter import ModelAdapter


class TabNetModel(ModelAdapter):
    def __init__(
        self,
        *,
        feature_names: list[str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        self._feature_names = feature_names or []
        self._params = dict(params or {})
        self._model = None
        self._classes: list[int] = []

    @property
    def model_name(self) -> str:
        return "tabnet"

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
    ) -> "TabNetModel":
        from pytorch_tabnet.tab_model import TabNetClassifier

        fit_params = {
            "max_epochs": int(self._params.pop("max_epochs", 50)),
            "patience": int(self._params.pop("patience", 10)),
            "batch_size": int(self._params.pop("batch_size", 1024)),
            "virtual_batch_size": int(self._params.pop("virtual_batch_size", 128)),
        }
        self._model = TabNetClassifier(**self._params)
        Xf = np.asarray(X, dtype=np.float32)
        yf = np.asarray(y).astype(np.int64).ravel()
        eval_arg = None
        if eval_set is not None:
            eval_arg = [
                (
                    np.asarray(eval_set[0], dtype=np.float32),
                    np.asarray(eval_set[1]).astype(np.int64).ravel(),
                )
            ]
        self._model.fit(
            Xf,
            yf,
            eval_set=eval_arg,
            max_epochs=fit_params["max_epochs"],
            patience=fit_params["patience"],
            batch_size=fit_params["batch_size"],
            virtual_batch_size=fit_params["virtual_batch_size"],
        )
        self._classes = list(self._model.classes_)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("TabNetModel.predict_proba called before fit/load")
        proba = self._model.predict_proba(np.asarray(X, dtype=np.float32))
        if 1 in self._classes:
            return proba[:, self._classes.index(1)]
        return np.zeros(proba.shape[0])

    def save(self, path: str) -> str:
        joblib.dump(
            {
                "model": self._model,
                "classes": self._classes,
                "feature_names": self._feature_names,
                "params": self._params,
            },
            path,
        )
        from cocoon.ml.registry.artifact_hash import hash_file

        return hash_file(path)

    @classmethod
    def load(cls, path: str) -> "TabNetModel":
        state = joblib.load(path)
        obj = cls(feature_names=state["feature_names"], params=state["params"])
        obj._classes = state["classes"]
        obj._model = state["model"]
        return obj

    def get_params(self) -> dict[str, Any]:
        return dict(self._params)
