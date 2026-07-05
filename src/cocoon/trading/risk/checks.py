"""Pre-trade check functions. DOCUMENT.md §9.2.

Each check is a pure function `(ProposedOrder, CheckContext) -> CheckResult`.
The engine (engine.py) runs them in the §9.2 order and short-circuits on the
first failure. Kept side-effect-free so checks are individually testable and
reorderable without hidden coupling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from cocoon.core.config.schema import RiskConfig
from cocoon.core.interfaces.broker_adapter import BrokerPosition, OrderDirection

_PIP = 0.0001


@dataclass(frozen=True)
class AccountState:
    equity: float
    equity_at_session_start: float
    realized_pnl_today: float
    unrealized_pnl: float


@dataclass(frozen=True)
class ProposedOrder:
    symbol: str
    direction: OrderDirection
    volume_lots: float
    entry_price: float
    stop_loss_price: float
    take_profit_price: float
    spread_pips: float
    ts_unix_ms: int
    contract_size: float = 100_000.0


@dataclass(frozen=True)
class CheckContext:
    risk: RiskConfig
    account: AccountState
    open_positions: list[BrokerPosition]
    max_allowed_spread_pips: float = 3.0
    session_windows_utc: list[tuple[str, str]] = field(default_factory=list)
    correlated_symbols: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    reason: str = ""
    detail: dict = field(default_factory=dict)


def _ok(name: str, **detail) -> CheckResult:
    return CheckResult(name=name, passed=True, detail=detail)


def _fail(name: str, reason: str, **detail) -> CheckResult:
    return CheckResult(name=name, passed=False, reason=reason, detail=detail)


def _position_risk_currency(order: ProposedOrder) -> float:
    stop_distance = abs(order.entry_price - order.stop_loss_price)
    return stop_distance * order.volume_lots * order.contract_size


def daily_loss_check(order: ProposedOrder, ctx: CheckContext) -> CheckResult:
    pnl_today = ctx.account.realized_pnl_today + ctx.account.unrealized_pnl
    limit = -(ctx.risk.max_daily_loss_pct / 100.0) * ctx.account.equity_at_session_start
    if pnl_today <= limit:
        return _fail(
            "daily_loss_check",
            "daily loss limit reached",
            pnl_today=pnl_today,
            limit=limit,
        )
    return _ok("daily_loss_check", pnl_today=pnl_today, limit=limit)


def position_count_check(order: ProposedOrder, ctx: CheckContext) -> CheckResult:
    n = len(ctx.open_positions)
    if n >= ctx.risk.max_open_positions:
        return _fail(
            "position_count_check",
            "max open positions reached",
            open=n,
            limit=ctx.risk.max_open_positions,
        )
    return _ok("position_count_check", open=n)


def position_risk_check(order: ProposedOrder, ctx: CheckContext) -> CheckResult:
    risk_currency = _position_risk_currency(order)
    limit = (ctx.risk.max_position_risk_pct / 100.0) * ctx.account.equity
    if risk_currency > limit:
        return _fail(
            "position_risk_check",
            "position risk exceeds per-trade cap",
            risk=risk_currency,
            limit=limit,
        )
    return _ok("position_risk_check", risk=risk_currency, limit=limit)


def correlated_exposure_check(order: ProposedOrder, ctx: CheckContext) -> CheckResult:
    correlated = set(ctx.correlated_symbols.get(order.symbol, []))
    correlated.add(order.symbol)
    exposure = _position_risk_currency(order)
    for pos in ctx.open_positions:
        if pos.symbol in correlated:
            stop = pos.stop_loss_price if pos.stop_loss_price is not None else pos.open_price
            exposure += abs(pos.open_price - stop) * pos.volume_lots * order.contract_size
    limit = (ctx.risk.max_correlated_exposure_pct / 100.0) * ctx.account.equity
    if exposure > limit:
        return _fail(
            "correlated_exposure_check",
            "correlated exposure exceeds cap",
            exposure=exposure,
            limit=limit,
        )
    return _ok("correlated_exposure_check", exposure=exposure, limit=limit)


def rr_check(order: ProposedOrder, ctx: CheckContext) -> CheckResult:
    sl = abs(order.entry_price - order.stop_loss_price)
    tp = abs(order.take_profit_price - order.entry_price)
    if sl <= 0:
        return _fail("rr_check", "stop-loss distance is zero")
    rr = tp / sl
    if rr < ctx.risk.min_rr_ratio:
        return _fail(
            "rr_check", "reward:risk below minimum", rr=rr, min=ctx.risk.min_rr_ratio
        )
    return _ok("rr_check", rr=rr)


def spread_check(order: ProposedOrder, ctx: CheckContext) -> CheckResult:
    if order.spread_pips > ctx.max_allowed_spread_pips:
        return _fail(
            "spread_check",
            "spread exceeds symbol maximum",
            spread=order.spread_pips,
            max=ctx.max_allowed_spread_pips,
        )
    return _ok("spread_check", spread=order.spread_pips)


def session_check(order: ProposedOrder, ctx: CheckContext) -> CheckResult:
    if not ctx.session_windows_utc:
        return _ok("session_check", reason="no session restriction configured")
    dt = datetime.fromtimestamp(order.ts_unix_ms / 1000.0, tz=timezone.utc)
    minutes = dt.hour * 60 + dt.minute
    for start, end in ctx.session_windows_utc:
        s = _parse_hhmm(start)
        e = _parse_hhmm(end)
        if s <= minutes < e:
            return _ok("session_check", window=f"{start}-{end}")
    return _fail(
        "session_check",
        "outside configured trading session window",
        time_utc=dt.isoformat(),
    )


def _parse_hhmm(value: str) -> int:
    hh, mm = value.split(":")
    return int(hh) * 60 + int(mm)


CHECK_SEQUENCE = (
    daily_loss_check,
    position_count_check,
    position_risk_check,
    correlated_exposure_check,
    rr_check,
    spread_check,
    session_check,
)
