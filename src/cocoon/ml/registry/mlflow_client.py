"""Model registry. DOCUMENT.md §9, §F9.

Authoritative store is a local, content-hashed filesystem registry under
`<data_dir>/models/<run_id>/` with a JSON index — deterministic and
server-free (§5: "local file-store backend, no server"). MLflow is used
best-effort for experiment tracking (params/metrics/artifact logging); its
absence or failure never breaks the authoritative local registry.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cocoon.core.errors.exceptions import ModelPromotionError
from cocoon.core.interfaces.model_adapter import ModelAdapter
from cocoon.core.logging.setup import get_logger

_logger = get_logger(__name__)

STAGES = ("none", "staging", "production")


@dataclass
class RegistryEntry:
    run_id: str
    model_name: str
    dataset_id: str
    artifact_path: str
    artifact_hash: str
    stage: str = "none"
    params: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)


class ModelRegistry:
    def __init__(
        self,
        *,
        models_dir: str | Path,
        tracking_uri: str | None = None,
    ) -> None:
        self._dir = Path(models_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._dir / "registry.json"
        self._tracking_uri = tracking_uri
        self._lock = threading.RLock()

    def _load_index(self) -> dict[str, dict]:
        if not self._index_path.exists():
            return {}
        return json.loads(self._index_path.read_text(encoding="utf-8"))

    def _save_index(self, index: dict[str, dict]) -> None:
        self._index_path.write_text(
            json.dumps(index, indent=2, sort_keys=True), encoding="utf-8"
        )

    def _model_class(self, model_name: str):
        from cocoon.ml.models import MODEL_REGISTRY
        from cocoon.ml.models.ensemble import EnsembleModel

        if model_name == "ensemble":
            return EnsembleModel
        return MODEL_REGISTRY[model_name]

    def register(
        self,
        model: ModelAdapter,
        *,
        dataset_id: str,
        params: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> RegistryEntry:
        with self._lock:
            tmp_stem = "artifact.json" if model.model_name == "ensemble" else "artifact.pkl"
            tmp_run_dir = self._dir / "_staging"
            tmp_run_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = tmp_run_dir / tmp_stem
            artifact_hash = model.save(str(tmp_path))
            run_id = f"{model.model_name}_{artifact_hash[:12]}"
            run_dir = self._dir / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            final_path = run_dir / tmp_stem
            model.save(str(final_path))

            entry = RegistryEntry(
                run_id=run_id,
                model_name=model.model_name,
                dataset_id=dataset_id,
                artifact_path=str(final_path),
                artifact_hash=artifact_hash,
                params=dict(params or {}),
                metrics=dict(metrics or {}),
            )
            index = self._load_index()
            index[run_id] = asdict(entry)
            self._save_index(index)
            self._log_mlflow(entry)
            _logger.info("model_registered", run_id=run_id, hash=artifact_hash)
            return entry

    def _log_mlflow(self, entry: RegistryEntry) -> None:
        if not self._tracking_uri:
            return
        try:
            import mlflow

            mlflow.set_tracking_uri(self._tracking_uri)
            mlflow.set_experiment("cocoon")
            with mlflow.start_run(run_name=entry.run_id):
                mlflow.log_param("model_name", entry.model_name)
                mlflow.log_param("dataset_id", entry.dataset_id)
                mlflow.log_param("artifact_hash", entry.artifact_hash)
                for k, v in entry.params.items():
                    mlflow.log_param(f"hp_{k}", v)
                for k, v in entry.metrics.items():
                    if isinstance(v, (int, float)):
                        mlflow.log_metric(k, float(v))
                mlflow.log_artifact(entry.artifact_path)
        except Exception as exc:  # best-effort only
            _logger.warning("mlflow_log_failed", error=str(exc))

    def get(self, run_id: str) -> RegistryEntry | None:
        index = self._load_index()
        raw = index.get(run_id)
        return RegistryEntry(**raw) if raw else None

    def list_runs(self) -> list[RegistryEntry]:
        return [RegistryEntry(**v) for v in self._load_index().values()]

    def promote(self, run_id: str, stage: str) -> RegistryEntry:
        if stage not in STAGES:
            raise ModelPromotionError(
                f"Unknown stage '{stage}'",
                context={"stage": stage, "valid": list(STAGES)},
            )
        with self._lock:
            index = self._load_index()
            if run_id not in index:
                raise ModelPromotionError(
                    "Unknown run_id for promotion",
                    context={"run_id": run_id},
                )
            if stage == "production":
                for rid, rec in index.items():
                    if (
                        rid != run_id
                        and rec["model_name"] == index[run_id]["model_name"]
                        and rec["stage"] == "production"
                    ):
                        rec["stage"] = "staging"
            index[run_id]["stage"] = stage
            self._save_index(index)
            return RegistryEntry(**index[run_id])

    def delete(self, run_id: str) -> bool:
        with self._lock:
            index = self._load_index()
            if run_id not in index:
                return False
            run_dir = self._dir / run_id
            if run_dir.exists():
                for f in run_dir.glob("*"):
                    f.unlink()
                run_dir.rmdir()
            del index[run_id]
            self._save_index(index)
            return True

    def production_run(self, model_name: str) -> RegistryEntry | None:
        for entry in self.list_runs():
            if entry.model_name == model_name and entry.stage == "production":
                return entry
        return None

    def load_model(self, run_id: str) -> ModelAdapter:
        entry = self.get(run_id)
        if entry is None:
            raise ModelPromotionError(
                "Cannot load unknown run_id", context={"run_id": run_id}
            )
        model_cls = self._model_class(entry.model_name)
        return model_cls.load(entry.artifact_path)
