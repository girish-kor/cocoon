"""Training Orchestrator. DOCUMENT.md §F6, §F8, §12.

Loads a versioned dataset, converts it to a binary directional problem
(P(up), neutral rows dropped), runs optional Optuna HPO over purged
walk-forward folds, fits the final artifact on the full dataset, and
registers it (content-hashed) in the model registry. Never serves live
inference (§12: training must not contain live serving).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from cocoon.core.config.schema import ModelConfig, TrainingConfig
from cocoon.core.errors.exceptions import TrainingError
from cocoon.core.interfaces.model_adapter import ModelAdapter
from cocoon.core.logging.setup import get_logger
from cocoon.data.dataset.builder import DatasetBuilder
from cocoon.data.market_data.mt5_fetcher import TIMEFRAME_SECONDS
from cocoon.ml.models import MODEL_REGISTRY
from cocoon.ml.models.ensemble import EnsembleModel
from cocoon.ml.registry.mlflow_client import ModelRegistry
from cocoon.ml.training.hpo import run_hpo
from cocoon.ml.training.walk_forward import PurgedWalkForwardSplit

_logger = get_logger(__name__)


@dataclass
class TrainingResult:
    run_id: str
    model_name: str
    dataset_id: str
    artifact_hash: str
    metrics: dict[str, float] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    fold_scores: list[float] = field(default_factory=list)


def _search_space(model_name: str) -> Callable[[Any], dict[str, Any]]:
    def lgbm(trial: Any) -> dict[str, Any]:
        return {
            "n_estimators": trial.suggest_int("n_estimators", 100, 600),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 15, 127),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        }

    def xgb(trial: Any) -> dict[str, Any]:
        return {
            "n_estimators": trial.suggest_int("n_estimators", 100, 600),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        }

    def tabnet(trial: Any) -> dict[str, Any]:
        return {
            "n_d": trial.suggest_int("n_d", 8, 32),
            "n_a": trial.suggest_int("n_a", 8, 32),
            "n_steps": trial.suggest_int("n_steps", 3, 6),
            "max_epochs": 30,
        }

    return {"lightgbm": lgbm, "xgboost": xgb, "tabnet": tabnet}[model_name]


class TrainingOrchestrator:
    def __init__(
        self,
        *,
        dataset_builder: DatasetBuilder,
        registry: ModelRegistry,
        training_config: TrainingConfig,
        model_config: ModelConfig,
    ) -> None:
        self._db = dataset_builder
        self._registry = registry
        self._tcfg = training_config
        self._mcfg = model_config

    def _load_xy(
        self, dataset_id: str
    ) -> tuple[np.ndarray, np.ndarray, list[str], str]:
        meta = self._db.describe(dataset_id)
        frame = self._db.load(dataset_id)
        frame = frame.filter(frame["label"] != 0)
        if frame.height == 0:
            raise TrainingError(
                "Dataset has no directional (non-neutral) rows",
                context={"dataset_id": dataset_id},
            )
        feature_names = meta.feature_names
        X = frame.select(feature_names).to_numpy().astype(np.float64)
        y = (frame["label"].to_numpy() > 0).astype(np.int64)
        return X, y, feature_names, meta.timeframe

    def _splitter(self, timeframe: str) -> PurgedWalkForwardSplit:
        tf_sec = TIMEFRAME_SECONDS.get(timeframe, 60)
        wf = self._tcfg.walk_forward
        bars = lambda days: max(1, int(days * 86400 / tf_sec))
        return PurgedWalkForwardSplit(
            train_size=bars(wf.train_window_days),
            test_size=bars(wf.test_window_days),
            step_size=bars(wf.step_days),
            purge=wf.purge_bars,
            embargo=wf.embargo_bars,
        )

    def _factory(
        self, model_name: str, feature_names: list[str]
    ) -> Callable[[dict[str, Any]], ModelAdapter]:
        if model_name == "ensemble":
            def make_ensemble(params: dict[str, Any]) -> ModelAdapter:
                members = [
                    MODEL_REGISTRY[m](feature_names=feature_names)
                    for m in self._mcfg.ensemble
                ]
                return EnsembleModel(members, list(self._mcfg.ensemble_weights))

            return make_ensemble

        model_cls = MODEL_REGISTRY[model_name]
        return lambda params: model_cls(feature_names=feature_names, params=params)

    def _walk_forward_scores(
        self,
        factory: Callable[[dict[str, Any]], ModelAdapter],
        params: dict[str, Any],
        X: np.ndarray,
        y: np.ndarray,
        splitter: PurgedWalkForwardSplit,
    ) -> list[float]:
        from sklearn.metrics import roc_auc_score

        scores: list[float] = []
        for fold in splitter.folds(X):
            model = factory(params)
            model.fit(X[fold.train_idx], y[fold.train_idx])
            proba = model.predict_proba(X[fold.test_idx])
            y_test = y[fold.test_idx]
            if len(np.unique(y_test)) < 2:
                continue
            scores.append(float(roc_auc_score(y_test, proba)))
        return scores

    def run(
        self,
        *,
        dataset_id: str,
        model_name: str,
        hpo: bool = False,
    ) -> TrainingResult:
        X, y, feature_names, timeframe = self._load_xy(dataset_id)
        splitter = self._splitter(timeframe)
        factory = self._factory(model_name, feature_names)

        params: dict[str, Any] = {}
        if hpo and model_name != "ensemble":
            params = run_hpo(
                factory=factory,
                search_space=_search_space(model_name),
                X=X,
                y=y,
                splitter=splitter,
                n_trials=self._tcfg.hpo.n_trials,
                timeout_sec=self._tcfg.hpo.timeout_sec,
                pruner=self._tcfg.hpo.pruner,
            )

        fold_scores = self._walk_forward_scores(factory, params, X, y, splitter)
        metrics = {
            "walk_forward_auc_mean": float(np.mean(fold_scores)) if fold_scores else 0.0,
            "walk_forward_auc_std": float(np.std(fold_scores)) if fold_scores else 0.0,
            "n_folds": float(len(fold_scores)),
            "n_samples": float(len(y)),
        }

        final_model = factory(params)
        final_model.fit(X, y)
        entry = self._registry.register(
            final_model,
            dataset_id=dataset_id,
            params=params,
            metrics=metrics,
        )
        _logger.info(
            "training_complete", run_id=entry.run_id, auc=metrics["walk_forward_auc_mean"]
        )
        return TrainingResult(
            run_id=entry.run_id,
            model_name=model_name,
            dataset_id=dataset_id,
            artifact_hash=entry.artifact_hash,
            metrics=metrics,
            params=params,
            fold_scores=fold_scores,
        )

    def walk_forward(
        self, *, dataset_id: str, model_name: str
    ) -> TrainingResult:
        return self.run(dataset_id=dataset_id, model_name=model_name, hpo=False)
