"""model command group. DOCUMENT.md §10, §F9, §16 (exit 32)."""

from __future__ import annotations

from dataclasses import asdict

import typer

from cocoon.cli import get_context, guard, output_obj, output_rows

app = typer.Typer(help="Model registry", no_args_is_help=True)


@app.command(name="list")
@guard
def list_models(ctx: typer.Context) -> None:
    app_ctx = get_context(ctx)
    # Deployables first: production, then staging, then unpromoted.
    stage_rank = {"production": 0, "staging": 1, "none": 2}
    entries = sorted(
        app_ctx.registry().list_runs(),
        key=lambda e: (stage_rank.get(e.stage, 3), e.model_name, e.run_id),
    )
    rows = [
        {"run_id": e.run_id, "model": e.model_name, "stage": e.stage, "dataset_id": e.dataset_id, "hash": e.artifact_hash[:12]}
        for e in entries
    ]
    output_rows(ctx, rows, title="model registry")


@app.command()
@guard
def promote(
    ctx: typer.Context,
    run_id: str = typer.Argument(..., help="Registry run_id, e.g. lightgbm_0e80d8aeb573"),
    stage: str = typer.Option(..., "--stage", help="staging|production (production is exclusive per model)"),
) -> None:
    app_ctx = get_context(ctx)
    entry = app_ctx.registry().promote(run_id, stage)
    output_obj(ctx, {"run_id": entry.run_id, "stage": entry.stage}, title="model promote")


@app.command()
@guard
def inspect(
    ctx: typer.Context,
    run_id: str = typer.Argument(..., help="Registry run_id to show in full"),
) -> None:
    app_ctx = get_context(ctx)
    entry = app_ctx.registry().get(run_id)
    if entry is None:
        output_obj(ctx, {"run_id": run_id, "found": False}, title="model inspect")
        raise typer.Exit(0)
    output_obj(ctx, asdict(entry), title=f"model {run_id}")


@app.command()
@guard
def delete(
    ctx: typer.Context,
    run_id: str = typer.Argument(..., help="Registry run_id to remove (artifact files are deleted too)"),
) -> None:
    app_ctx = get_context(ctx)
    ok = app_ctx.registry().delete(run_id)
    output_obj(ctx, {"run_id": run_id, "deleted": bool(ok)}, title="model delete")
