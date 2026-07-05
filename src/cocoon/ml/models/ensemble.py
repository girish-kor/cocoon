"""Ensemble model. DOCUMENT.md §8.3 (ensemble_weights), §9.1.

Weighted average of member P(up). Implements ModelAdapter so inference and
signal code treat the ensemble exactly like a single model.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from cocoon.core.interfaces.model_adapter import ModelAdapter


class EnsembleModel(ModelAdapter):
    def __init__(self, members: list[ModelAdapter], weights: list[float]) -> None:
        if len(members) != len(weights):
            raise ValueError("ensemble members and weights length mismatch")
        total = sum(weights)
        if total <= 0:
            raise ValueError("ensemble weights must sum to a positive value")
        self._members = members
        self._weights = [w / total for w in weights]

    @property
    def model_name(self) -> str:
        return "ensemble"

    @property
    def feature_names(self) -> list[str]:
        return self._members[0].feature_names if self._members else []

    @property
    def members(self) -> list[ModelAdapter]:
        return self._members

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        *,
        eval_set: tuple[np.ndarray, np.ndarray] | None = None,
        sample_weight: np.ndarray | None = None,
    ) -> "EnsembleModel":
        for member in self._members:
            member.fit(X, y, eval_set=eval_set, sample_weight=sample_weight)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        acc = np.zeros(X.shape[0], dtype=np.float64)
        for member, weight in zip(self._members, self._weights):
            acc += weight * member.predict_proba(X)
        return acc

    def save(self, path: str) -> str:
        from cocoon.ml.registry.artifact_hash import hash_file

        base = Path(path)
        base.parent.mkdir(parents=True, exist_ok=True)
        member_hashes: list[str] = []
        member_files: list[str] = []
        for i, member in enumerate(self._members):
            member_path = base.parent / f"{base.stem}_member{i}_{member.model_name}.pkl"
            member_hashes.append(member.save(str(member_path)))
            member_files.append(member_path.name)
        manifest = {
            "members": [
                {"name": m.model_name, "file": f, "hash": h, "weight": w}
                for m, f, h, w in zip(
                    self._members, member_files, member_hashes, self._weights
                )
            ]
        }
        base.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return hash_file(str(base))

    @classmethod
    def load(cls, path: str) -> "EnsembleModel":
        from cocoon.ml.models import MODEL_REGISTRY

        base = Path(path)
        manifest = json.loads(base.read_text(encoding="utf-8"))
        members: list[ModelAdapter] = []
        weights: list[float] = []
        for entry in manifest["members"]:
            model_cls = MODEL_REGISTRY[entry["name"]]
            members.append(model_cls.load(str(base.parent / entry["file"])))
            weights.append(float(entry["weight"]))
        return cls(members, weights)

    def get_params(self) -> dict[str, Any]:
        return {
            "weights": self._weights,
            "members": [m.model_name for m in self._members],
            "member_params": [m.get_params() for m in self._members],
        }
