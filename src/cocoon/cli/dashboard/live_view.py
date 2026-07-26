"""Live dashboard. DOCUMENT.md §14.

rich-rendered `trade status`. Colours per §14: profit green, loss red,
RUNNING cyan, SAFE_HALT yellow bold, SHUTTING_DOWN grey.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

_console = Console()

_SEP = (" · ", "dim")

_STATE_STYLE = {
    "RUNNING": "cyan",
    "SAFE_HALT": "yellow bold",
    "SHUTTING_DOWN": "dim",
    "TERMINATED": "dim",
    "STATE_RECONCILING": "cyan",
}


def _read_state(app_ctx) -> dict:
    p = Path(app_ctx.data_dir) / "runtime" / "state.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _positions(app_ctx) -> list[dict]:
    try:
        from cocoon.persistence.repositories import PositionRepository

        return PositionRepository(app_ctx.database()).list_open()
    except Exception:
        return []


def _render(app_ctx):
    state = _read_state(app_ctx)
    state_name = state.get("state", "UNKNOWN")
    style = _STATE_STYLE.get(state_name, "white")
    positions = _positions(app_ctx)

    header = Text.assemble(
        ("Cocoon", "bold"),
        _SEP,
        (str(app_ctx.config.runtime.mode.value).upper(), "bold"),
        _SEP,
        ("profile ", "dim"),
        (app_ctx.options.profile, ""),
        _SEP,
        (state_name, style),
    )

    total_pnl = sum(p.get("unrealized_pnl", 0.0) for p in positions)
    pnl_style = "green" if total_pnl >= 0 else "red"
    summary = Text.assemble(
        (f"open {len(positions)}/{app_ctx.config.risk.max_open_positions}", ""),
        _SEP,
        ("unrealized ", ""),
        (f"{total_pnl:+.2f}", pnl_style),
        _SEP,
        (f"daily loss budget {app_ctx.config.risk.max_daily_loss_pct}%", "dim"),
    )

    table = Table(
        box=None, show_edge=False, pad_edge=False,
        padding=(0, 2, 0, 0), header_style="dim cyan",
    )
    for col in ("SYMBOL", "DIR", "LOTS", "ENTRY", "SL", "TP", "P&L", "ORIGIN"):
        table.add_column(col)
    for p in positions:
        pnl = p.get("unrealized_pnl", 0.0)
        direction = p.get("direction", "")
        origin = p.get("origin", "")
        table.add_row(
            Text(p.get("symbol", ""), style="bold"),
            Text(direction, style="green" if direction == "BUY" else "red"),
            Text(f"{p.get('volume_lots', 0):.2f}", style="yellow"),
            Text(f"{p.get('open_price', 0):.5f}", style="yellow"),
            Text(f"{(p.get('stop_loss_price') or 0):.5f}", style="yellow"),
            Text(f"{(p.get('take_profit_price') or 0):.5f}", style="yellow"),
            Text(f"{pnl:+.2f}", style="green" if pnl >= 0 else "red"),
            Text(origin, style="yellow" if origin == "external" else "dim"),
        )

    footer = Text.assemble(
        ("bridge ", "dim"),
        ("CONNECTED" if state_name in ("RUNNING", "STATE_RECONCILING") else "–", ""),
        _SEP,
        ("model ", "dim"),
        (", ".join(app_ctx.config.model.ensemble), ""),
    )

    return Panel(
        Group(header, summary, table, footer),
        title="LIVE",
        title_align="left",
        border_style=style,
        box=box.ROUNDED,
    )


def render_once(app_ctx) -> None:
    _console.print(_render(app_ctx))


def watch_dashboard(app_ctx, *, refresh_hz: float = 2.0) -> None:
    interval = 1.0 / refresh_hz
    with Live(_render(app_ctx), console=_console, refresh_per_second=refresh_hz) as live:
        try:
            while True:
                time.sleep(interval)
                live.update(_render(app_ctx))
        except KeyboardInterrupt:
            return
