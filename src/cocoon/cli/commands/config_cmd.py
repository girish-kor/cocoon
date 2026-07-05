"""config command group. DOCUMENT.md §10."""

from __future__ import annotations

import json
from pathlib import Path

import typer
import yaml

from cocoon.cli import get_context, guard, output_obj, console
from cocoon.core.config.loader import default_sources, resolve

app = typer.Typer(help="Configuration management", no_args_is_help=True)
profile_app = typer.Typer(help="Profile management", no_args_is_help=True)
app.add_typer(profile_app, name="profile")


@app.command()
@guard
def show(
    ctx: typer.Context,
    profile: str = typer.Option(None, "--profile"),
    resolved: bool = typer.Option(False, "--resolved", help="Show fully resolved config"),
) -> None:
    app_ctx = get_context(ctx)
    if resolved or profile is None:
        output_obj(ctx, app_ctx.config.model_dump(), title="resolved config")
        return
    path = Path(app_ctx.config_dir) / "profiles" / f"{profile}.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    output_obj(ctx, raw or {}, title=f"profile {profile}")


@app.command()
@guard
def validate(
    ctx: typer.Context,
    profile: str = typer.Option(None, "--profile"),
) -> None:
    app_ctx = get_context(ctx)
    name = profile or app_ctx.options.profile
    resolve(default_sources(profile=name, config_dir=app_ctx.config_dir))
    console.print(f"[green]config for profile '{name}' is valid[/]")


@app.command(name="set")
@guard
def set_value(
    ctx: typer.Context,
    dot_path: str = typer.Argument(..., help="e.g. risk.max_daily_loss_pct"),
    value: str = typer.Argument(...),
    profile: str = typer.Option(None, "--profile"),
) -> None:
    app_ctx = get_context(ctx)
    name = profile or app_ctx.options.profile
    path = Path(app_ctx.config_dir) / "profiles" / f"{name}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    data = data or {}
    try:
        coerced = json.loads(value)
    except json.JSONDecodeError:
        coerced = value
    cursor = data
    parts = dot_path.split(".")
    for p in parts[:-1]:
        cursor = cursor.setdefault(p, {})
    cursor[parts[-1]] = coerced
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    console.print(f"[green]set[/] {dot_path} = {coerced} in profile '{name}'")


@profile_app.command("create")
@guard
def profile_create(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    from_profile: str = typer.Option(None, "--from"),
) -> None:
    app_ctx = get_context(ctx)
    profiles_dir = Path(app_ctx.config_dir) / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    dest = profiles_dir / f"{name}.yaml"
    if dest.exists():
        console.print(f"[yellow]profile '{name}' already exists[/]")
        raise typer.Exit(0)
    if from_profile:
        src = profiles_dir / f"{from_profile}.yaml"
        dest.write_text(src.read_text(encoding="utf-8") if src.exists() else "", encoding="utf-8")
    else:
        dest.write_text("# profile overrides\n", encoding="utf-8")
    console.print(f"[green]created profile[/] {name}")


@profile_app.command("list")
@guard
def profile_list(ctx: typer.Context) -> None:
    app_ctx = get_context(ctx)
    profiles_dir = Path(app_ctx.config_dir) / "profiles"
    names = [p.stem for p in sorted(profiles_dir.glob("*.yaml"))] if profiles_dir.exists() else []
    output_obj(ctx, {"profiles": names}, title="profiles")


@profile_app.command("delete")
@guard
def profile_delete(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    app_ctx = get_context(ctx)
    dest = Path(app_ctx.config_dir) / "profiles" / f"{name}.yaml"
    if dest.exists():
        dest.unlink()
        console.print(f"[green]deleted profile[/] {name}")
    else:
        console.print(f"[yellow]no such profile[/] {name}")
