"""L5: cli. May import L0-L4 (DOCUMENT.md §6.1). Composition root — the only
place concrete implementations are wired to interfaces (§18).

Shared CLI helpers (AppContext service factories, the guard/exit-code
mapper, output formatters) live here rather than in main.py so that command
modules can import them without creating a main<->command import cycle:
this package imports neither main nor the command modules.
"""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import typer
from rich.console import Console
from rich.table import Table

from cocoon._layering import enforce_layering

enforce_layering(__name__)

from cocoon.core.config.loader import default_sources, resolve
from cocoon.core.config.schema import ConfigModel, LogLevel
from cocoon.core.errors.exceptions import CocoonError
from cocoon.core.errors.exit_codes import ExitCode
from cocoon.core.logging.audit import AuditLogger
from cocoon.core.logging.setup import configure_logging, get_logger

_logger = get_logger(__name__)
console = Console()
err_console = Console(stderr=True)


@dataclass
class GlobalOptions:
    profile: str = "default"
    config_file: str | None = None
    log_level: str | None = None
    dry_run: bool = False
    yes: bool = False
    output: str = "table"


@dataclass
class AppContext:
    config: ConfigModel
    options: GlobalOptions
    config_dir: str = "./config"
    _audit: AuditLogger | None = field(default=None, repr=False)

    @property
    def data_dir(self) -> Path:
        return Path(self.config.runtime.data_dir)

    def market_data(self):
        from cocoon.data.market_data.manager import MarketDataManager

        return MarketDataManager(data_dir=str(self.data_dir))

    def dataset_builder(self):
        from cocoon.data.dataset.builder import DatasetBuilder

        return DatasetBuilder(
            market_data=self.market_data(),
            fe_config=self.config.feature_engineering,
            data_dir=str(self.data_dir),
        )

    def registry(self):
        from cocoon.ml.registry.mlflow_client import ModelRegistry

        return ModelRegistry(
            models_dir=str(self.data_dir / "models"),
            tracking_uri=self.config.model.active_registry_uri,
        )

    def database(self):
        from cocoon.persistence.db import get_database

        return get_database(str(self.data_dir / "cocoon.db"))

    def audit_logger(self) -> AuditLogger:
        if self._audit is None:
            self._audit = AuditLogger(self.config.logging.audit_log_path)
        return self._audit

    def plugin_loader(self):
        from cocoon.plugins.loader import PluginLoader

        return PluginLoader(plugins_dir=str(self.data_dir / "plugins"))

    def bridge_broker(self):
        from cocoon.bridge.broker_adapter import ZmqBrokerAdapter
        from cocoon.bridge.heartbeat import HeartbeatMonitor
        from cocoon.bridge.zmq_endpoint import ZmqEndpoint

        endpoint = ZmqEndpoint(
            req_port=self.config.mt5.zmq_req_port,
            pub_port=self.config.mt5.zmq_pub_port,
        )
        heartbeat = HeartbeatMonitor(
            interval_ms=self.config.runtime.heartbeat_interval_ms,
            miss_threshold=self.config.runtime.heartbeat_miss_threshold,
        )
        return ZmqBrokerAdapter(endpoint=endpoint, heartbeat=heartbeat)


def build_context(options: GlobalOptions) -> AppContext:
    config_dir = "./config"
    if options.config_file:
        config_dir = str(Path(options.config_file).parent)
    sources = default_sources(profile=options.profile, config_dir=config_dir)
    config = resolve(sources)
    log_level = (
        LogLevel(options.log_level) if options.log_level else config.runtime.log_level
    )
    configure_logging(config.logging, log_level=log_level)
    return AppContext(config=config, options=options, config_dir=config_dir)


def _emit_error(exc: CocoonError) -> None:
    record = exc.to_log_record()
    _logger.error("cli_error", **record)
    err_console.print(f"[bold red]{record['error_type']}[/]: {record['message']}")
    if record.get("context"):
        err_console.print(f"[dim]context: {json.dumps(record['context'], default=str)}[/]")


def guard(func: Callable) -> Callable:
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any):
        try:
            return func(*args, **kwargs)
        except CocoonError as exc:
            code = int(exc.exit_code) if exc.exit_code is not None else int(ExitCode.GENERIC_ERROR)
            _emit_error(exc)
            raise typer.Exit(code)

    return wrapper


def get_context(ctx: typer.Context) -> AppContext:
    if ctx.obj is None or isinstance(ctx.obj, GlobalOptions):
        base = ctx.obj if isinstance(ctx.obj, GlobalOptions) else GlobalOptions()
        ctx.obj = build_context(base)
    return ctx.obj


def output_rows(ctx: typer.Context, rows: list[dict[str, Any]], *, title: str = "") -> None:
    app_ctx = get_context(ctx)
    if app_ctx.options.output == "json":
        console.print_json(json.dumps(rows, default=str))
        return
    if not rows:
        console.print(f"[dim]{title or 'no rows'}[/]")
        return
    table = Table(title=title or None)
    for col in rows[0].keys():
        table.add_column(str(col))
    for row in rows:
        table.add_row(*[str(row.get(col, "")) for col in rows[0].keys()])
    console.print(table)


def output_obj(ctx: typer.Context, obj: dict[str, Any], *, title: str = "") -> None:
    app_ctx = get_context(ctx)
    if app_ctx.options.output == "json":
        console.print_json(json.dumps(obj, default=str))
        return
    table = Table(title=title or None, show_header=False)
    table.add_column("key")
    table.add_column("value")
    for k, v in obj.items():
        table.add_row(str(k), json.dumps(v, default=str) if isinstance(v, (dict, list)) else str(v))
    console.print(table)
