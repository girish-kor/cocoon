"""L5: cli. May import L0-L4 (DOCUMENT.md §6.1). Composition root — the only
place concrete implementations are wired to interfaces (§18).

Shared CLI helpers (AppContext service factories, the guard/exit-code
mapper, output formatters) live here rather than in main.py so that command
modules can import them without creating a main<->command import cycle:
this package imports neither main nor the command modules.
"""

from __future__ import annotations

import enum
import functools
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import typer
from rich.console import Console
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

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

# TERMINAL_V2.md §2.2 — outcome glyphs, ASCII under TERM=dumb. Rich handles
# NO_COLOR / non-TTY colour stripping itself.
_DUMB_TERM = os.environ.get("TERM") == "dumb"
GLYPH_OK = "OK" if _DUMB_TERM else "✓"
GLYPH_NONE = "-" if _DUMB_TERM else "–"
GLYPH_ERR = "X" if _DUMB_TERM else "✗"

_NEUTRAL_STATUS = ("not found", "already exists", "unknown format", "none")

# TERMINAL_V2.md §2.1 — semantic value colours (ANSI-16 only).
_TITLE_STYLE = "bold cyan"
_KEY_STYLE = "dim cyan"
_ID_KEYS = {
    "run_id", "dataset_id", "backtest_id", "artifact_hash", "hash",
    "idempotency_key", "ticket", "broker_ticket_id", "session_id",
}
_PATH_KEYS = {"path", "paths", "root", "file"}
_PNL_KEYS = {"pnl", "total_pnl", "unrealized_pnl", "expectancy"}
_NAME_KEYS = {"symbol", "symbols", "model", "profile", "name"}
_STATUS_OK = {"FILLED", "ACKNOWLEDGED", "PARTIALLY_FILLED"}


def _semantic_style(key: str, value: Any) -> str | None:
    """Colour a cell by what it means, never just to decorate."""
    k = str(key).lower()
    if k in ("dir", "direction"):
        return {"BUY": "green", "SELL": "red"}.get(str(value))
    if k == "status":
        text = str(value).upper()
        if text in _STATUS_OK:
            return "green"
        if "REJECT" in text or "FAILED" in text or "TIMEOUT" in text:
            return "red"
        return None
    if k == "stage":
        return {"production": "green", "staging": "yellow", "none": "dim"}.get(str(value))
    if k == "origin":
        return "yellow" if str(value) == "external" else "dim"
    if k in _PNL_KEYS and isinstance(value, (int, float)) and not isinstance(value, bool):
        return "green" if value >= 0 else "red"
    if k in _ID_KEYS or k.endswith("_id"):
        return "magenta"
    if k in _PATH_KEYS:
        return "blue"
    if k in _NAME_KEYS:
        return "bold"
    if isinstance(value, bool):
        return "green" if value else "dim"
    if isinstance(value, (int, float)):
        return "yellow"
    return None


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
            from cocoon.persistence.audit_sink import DbMirroredAuditLogger

            self._audit = DbMirroredAuditLogger(
                self.config.logging.audit_log_path, self.database()
            )
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
    err_console.print(
        Text.assemble(
            (f"{GLYPH_ERR} ", "red"),
            (str(record["error_type"]), "bold red"),
            (f": {record['message']}", ""),
        )
    )
    if record.get("context"):
        err_console.print(
            Text(f"  context: {json.dumps(record['context'], default=str)}", style="dim")
        )


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


def _fmt_scalar(value: Any) -> str:
    """Human-table cell formatting: thousands separators for ints, compact
    floats. The `--output json` path never goes through here — that output
    is a scripting contract and stays raw."""
    if isinstance(value, enum.Enum):
        return str(value.value)
    if isinstance(value, bool) or value is None:
        return str(value)
    if isinstance(value, int):
        # Group 5+ digit numbers only: "110,125,169" reads better but a
        # port rendered "5,555" reads worse.
        return f"{value:,}" if abs(value) >= 10_000 else str(value)
    if isinstance(value, float):
        return f"{value:,.6g}"
    return str(value)


def _flatten_lines(mapping: dict[str, Any], prefix: str = "") -> list[str]:
    lines: list[str] = []
    for key, value in mapping.items():
        if isinstance(value, dict):
            lines.extend(_flatten_lines(value, f"{prefix}{key}."))
        else:
            lines.append(f"{prefix}{key} = {_render_value(value)}")
    return lines


def _render_value(value: Any) -> str:
    if isinstance(value, dict):
        return "\n".join(_flatten_lines(value))
    if isinstance(value, list):
        if all(not isinstance(item, (dict, list)) for item in value):
            return ", ".join(str(item) for item in value)
        return json.dumps(value, default=str)
    return _fmt_scalar(value)


def _decorated_value(key: str, value: Any, title: str) -> Text | None:
    """TERMINAL_V2.md §6.7 — outcome glyphs on status vocabulary. Table mode
    only; the JSON path never sees these."""
    if key == "status":
        text = str(value)
        if text.startswith(_NEUTRAL_STATUS):
            return Text(f"{GLYPH_NONE} {text}", style="dim")
        return Text(f"{GLYPH_OK} {text}", style="green")
    if key == "valid" and value is True:
        return Text(f"{GLYPH_OK} True", style="green")
    if key == "found" and value is False:
        return Text("False", style="dim")
    if key == "stage" and title == "model promote":
        return Text(f"{GLYPH_OK} {value}", style="green")
    return None


def _print_titled(title: str, renderable) -> None:
    """§2.3 block layout: bold flush-left title, data indented two spaces."""
    if title:
        console.print(Text(title, style=_TITLE_STYLE))
    console.print(Padding(renderable, (0, 0, 0, 2)))


def output_rows(ctx: typer.Context, rows: list[dict[str, Any]], *, title: str = "") -> None:
    app_ctx = get_context(ctx)
    if app_ctx.options.output == "json":
        console.print_json(json.dumps(rows, default=str))
        return
    if not rows:
        console.print(
            Text.assemble((title or "no rows", _TITLE_STYLE), (f"  {GLYPH_NONE} none", "dim"))
        )
        return
    columns = list(rows[0].keys())
    numeric = {
        col: all(
            isinstance(row.get(col), (int, float))
            and not isinstance(row.get(col), bool)
            for row in rows
        )
        for col in columns
    }
    table = Table(
        box=None,
        show_edge=False,
        pad_edge=False,
        padding=(0, 2, 0, 0),
        header_style=_KEY_STYLE,
    )
    for col in columns:
        table.add_column(
            str(col).upper().replace("_", " "),
            justify="right" if numeric[col] else "left",
        )
    for row in rows:
        cells = []
        for col in columns:
            raw = row.get(col, "")
            style = _semantic_style(str(col), raw)
            rendered = _fmt_scalar(raw)
            cells.append(Text(rendered, style=style) if style else rendered)
        table.add_row(*cells)
    _print_titled(title, table)


def output_obj(ctx: typer.Context, obj: dict[str, Any], *, title: str = "") -> None:
    app_ctx = get_context(ctx)
    if app_ctx.options.output == "json":
        console.print_json(json.dumps(obj, default=str))
        return
    grid = Table.grid(padding=(0, 2, 0, 0))
    grid.add_column(style=_KEY_STYLE)
    grid.add_column()
    for k, v in obj.items():
        cell = _decorated_value(str(k), v, title)
        if cell is None:
            rendered = _render_value(v)
            style = None if isinstance(v, (dict, list)) else _semantic_style(str(k), v)
            cell = Text(rendered, style=style) if style else rendered
        grid.add_row(str(k), cell)
    _print_titled(title, grid)
