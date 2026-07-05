"""CLI composition root. DOCUMENT.md §10, §16, §18.

typer app root. Owns global flags (§10.2), config resolution, logging setup,
the AppContext service factory bundle (the ONLY place concrete
implementations are bound to interfaces, §18), and the CocoonError ->
exit-code mapping (§16). Command bodies are thin (§12) — they call into
L1-L4 services via AppContext.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from cocoon.cli import (
    GlobalOptions,
    build_context,
    console,
    guard,
    _emit_error,
)
from cocoon.core.errors.exceptions import CocoonError
from cocoon.core.errors.exit_codes import ExitCode

app = typer.Typer(
    name="cocoon",
    help="Cocoon — Forex Trading ML Model V1 CLI",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def main(
    ctx: typer.Context,
    profile: str = typer.Option("default", "--profile", help="Active config profile"),
    config_file: str = typer.Option(None, "--config-file", help="Explicit config file path"),
    log_level: str = typer.Option(None, "--log-level", help="DEBUG|INFO|WARN|ERROR"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate and print without executing"),
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation prompts"),
    output: str = typer.Option("table", "--output", help="table|json"),
) -> None:
    options = GlobalOptions(
        profile=profile,
        config_file=config_file,
        log_level=log_level,
        dry_run=dry_run,
        yes=yes,
        output=output,
    )
    if ctx.invoked_subcommand == "init":
        ctx.obj = options
        return
    ctx.obj = build_context(options)


_BASE_YAML = """profile: "default"

runtime:
  mode: "paper"
  log_level: "INFO"
  data_dir: "./data"
  mt5_connect_timeout_ms: 5000
  heartbeat_interval_ms: 1000
  heartbeat_miss_threshold: 3
  shutdown_grace_ms: 10000

mt5:
  terminal_path: "C:/Program Files/MetaTrader 5/terminal64.exe"
  login: 0
  server: ""
  zmq_req_port: 5555
  zmq_pub_port: 5556

symbols:
  - name: "EURUSD"
    timeframes: ["M1", "M5", "M15", "H1"]

feature_engineering:
  fractal_n: 5
  eq_tol_pips: 2.0
  sweep_confirm_bars: 3
  lookback_bars: 500

model:
  active_registry_uri: "mlflow.db"
  ensemble: ["lightgbm", "xgboost", "tabnet"]
  ensemble_weights: [0.4, 0.4, 0.2]
  inference_batch_max_ms: 50

training:
  walk_forward:
    train_window_days: 180
    test_window_days: 30
    step_days: 30
    purge_bars: 50
    embargo_bars: 20
  hpo:
    n_trials: 200
    pruner: "median"
    timeout_sec: 14400

risk:
  max_daily_loss_pct: 2.0
  max_position_risk_pct: 0.5
  max_open_positions: 5
  max_correlated_exposure_pct: 3.0
  min_rr_ratio: 1.5

order:
  default_slippage_pips: 2
  retry_max_attempts: 3
  retry_backoff_ms: [200, 500, 1000]
  idempotency_ttl_sec: 300

logging:
  format: "json"
  rotate_max_mb: 100
  rotate_backups: 10
  audit_log_path: "./logs/audit.jsonl"
"""


@app.command()
@guard
def init(ctx: typer.Context) -> None:
    """First-run: scaffold config/, data/, logs/."""
    created: list[str] = []
    for d in ("config", "config/profiles", "data", "data/raw", "data/features",
              "data/datasets", "data/models", "data/plugins", "logs"):
        p = Path(d)
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            created.append(str(p))
    base = Path("config/base.yaml")
    if not base.exists():
        base.write_text(_BASE_YAML, encoding="utf-8")
        created.append(str(base))
    profile = Path("config/profiles/default.yaml")
    if not profile.exists():
        profile.write_text("# profile overrides\n", encoding="utf-8")
        created.append(str(profile))
    for path in created:
        console.print(f"[green]created[/] {path}")
    console.print("[bold green]cocoon initialised[/]")


def _register() -> None:
    from cocoon.cli.commands import (
        backtest_cmd,
        config_cmd,
        data_cmd,
        dataset_cmd,
        features_cmd,
        model_cmd,
        plugin_cmd,
        positions_cmd,
        report_cmd,
        train_cmd,
        trade_cmd,
    )
    from cocoon.cli.menu.interactive import menu_app

    app.add_typer(config_cmd.app, name="config")
    app.add_typer(data_cmd.app, name="data")
    app.add_typer(features_cmd.app, name="features")
    app.add_typer(dataset_cmd.app, name="dataset")
    app.add_typer(train_cmd.app, name="train")
    app.add_typer(model_cmd.app, name="model")
    app.add_typer(backtest_cmd.app, name="backtest")
    app.add_typer(trade_cmd.app, name="trade")
    app.add_typer(positions_cmd.app, name="positions")
    app.add_typer(report_cmd.app, name="report")
    app.add_typer(plugin_cmd.app, name="plugin")
    app.add_typer(menu_app, name="menu")


_register()


def _load_dotenv() -> None:
    """Load `.env` into os.environ before config resolution. Real environment
    variables win over `.env` (override=False), preserving the §8.1 precedence
    (env > file). No-op if python-dotenv is not installed or no `.env` exists.
    Loaded here (entrypoint), not at import, so library/test imports are
    unaffected."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(override=False)


def entrypoint() -> None:
    _load_dotenv()
    try:
        app()
    except CocoonError as exc:
        code = int(exc.exit_code) if exc.exit_code is not None else int(ExitCode.GENERIC_ERROR)
        _emit_error(exc)
        sys.exit(code)


if __name__ == "__main__":
    entrypoint()
