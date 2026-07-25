"""config command group. DOCUMENT.md §10."""

from __future__ import annotations

import json
from pathlib import Path

import typer
import yaml

from cocoon.cli import get_context, guard, output_obj
from cocoon.core.config.loader import default_sources, resolve

app = typer.Typer(help="Configuration management", no_args_is_help=True)
profile_app = typer.Typer(help="Profile management", no_args_is_help=True)
app.add_typer(profile_app, name="profile")


@app.command()
@guard
def show(
    ctx: typer.Context,
    profile: str = typer.Option(None, "--profile", help="Show this profile's raw overrides"),
    resolved: bool = typer.Option(False, "--resolved", help="Show the fully merged config (defaults + files + env)"),
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
    profile: str = typer.Option(None, "--profile", help="Profile to validate (default: active profile)"),
) -> None:
    app_ctx = get_context(ctx)
    name = profile or app_ctx.options.profile
    resolve(default_sources(profile=name, config_dir=app_ctx.config_dir))
    output_obj(ctx, {"profile": name, "valid": True}, title="config validate")


@app.command(name="set")
@guard
def set_value(
    ctx: typer.Context,
    dot_path: str = typer.Argument(..., help="Nested key, e.g. risk.max_daily_loss_pct"),
    value: str = typer.Argument(..., help="New value; parsed as JSON when possible (1.5, true, [\"M5\"])"),
    profile: str = typer.Option(None, "--profile", help="Profile to write to (default: active profile)"),
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
    output_obj(ctx, {"profile": name, "key": dot_path, "value": coerced}, title="config set")


@profile_app.command("create")
@guard
def profile_create(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="New profile name"),
    from_profile: str = typer.Option(None, "--from", help="Copy overrides from this existing profile"),
) -> None:
    app_ctx = get_context(ctx)
    profiles_dir = Path(app_ctx.config_dir) / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    dest = profiles_dir / f"{name}.yaml"
    if dest.exists():
        output_obj(ctx, {"profile": name, "status": "already exists"}, title="profile create")
        raise typer.Exit(0)
    if from_profile:
        src = profiles_dir / f"{from_profile}.yaml"
        dest.write_text(src.read_text(encoding="utf-8") if src.exists() else "", encoding="utf-8")
    else:
        dest.write_text("# profile overrides\n", encoding="utf-8")
    output_obj(ctx, {"profile": name, "status": "created", "path": str(dest)}, title="profile create")


@profile_app.command("list")
@guard
def profile_list(ctx: typer.Context) -> None:
    app_ctx = get_context(ctx)
    profiles_dir = Path(app_ctx.config_dir) / "profiles"
    names = [p.stem for p in sorted(profiles_dir.glob("*.yaml"))] if profiles_dir.exists() else []
    output_obj(ctx, {"profiles": names}, title="profiles")


@profile_app.command("delete")
@guard
def profile_delete(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Profile to delete"),
) -> None:
    app_ctx = get_context(ctx)
    dest = Path(app_ctx.config_dir) / "profiles" / f"{name}.yaml"
    if dest.exists():
        dest.unlink()
        output_obj(ctx, {"profile": name, "status": "deleted"}, title="profile delete")
    else:
        output_obj(ctx, {"profile": name, "status": "not found"}, title="profile delete")
