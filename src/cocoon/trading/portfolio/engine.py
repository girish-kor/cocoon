"""Portfolio Engine. DOCUMENT.md §9.3.

Holds authoritative in-memory position/account state but treats it as a
CACHE: every risk-decision read checks `now - last_sync` against
`staleness_threshold_ms` and forces a synchronous resync from the broker
before proceeding when stale. This is what closes the §1.2 partial-fill /
reconciliation gap — decisions never run on state that could silently be
behind the broker.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

from cocoon.core.interfaces.broker_adapter import BrokerAdapter, BrokerPosition
from cocoon.core.logging.setup import get_logger
from cocoon.trading.risk.checks import AccountState

_logger = get_logger(__name__)


def _default_clock() -> int:
    return int(time.time() * 1000)


class PortfolioEngine:
    def __init__(
        self,
        *,
        broker: BrokerAdapter,
        staleness_threshold_ms: int,
        clock: Callable[[], int] = _default_clock,
    ) -> None:
        self._broker = broker
        self._staleness = staleness_threshold_ms
        self._clock = clock
        self._lock = threading.RLock()
        self._positions: list[BrokerPosition] = []
        self._last_sync_ms: int | None = None
        self._equity = 0.0
        self._equity_session_start = 0.0
        self._realized_pnl_today = 0.0

    def set_account(
        self,
        *,
        equity: float,
        equity_session_start: float | None = None,
        realized_pnl_today: float | None = None,
    ) -> None:
        with self._lock:
            self._equity = equity
            if equity_session_start is not None:
                self._equity_session_start = equity_session_start
            elif self._equity_session_start == 0.0:
                self._equity_session_start = equity
            if realized_pnl_today is not None:
                self._realized_pnl_today = realized_pnl_today

    def sync(self) -> None:
        positions = self._broker.get_positions()
        with self._lock:
            self._positions = positions
            self._last_sync_ms = self._clock()
        _logger.debug("portfolio_synced", n_positions=len(positions))

    def _is_stale(self) -> bool:
        if self._last_sync_ms is None:
            return True
        return (self._clock() - self._last_sync_ms) > self._staleness

    def get_positions(self, *, for_decision: bool = True) -> list[BrokerPosition]:
        if for_decision and self._is_stale():
            _logger.info("portfolio_stale_forcing_resync")
            self.sync()
        with self._lock:
            return list(self._positions)

    def unrealized_pnl(self, *, for_decision: bool = True) -> float:
        return sum(p.unrealized_pnl for p in self.get_positions(for_decision=for_decision))

    def account_state(self, *, for_decision: bool = True) -> AccountState:
        unrealized = self.unrealized_pnl(for_decision=for_decision)
        with self._lock:
            return AccountState(
                equity=self._equity,
                equity_at_session_start=self._equity_session_start,
                realized_pnl_today=self._realized_pnl_today,
                unrealized_pnl=unrealized,
            )

    @property
    def last_sync_ms(self) -> int | None:
        return self._last_sync_ms
