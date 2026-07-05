"""plugin command group. DOCUMENT.md §10, §F21, §16 (exit 60)."""

from __future__ import annotations

import typer

from cocoon.cli import console, get_context, guard, output_rows

app = typer.Typer(help="Plugin management", no_args_is_help=True)


@app.command(name="list")
@guard
def list_plugins(ctx: typer.Context) -> None:
    app_ctx = get_context(ctx)
    rows = [
        {"name": p.name, "kind": p.kind, "source": p.source}
        for p in app_ctx.plugin_loader().list_plugins()
    ]
    output_rows(ctx, rows, title="plugins")


@app.command()
@guard
def install(ctx: typer.Context, path: str = typer.Argument(...)) -> None:
    app_ctx = get_context(ctx)
    info = app_ctx.plugin_loader().install(path)
    console.print(f"[green]installed[/] {info.name} ({info.source})")


@app.command()
@guard
def remove(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    app_ctx = get_context(ctx)
    ok = app_ctx.plugin_loader().remove(name)
    console.print(f"[green]removed[/] {name}" if ok else f"[yellow]no such plugin[/] {name}")
