"""model command group. DOCUMENT.md §10, §F9, §16 (exit 32)."""

from __future__ import annotations

from dataclasses import asdict

import typer

from cocoon.cli import console, get_context, guard, output_obj, output_rows

app = typer.Typer(help="Model registry", no_args_is_help=True)


@app.command(name="list")
@guard
def list_models(ctx: typer.Context) -> None:
    app_ctx = get_context(ctx)
    rows = [
        {"run_id": e.run_id, "model": e.model_name, "stage": e.stage, "dataset_id": e.dataset_id, "hash": e.artifact_hash[:12]}
        for e in app_ctx.registry().list_runs()
    ]
    output_rows(ctx, rows, title="model registry")


@app.command()
@guard
def promote(
    ctx: typer.Context,
    run_id: str = typer.Argument(...),
    stage: str = typer.Option(..., "--stage", help="staging|production"),
) -> None:
    app_ctx = get_context(ctx)
    entry = app_ctx.registry().promote(run_id, stage)
    console.print(f"[green]promoted[/] {entry.run_id} -> {entry.stage}")


@app.command()
@guard
def inspect(ctx: typer.Context, run_id: str = typer.Argument(...)) -> None:
    app_ctx = get_context(ctx)
    entry = app_ctx.registry().get(run_id)
    if entry is None:
        console.print(f"[yellow]no such run[/] {run_id}")
        raise typer.Exit(0)
    output_obj(ctx, asdict(entry), title=f"model {run_id}")


@app.command()
@guard
def delete(ctx: typer.Context, run_id: str = typer.Argument(...)) -> None:
    app_ctx = get_context(ctx)
    ok = app_ctx.registry().delete(run_id)
    console.print(f"[green]deleted[/] {run_id}" if ok else f"[yellow]no such run[/] {run_id}")
