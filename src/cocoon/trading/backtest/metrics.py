"""Backtest performance metrics. DOCUMENT.md §F10, §F20.

Deterministic (no wall-clock branching) — same trade list in, same numbers
out (NFR §3).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PerformanceMetrics:
    n_trades: int
    win_rate: float
    total_pnl: float
    gross_profit: float
    gross_loss: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    expectancy: float
    max_drawdown: float
    sharpe: float
    final_equity: float

    def to_dict(self) -> dict:
        return {
            "n_trades": self.n_trades,
            "win_rate": self.win_rate,
            "total_pnl": self.total_pnl,
            "gross_profit": self.gross_profit,
            "gross_loss": self.gross_loss,
            "profit_factor": self.profit_factor,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "expectancy": self.expectancy,
            "max_drawdown": self.max_drawdown,
            "sharpe": self.sharpe,
            "final_equity": self.final_equity,
        }


def compute_metrics(
    trade_pnls: list[float], *, starting_equity: float
) -> PerformanceMetrics:
    n = len(trade_pnls)
    wins = [p for p in trade_pnls if p > 0]
    losses = [p for p in trade_pnls if p < 0]
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    total_pnl = sum(trade_pnls)

    win_rate = len(wins) / n if n else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0
    avg_win = gross_profit / len(wins) if wins else 0.0
    avg_loss = gross_loss / len(losses) if losses else 0.0
    expectancy = total_pnl / n if n else 0.0

    equity = starting_equity
    peak = starting_equity
    max_dd = 0.0
    for p in trade_pnls:
        equity += p
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)

    sharpe = 0.0
    if n > 1:
        mean = total_pnl / n
        var = sum((p - mean) ** 2 for p in trade_pnls) / (n - 1)
        std = math.sqrt(var)
        if std > 0:
            sharpe = (mean / std) * math.sqrt(n)

    return PerformanceMetrics(
        n_trades=n,
        win_rate=win_rate,
        total_pnl=total_pnl,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=profit_factor,
        avg_win=avg_win,
        avg_loss=avg_loss,
        expectancy=expectancy,
        max_drawdown=max_dd,
        sharpe=sharpe,
        final_equity=starting_equity + total_pnl,
    )
