"""Live dashboard. DOCUMENT.md §14.

rich-rendered `trade status`. Colours per §14: profit green, loss red,
RUNNING cyan, SAFE_HALT yellow bold, SHUTTING_DOWN grey.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

_console = Console()

_STATE_STYLE = {
    "RUNNING": "cyan",
    "SAFE_HALT": "yellow bold",
    "SHUTTING_DOWN": "grey50",
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
        ("Cocoon — ", "bold white"),
        (str(app_ctx.config.runtime.mode.value).upper(), "bold white"),
        ("  profile:", "dim"),
        (app_ctx.options.profile, "white"),
        ("  state:", "dim"),
        (state_name, style),
    )

    total_pnl = sum(p.get("unrealized_pnl", 0.0) for p in positions)
    pnl_style = "green" if total_pnl >= 0 else "red"
    summary = Text.assemble(
        (f"Open Positions: {len(positions)}/{app_ctx.config.risk.max_open_positions}   ", "white"),
        ("Unrealized P&L: ", "white"),
        (f"{total_pnl:+.2f}", pnl_style),
        (f"   Daily Loss Budget: {app_ctx.config.risk.max_daily_loss_pct}%", "dim"),
    )

    table = Table(expand=True)
    for col in ("SYMBOL", "DIR", "LOTS", "ENTRY", "SL", "TP", "P&L", "ORIGIN"):
        table.add_column(col)
    for p in positions:
        pnl = p.get("unrealized_pnl", 0.0)
        table.add_row(
            p.get("symbol", ""),
            p.get("direction", ""),
            f"{p.get('volume_lots', 0):.2f}",
            f"{p.get('open_price', 0):.5f}",
            f"{(p.get('stop_loss_price') or 0):.5f}",
            f"{(p.get('take_profit_price') or 0):.5f}",
            Text(f"{pnl:+.2f}", style="green" if pnl >= 0 else "red"),
            p.get("origin", ""),
        )

    footer = Text.assemble(
        ("Bridge: ", "dim"),
        ("CONNECTED" if state_name in ("RUNNING", "STATE_RECONCILING") else "—", "white"),
        ("   Model: ", "dim"),
        (str(app_ctx.config.model.ensemble), "white"),
    )

    return Panel(
        Group(header, summary, table, footer),
        title="LIVE",
        border_style=style,
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
