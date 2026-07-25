"""Paper-run dashboard. DOCUMENT.md §14 styling conventions.

A rich Live view for `trade start --mode paper`: replay progress bar,
account stat row, an equity sparkline, and the open-position table —
instead of the raw JSON log stream (which keeps flowing to the app log
file; see core.logging.setup.quiet_console_logging).

Reads only `runtime.stats` (swapped wholesale by the feed thread) and
`runtime.equity_curve` (append-only), so no locking is needed.
"""

from __future__ import annotations

import threading
import time

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

_console = Console()

_SPARK = "▁▂▃▄▅▆▇█"

_STATE_STYLE = {
    "RUNNING": "cyan",
    "SAFE_HALT": "yellow bold",
    "SHUTTING_DOWN": "grey50",
    "TERMINATED": "grey50",
}


def _sparkline(values: list[float], width: int = 64) -> str:
    if len(values) < 2:
        return ""
    step = max(1, len(values) // width)
    sampled = values[::step][-width:]
    lo, hi = min(sampled), max(sampled)
    span = (hi - lo) or 1.0
    return "".join(_SPARK[int((v - lo) / span * (len(_SPARK) - 1))] for v in sampled)


def _render(runtime) -> Panel:
    s = runtime.stats
    state = runtime.state_name
    style = _STATE_STYLE.get(state, "white")

    header = Text.assemble(
        ("Cocoon PAPER  ", "bold white"),
        (f"{s.get('symbol', '…')} {s.get('tf', '')}", "bold cyan"),
        ("   state: ", "dim"),
        (state, style),
    )

    done, total = s.get("bars_done", 0), s.get("bars_total", 0)
    pct = 100.0 * done / total if total else 0.0
    progress = Table.grid(padding=(0, 1))
    progress.add_row(
        ProgressBar(total=max(total, 1), completed=done, width=44),
        Text(f"{done:,}/{total:,} bars  {pct:5.1f}%"),
    )

    equity = s.get("equity", 0.0) + s.get("unrealized", 0.0)
    pnl = equity - s.get("starting_equity", equity)
    pnl_style = "green" if pnl >= 0 else "red"
    trades = s.get("trades", 0)
    wins = s.get("wins", 0)

    stat = Table(expand=True)
    for col in ("EQUITY", "P&L", "TRADES", "WIN %", "OPEN", "SIGNALS", "REJECTED"):
        stat.add_column(col, justify="right")
    stat.add_row(
        f"{equity:,.2f}",
        Text(f"{pnl:+,.2f}", style=pnl_style),
        str(trades),
        f"{100.0 * wins / trades:.0f}%" if trades else "—",
        str(len(s.get("open_positions", []))),
        str(s.get("signals", 0)),
        str(s.get("rejected", 0)),
    )

    parts = [header, progress, stat]

    curve = runtime.equity_curve
    if len(curve) >= 2:
        parts.append(
            Group(
                Text(f"equity  {max(curve):,.0f} max · {min(curve):,.0f} min", style="dim"),
                Text(_sparkline(curve), style=pnl_style),
            )
        )

    open_positions = s.get("open_positions", [])
    if open_positions:
        pos_table = Table(expand=True)
        for col in ("SYMBOL", "DIR", "LOTS", "ENTRY", "UNREAL P&L"):
            pos_table.add_column(col, justify="right")
        for symbol, direction, lots, entry, upnl in open_positions:
            pos_table.add_row(
                symbol,
                direction,
                f"{lots:.2f}",
                f"{entry:.5f}",
                Text(f"{upnl:+.2f}", style="green" if upnl >= 0 else "red"),
            )
        parts.append(pos_table)

    return Panel(Group(*parts), title="PAPER TRADING", border_style=style)


def run_paper_dashboard(runtime, *, refresh_hz: float = 5.0) -> None:
    """Run `runtime.run()` under a Live dashboard; returns when it does."""
    stop = threading.Event()

    def _tick(live: Live) -> None:
        while not stop.is_set():
            live.update(_render(runtime))
            time.sleep(1.0 / refresh_hz)

    with Live(_render(runtime), console=_console, refresh_per_second=refresh_hz) as live:
        updater = threading.Thread(target=_tick, args=(live,), daemon=True)
        updater.start()
        try:
            runtime.run()
        finally:
            stop.set()
            updater.join(timeout=2.0)
            live.update(_render(runtime))
