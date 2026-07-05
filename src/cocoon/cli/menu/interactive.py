"""Interactive menu. DOCUMENT.md §10.1.

A questionary-driven nested menu that is a THIN presentation layer over the
same typer command objects — it builds an argv and re-invokes the root
`app`, so interactive and scripted behaviour cannot diverge (they are the
same command functions).
"""

from __future__ import annotations

import shlex

import questionary
import typer

menu_app = typer.Typer(help="Interactive menu", invoke_without_command=True)

# group -> {command label: (argv-template, [prompt-specs])}. Prompt spec is
# (flag, message, default). A flag of "" means positional.
_MENU: dict[str, dict[str, tuple[list[str], list[tuple[str, str, str]]]]] = {
    "config": {
        "show resolved": (["config", "show", "--resolved"], []),
        "validate": (["config", "validate"], []),
        "list profiles": (["config", "profile", "list"], []),
    },
    "data": {
        "status": (["data", "status"], []),
        "cache stats": (["data", "cache", "stats"], []),
        "fetch": (
            ["data", "fetch"],
            [("--symbol", "Symbol", "EURUSD"), ("--tf", "Timeframe", "M5"),
             ("--from", "From (ISO)", "2024-01-01"), ("--to", "To (ISO)", "2024-02-01")],
        ),
    },
    "features": {
        "list": (["features", "list"], []),
        "build": (["features", "build"], [("--symbol", "Symbol", "EURUSD"), ("--tf", "Timeframe", "M5")]),
    },
    "dataset": {
        "list": (["dataset", "list"], []),
        "build": (
            ["dataset", "build"],
            [("--symbols", "Symbols (csv)", "EURUSD"), ("--tf", "Timeframe", "M5"),
             ("--label-horizon", "Label horizon", "5")],
        ),
    },
    "train": {
        "run": (["train", "run"], [("--dataset", "Dataset id", ""), ("--model", "Model", "lightgbm")]),
    },
    "model": {
        "list": (["model", "list"], []),
        "promote": (["model", "promote"], [("", "Run id", ""), ("--stage", "Stage", "production")]),
    },
    "backtest": {
        "run": (
            ["backtest", "run"],
            [("--model-version", "Run id", ""), ("--symbols", "Symbols (csv)", "EURUSD"),
             ("--tf", "Timeframe", "M5")],
        ),
    },
    "trade": {
        "status": (["trade", "status"], []),
        "halt": (["trade", "halt", "--yes"], []),
        "resume": (["trade", "resume"], []),
        "stop": (["trade", "stop"], []),
    },
    "positions": {
        "list": (["positions", "list"], []),
    },
    "plugin": {
        "list": (["plugin", "list"], []),
    },
}


def _run_argv(argv: list[str]) -> None:
    from cocoon.cli.main import app

    try:
        app(args=argv, standalone_mode=False, prog_name="cocoon")
    except SystemExit:
        pass
    except typer.Exit:
        pass


@menu_app.callback(invoke_without_command=True)
def menu(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    while True:
        group = questionary.select(
            "Cocoon — select a group",
            choices=[*_MENU.keys(), "custom command", "quit"],
        ).ask()
        if group in (None, "quit"):
            return
        if group == "custom command":
            raw = questionary.text("Enter command (without 'cocoon')").ask()
            if raw:
                _run_argv(shlex.split(raw))
            continue
        commands = _MENU[group]
        label = questionary.select(
            f"{group} — select a command",
            choices=[*commands.keys(), "back"],
        ).ask()
        if label in (None, "back"):
            continue
        argv_template, prompts = commands[label]
        argv = list(argv_template)
        for flag, message, default in prompts:
            value = questionary.text(message, default=default).ask()
            if value is None:
                break
            if flag:
                argv.extend([flag, value])
            else:
                argv.append(value)
        _run_argv(argv)
