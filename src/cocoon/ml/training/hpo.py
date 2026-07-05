"""Optuna HPO. DOCUMENT.md §F7, §5.

MedianPruner over walk-forward folds. Raises HPOExhaustedError (exit 31)
if no trial produced a valid (non-NaN) score.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
from sklearn.metrics import roc_auc_score

from cocoon.core.errors.exceptions import HPOExhaustedError
from cocoon.core.interfaces.model_adapter import ModelAdapter
from cocoon.core.logging.setup import get_logger
from cocoon.ml.training.walk_forward import PurgedWalkForwardSplit

_logger = get_logger(__name__)

ModelFactory = Callable[[dict[str, Any]], ModelAdapter]
SearchSpace = Callable[[Any], dict[str, Any]]


def _score_fold(
    factory: ModelFactory,
    params: dict[str, Any],
    X: np.ndarray,
    y: np.ndarray,
    train_idx: np.ndarray,
    test_idx: np.ndarray,
) -> float:
    model = factory(params)
    model.fit(X[train_idx], y[train_idx])
    proba = model.predict_proba(X[test_idx])
    y_test = y[test_idx]
    if len(np.unique(y_test)) < 2:
        return float("nan")
    return float(roc_auc_score(y_test, proba))


def run_hpo(
    *,
    factory: ModelFactory,
    search_space: SearchSpace,
    X: np.ndarray,
    y: np.ndarray,
    splitter: PurgedWalkForwardSplit,
    n_trials: int = 200,
    timeout_sec: int | None = None,
    pruner: str = "median",
) -> dict[str, Any]:
    import optuna

    folds = splitter.folds(X)
    optuna_pruner = (
        optuna.pruners.MedianPruner()
        if pruner == "median"
        else optuna.pruners.NopPruner()
    )
    sampler = optuna.samplers.TPESampler(seed=42)
    study = optuna.create_study(
        direction="maximize", pruner=optuna_pruner, sampler=sampler
    )

    def objective(trial: Any) -> float:
        params = search_space(trial)
        scores: list[float] = []
        for step, fold in enumerate(folds):
            score = _score_fold(
                factory, params, X, y, fold.train_idx, fold.test_idx
            )
            if np.isnan(score):
                continue
            scores.append(score)
            trial.report(float(np.mean(scores)), step)
            if trial.should_prune():
                raise optuna.TrialPruned()
        if not scores:
            raise optuna.TrialPruned()
        return float(np.mean(scores))

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study.optimize(objective, n_trials=n_trials, timeout=timeout_sec)

    completed = [
        t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE
    ]
    if not completed:
        raise HPOExhaustedError(
            "HPO exhausted without a valid completed trial",
            context={"n_trials": n_trials, "completed": 0},
        )
    _logger.info("hpo_complete", best_value=study.best_value, trials=len(completed))
    return dict(study.best_params)
