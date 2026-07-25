"""train command group. DOCUMENT.md §10, §F6/F7/F8, §16 (exit 31)."""

from __future__ import annotations

import typer

from cocoon.cli import get_context, guard, output_obj

app = typer.Typer(help="Model training", no_args_is_help=True)


def _orchestrator(app_ctx):
    from cocoon.ml.training.orchestrator import TrainingOrchestrator

    return TrainingOrchestrator(
        dataset_builder=app_ctx.dataset_builder(),
        registry=app_ctx.registry(),
        training_config=app_ctx.config.training,
        model_config=app_ctx.config.model,
    )


def _record_run(app_ctx, result) -> None:
    from sqlalchemy import select

    from cocoon.persistence.models import ModelRun

    db = app_ctx.database()
    with db.session() as s:
        # Training is deterministic, so re-running yields the same run_id.
        # run_id is a UNIQUE column but not the primary key (id is), so
        # session.merge() — which identifies by primary key — would always
        # attempt an INSERT and violate the unique constraint. Upsert by
        # run_id explicitly, preserving any promotion stage on update.
        existing = s.scalar(select(ModelRun).where(ModelRun.run_id == result.run_id))
        if existing is not None:
            existing.model_name = result.model_name
            existing.dataset_id = result.dataset_id
            existing.artifact_hash = result.artifact_hash
            existing.params = result.params
            existing.metrics = result.metrics
        else:
            s.add(
                ModelRun(
                    run_id=result.run_id,
                    model_name=result.model_name,
                    dataset_id=result.dataset_id,
                    artifact_hash=result.artifact_hash,
                    stage="none",
                    params=result.params,
                    metrics=result.metrics,
                )
            )


@app.command()
@guard
def run(
    ctx: typer.Context,
    dataset: str = typer.Option(..., "--dataset", help="ds_* id from `cocoon dataset build`"),
    model: str = typer.Option(..., "--model", help="lightgbm|xgboost|tabnet|ensemble"),
    hpo: bool = typer.Option(False, "--hpo", help="Run Optuna hyperparameter search (single model only)"),
) -> None:
    app_ctx = get_context(ctx)
    result = _orchestrator(app_ctx).run(dataset_id=dataset, model_name=model, hpo=hpo)
    _record_run(app_ctx, result)
    output_obj(
        ctx,
        {"run_id": result.run_id, "model": result.model_name, "metrics": result.metrics, "artifact_hash": result.artifact_hash},
        title="training complete",
    )


@app.command(name="walk-forward")
@guard
def walk_forward(
    ctx: typer.Context,
    dataset: str = typer.Option(..., "--dataset", help="ds_* id from `cocoon dataset build`"),
    model: str = typer.Option(..., "--model", help="lightgbm|xgboost|tabnet|ensemble"),
) -> None:
    app_ctx = get_context(ctx)
    result = _orchestrator(app_ctx).walk_forward(dataset_id=dataset, model_name=model)
    _record_run(app_ctx, result)
    output_obj(ctx, {"run_id": result.run_id, "fold_scores": result.fold_scores, "metrics": result.metrics}, title="walk-forward complete")


@app.command()
@guard
def status(
    ctx: typer.Context,
    run_id: str = typer.Argument(..., help="Run id printed by `cocoon train run`"),
) -> None:
    app_ctx = get_context(ctx)
    from cocoon.persistence.models import ModelRun
    from sqlalchemy import select

    db = app_ctx.database()
    with db.session() as s:
        row = s.scalar(select(ModelRun).where(ModelRun.run_id == run_id))
        if row is None:
            output_obj(ctx, {"run_id": run_id, "found": False}, title="run status")
            return
        output_obj(
            ctx,
            {"run_id": row.run_id, "model": row.model_name, "dataset_id": row.dataset_id, "stage": row.stage, "metrics": row.metrics},
            title="run status",
        )
