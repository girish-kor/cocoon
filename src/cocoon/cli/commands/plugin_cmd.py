"""plugin command group. DOCUMENT.md §10, §F21, §16 (exit 60)."""

from __future__ import annotations

import typer

from cocoon.cli import get_context, guard, output_obj, output_rows

app = typer.Typer(help="Plugin management", no_args_is_help=True)


@app.command(name="list")
@guard
def list_plugins(ctx: typer.Context) -> None:
    """List discovered plugins — entry-point packages and local files."""
    app_ctx = get_context(ctx)
    rows = [
        {"name": p.name, "kind": p.kind, "source": p.source}
        for p in app_ctx.plugin_loader().list_plugins()
    ]
    output_rows(ctx, rows, title="plugins")


@app.command()
@guard
def install(
    ctx: typer.Context,
    path: str = typer.Argument(
        ...,
        help="Local .py file exposing build_features() that returns FeatureFn "
        "object(s); copied into data/plugins/. Exit 60 if non-conforming.",
    ),
) -> None:
    """Install a local feature plugin, e.g. `cocoon plugin install ./my_indicator.py`."""
    app_ctx = get_context(ctx)
    info = app_ctx.plugin_loader().install(path)
    output_obj(ctx, {"name": info.name, "source": info.source, "status": "installed"}, title="plugin install")


@app.command()
@guard
def remove(
    ctx: typer.Context,
    name: str = typer.Argument(
        ..., help="Installed plugin name, as shown by `cocoon plugin list`"
    ),
) -> None:
    """Remove an installed local plugin by name."""
    app_ctx = get_context(ctx)
    ok = app_ctx.plugin_loader().remove(name)
    output_obj(ctx, {"name": name, "removed": bool(ok)}, title="plugin remove")
