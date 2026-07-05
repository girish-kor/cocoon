"""BrokerAdapter interface. Authoritative source: DOCUMENT.md §9, §13, §15.2, §18.

This is THE mechanism that prevents backtest/live logic divergence
(§15.2): the same Signal/Risk/Order engine instances run against either
a live `BrokerAdapter` (bridge/broker_adapter.py, L4, talking ZMQ to the
MQL5 EA) or a `SimulatedBrokerAdapter` (trading/backtest, L3) — both
implement this exact contract, so the trading layer above never knows
which one it is holding.

Per §18: every core/interfaces/*.py defines an abc.ABC; concrete
implementations are wired at the CLI composition root only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Callable


class OrderDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    """Mirrors the order lifecycle state diagram, §9.4, verbatim."""

    INTENT = "INTENT"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    SUBMIT_TIMEOUT = "SUBMIT_TIMEOUT"
    RETRYING = "RETRYING"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED_BY_BROKER = "REJECTED_BY_BROKER"
    PARTIALLY_FILLED_TIMEOUT = "PARTIALLY_FILLED_TIMEOUT"


class PositionOrigin(str, Enum):
    """§9.6: a position discovered during reconciliation that the local
    DB has no record of is tagged `external` and never auto-closed."""

    INTERNAL = "internal"
    EXTERNAL = "external"


@dataclass(frozen=True)
class OrderIntent:
    """Wire-compatible with the ORDER_SUBMIT payload schema, §13.3."""

    idempotency_key: str
    symbol: str
    direction: OrderDirection
    volume_lots: float
    stop_loss_price: float
    take_profit_price: float
    max_slippage_pips: float


@dataclass(frozen=True)
class OrderResult:
    """Wire-compatible with the ORDER_RESULT payload schema, §13.3."""

    idempotency_key: str
    status: OrderStatus
    broker_ticket_id: int | None
    filled_volume_lots: float
    filled_price: float | None
    reject_reason: str | None


@dataclass(frozen=True)
class BrokerPosition:
    ticket_id: int
    symbol: str
    direction: OrderDirection
    volume_lots: float
    open_price: float
    current_price: float
    stop_loss_price: float | None
    take_profit_price: float | None
    unrealized_pnl: float
    origin: PositionOrigin


@dataclass(frozen=True)
class BrokerOrder:
    ticket_id: int
    symbol: str
    direction: OrderDirection
    volume_lots: float
    requested_price: float
    stop_loss_price: float | None
    take_profit_price: float | None
    status: OrderStatus
    origin: PositionOrigin


@dataclass(frozen=True)
class Bar:
    symbol: str
    timeframe: str
    ts_unix_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


BarCallback = Callable[[Bar], None]


class BrokerAdapter(ABC):
    """Single authoritative broker contract. §6.1 layering rule: the
    trading layer (L3) depends on this interface only; the concrete
    `bridge.broker_adapter.BrokerAdapter` (real, ZMQ-backed) and
    `trading.backtest.SimulatedBrokerAdapter` are wired in at the CLI
    composition root (cli/main.py) — never imported directly by
    trading/* modules."""

    @abstractmethod
    def connect(self, timeout_ms: int) -> None:
        ...

    @abstractmethod
    def disconnect(self) -> None:
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        ...

    @property
    @abstractmethod
    def last_heartbeat_ts_unix_ms(self) -> int | None:
        ...

    @abstractmethod
    def submit_order(self, intent: OrderIntent) -> OrderResult:
        ...

    @abstractmethod
    def cancel_order(self, ticket_id: int) -> OrderResult:
        ...

    @abstractmethod
    def modify_order(
        self,
        ticket_id: int,
        *,
        stop_loss_price: float | None,
        take_profit_price: float | None,
    ) -> OrderResult:
        ...

    @abstractmethod
    def get_positions(self) -> list[BrokerPosition]:
        ...

    @abstractmethod
    def get_orders(self) -> list[BrokerOrder]:
        ...

    @abstractmethod
    def subscribe_bars(self, callback: BarCallback) -> None:
        ...
