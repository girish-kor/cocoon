"""Event-driven backtest + SimulatedBrokerAdapter. DOCUMENT.md §15.2.

The backtest runs the SAME Signal/Risk/Order engine instances as live, with
a SimulatedBrokerAdapter substituted behind the L0 BrokerAdapter contract —
this is the mechanism that prevents backtest/live logic divergence (§15.2).
Event-driven (not vectorized) so the code path is identical.

Fill model (§15.2): market orders fill at next-bar-open ± fixed slippage;
stop/take-profit levels fill only when the bar's high/low range crosses the
level, at the level price (conservative, no favourable improvement).
Deterministic: no wall-clock branching (NFR §3).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from cocoon.core.config.schema import OrderConfig, RiskConfig
from cocoon.core.interfaces.broker_adapter import (
    Bar,
    BarCallback,
    BrokerAdapter,
    BrokerOrder,
    BrokerPosition,
    OrderDirection,
    OrderIntent,
    OrderResult,
    OrderStatus,
    PositionOrigin,
)
from cocoon.core.logging.setup import get_logger
from cocoon.data.feature_eng.engine import FeatureEngine
from cocoon.ml.inference.engine import InferenceEngine
from cocoon.trading.backtest.metrics import PerformanceMetrics, compute_metrics
from cocoon.trading.order.engine import OrderEngine
from cocoon.trading.order.idempotency import IdempotencyCache, make_idempotency_key
from cocoon.trading.risk.checks import (
    AccountState,
    CheckContext,
    ProposedOrder,
)
from cocoon.trading.risk.engine import RiskEngine
from cocoon.trading.signal.engine import SignalEngine

_logger = get_logger(__name__)
_PIP = 0.0001


@dataclass
class _SimPosition:
    ticket_id: int
    symbol: str
    direction: OrderDirection
    volume_lots: float
    entry_price: float
    stop_loss_price: float
    take_profit_price: float
    contract_size: float
    current_price: float

    def unrealized(self) -> float:
        sign = 1.0 if self.direction == OrderDirection.BUY else -1.0
        return (self.current_price - self.entry_price) * sign * self.volume_lots * self.contract_size


class SimulatedBrokerAdapter(BrokerAdapter):
    def __init__(
        self,
        *,
        slippage_pips: float = 2.0,
        contract_size: float = 100_000.0,
    ) -> None:
        self._slippage = slippage_pips * _PIP
        self._contract_size = contract_size
        self._connected = False
        self._positions: dict[int, _SimPosition] = {}
        self._next_ticket = 1
        self._fill_price: float | None = None
        self._closed_pnls: list[float] = []
        self._bar_callback: BarCallback | None = None

    def connect(self, timeout_ms: int) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def last_heartbeat_ts_unix_ms(self) -> int | None:
        return None

    def set_fill_price(self, price: float) -> None:
        self._fill_price = price

    def submit_order(self, intent: OrderIntent) -> OrderResult:
        if self._fill_price is None:
            raise RuntimeError("SimulatedBrokerAdapter fill price not set")
        slip = self._slippage if intent.direction == OrderDirection.BUY else -self._slippage
        fill = self._fill_price + slip
        ticket = self._next_ticket
        self._next_ticket += 1
        self._positions[ticket] = _SimPosition(
            ticket_id=ticket,
            symbol=intent.symbol,
            direction=intent.direction,
            volume_lots=intent.volume_lots,
            entry_price=fill,
            stop_loss_price=intent.stop_loss_price,
            take_profit_price=intent.take_profit_price,
            contract_size=self._contract_size,
            current_price=fill,
        )
        return OrderResult(
            idempotency_key=intent.idempotency_key,
            status=OrderStatus.FILLED,
            broker_ticket_id=ticket,
            filled_volume_lots=intent.volume_lots,
            filled_price=fill,
            reject_reason=None,
        )

    def cancel_order(self, ticket_id: int) -> OrderResult:
        pos = self._positions.pop(ticket_id, None)
        return OrderResult(
            idempotency_key="",
            status=OrderStatus.FILLED if pos else OrderStatus.REJECTED_BY_BROKER,
            broker_ticket_id=ticket_id,
            filled_volume_lots=0.0,
            filled_price=None,
            reject_reason=None if pos else "unknown ticket",
        )

    def modify_order(
        self,
        ticket_id: int,
        *,
        stop_loss_price: float | None,
        take_profit_price: float | None,
    ) -> OrderResult:
        pos = self._positions.get(ticket_id)
        if pos is not None:
            if stop_loss_price is not None:
                pos.stop_loss_price = stop_loss_price
            if take_profit_price is not None:
                pos.take_profit_price = take_profit_price
        return OrderResult(
            idempotency_key="",
            status=OrderStatus.ACKNOWLEDGED if pos else OrderStatus.REJECTED_BY_BROKER,
            broker_ticket_id=ticket_id,
            filled_volume_lots=0.0,
            filled_price=None,
            reject_reason=None if pos else "unknown ticket",
        )

    def get_positions(self) -> list[BrokerPosition]:
        return [
            BrokerPosition(
                ticket_id=p.ticket_id,
                symbol=p.symbol,
                direction=p.direction,
                volume_lots=p.volume_lots,
                open_price=p.entry_price,
                current_price=p.current_price,
                stop_loss_price=p.stop_loss_price,
                take_profit_price=p.take_profit_price,
                unrealized_pnl=p.unrealized(),
                origin=PositionOrigin.INTERNAL,
            )
            for p in self._positions.values()
        ]

    def get_orders(self) -> list[BrokerOrder]:
        return []

    def subscribe_bars(self, callback: BarCallback) -> None:
        self._bar_callback = callback

    def on_bar(self, bar: Bar) -> list[float]:
        realized: list[float] = []
        for ticket in list(self._positions):
            pos = self._positions[ticket]
            if pos.symbol != bar.symbol:
                continue
            pos.current_price = bar.close
            exit_price = self._check_exit(pos, bar)
            if exit_price is not None:
                sign = 1.0 if pos.direction == OrderDirection.BUY else -1.0
                pnl = (exit_price - pos.entry_price) * sign * pos.volume_lots * pos.contract_size
                realized.append(pnl)
                self._closed_pnls.append(pnl)
                del self._positions[ticket]
        return realized

    @staticmethod
    def _check_exit(pos: _SimPosition, bar: Bar) -> float | None:
        if pos.direction == OrderDirection.BUY:
            if bar.low <= pos.stop_loss_price:
                return pos.stop_loss_price
            if bar.high >= pos.take_profit_price:
                return pos.take_profit_price
        else:
            if bar.high >= pos.stop_loss_price:
                return pos.stop_loss_price
            if bar.low <= pos.take_profit_price:
                return pos.take_profit_price
        return None

    def force_close_all(self, price: float) -> list[float]:
        realized: list[float] = []
        for ticket in list(self._positions):
            pos = self._positions[ticket]
            sign = 1.0 if pos.direction == OrderDirection.BUY else -1.0
            pnl = (price - pos.entry_price) * sign * pos.volume_lots * pos.contract_size
            realized.append(pnl)
            self._closed_pnls.append(pnl)
            del self._positions[ticket]
        return realized

    @property
    def closed_pnls(self) -> list[float]:
        return list(self._closed_pnls)


@dataclass
class BacktestResult:
    symbol: str
    trade_pnls: list[float]
    metrics: PerformanceMetrics
    starting_equity: float
    signals: int = 0
    rejected: int = 0
    equity_curve: list[float] = field(default_factory=list)


class BacktestEventEngine:
    def __init__(
        self,
        *,
        feature_engine: FeatureEngine,
        inference_engine: InferenceEngine,
        risk_config: RiskConfig,
        order_config: OrderConfig,
        starting_equity: float = 10_000.0,
        slippage_pips: float = 2.0,
        atr_stop_mult: float = 1.5,
        lookback: int = 250,
        contract_size: float = 100_000.0,
    ) -> None:
        self._fe = feature_engine
        self._inf = inference_engine
        self._risk_cfg = risk_config
        self._order_cfg = order_config
        self._starting_equity = starting_equity
        self._slippage_pips = slippage_pips
        self._atr_stop_mult = atr_stop_mult
        self._lookback = lookback
        self._contract_size = contract_size

    def run(self, symbol: str, frame: pl.DataFrame) -> BacktestResult:
        frame = frame.sort("ts_unix_ms")
        n = frame.height
        if n <= self._lookback + 2:
            raise ValueError("Not enough bars for backtest lookback window")

        sim = SimulatedBrokerAdapter(
            slippage_pips=self._slippage_pips, contract_size=self._contract_size
        )
        sim.connect(1000)
        signal_engine = SignalEngine(risk_config=self._risk_cfg)
        risk_engine = RiskEngine()
        idem = IdempotencyCache(ttl_sec=self._order_cfg.idempotency_ttl_sec)
        order_engine = OrderEngine(
            broker=sim,
            order_config=self._order_cfg,
            idempotency=idem,
            sleep=lambda _s: None,
        )

        # Features are point-in-time-safe (causal), so a single full-frame
        # pass yields, at every row i, exactly what a per-slice compute_point
        # at t_index=i would — but O(n) instead of O(n^2). §7.3 causality is
        # what makes this substitution sound.
        feat_df = self._fe.compute_frame(frame)
        feature_names = self._fe.feature_names
        feat_rows = feat_df.select(feature_names).to_dicts()
        proba_all = [r.probability_up for r in self._inf.predict_batch(feat_rows)]

        opens = frame.get_column("open").to_list()
        highs = frame.get_column("high").to_list()
        lows = frame.get_column("low").to_list()
        closes = frame.get_column("close").to_list()
        ts = frame.get_column("ts_unix_ms").to_list()

        equity = self._starting_equity
        equity_curve: list[float] = []
        signals = 0
        rejected = 0

        for i in range(self._lookback, n - 1):
            bar_i = Bar(
                symbol=symbol,
                timeframe="",
                ts_unix_ms=int(ts[i]),
                open=opens[i],
                high=highs[i],
                low=lows[i],
                close=closes[i],
                volume=0.0,
            )
            realized = sim.on_bar(bar_i)
            equity += sum(realized)
            equity_curve.append(equity)

            feats = feat_rows[i]
            probability_up = proba_all[i]
            atr_price = feats.get("atr_14_rel", 0.0) * closes[i]
            if atr_price <= 0:
                continue

            intent_signal = signal_engine.evaluate(
                symbol=symbol,
                probability_up=probability_up,
                ts_unix_ms=int(ts[i]),
                model_version_hash=self._inf.model_version_hash,
                atr=None,
                atr_sma=None,
            )
            if intent_signal is None:
                continue
            signals += 1

            next_open = opens[i + 1]
            stop_dist = self._atr_stop_mult * atr_price
            if intent_signal.direction == OrderDirection.BUY:
                sl = next_open - stop_dist
                tp = next_open + stop_dist * self._risk_cfg.min_rr_ratio
            else:
                sl = next_open + stop_dist
                tp = next_open - stop_dist * self._risk_cfg.min_rr_ratio

            risk_amount = (self._risk_cfg.max_position_risk_pct / 100.0) * equity
            volume = max(0.01, risk_amount / (stop_dist * self._contract_size))

            proposed = ProposedOrder(
                symbol=symbol,
                direction=intent_signal.direction,
                volume_lots=volume,
                entry_price=next_open,
                stop_loss_price=sl,
                take_profit_price=tp,
                spread_pips=self._slippage_pips,
                ts_unix_ms=int(ts[i]),
                contract_size=self._contract_size,
            )
            ctx = CheckContext(
                risk=self._risk_cfg,
                account=AccountState(
                    equity=equity,
                    equity_at_session_start=self._starting_equity,
                    realized_pnl_today=equity - self._starting_equity,
                    unrealized_pnl=sim.get_positions() and sum(
                        p.unrealized_pnl for p in sim.get_positions()
                    ) or 0.0,
                ),
                open_positions=sim.get_positions(),
                max_allowed_spread_pips=max(self._slippage_pips + 1.0, 3.0),
            )
            decision = risk_engine.evaluate(proposed, ctx)
            if not decision.approved:
                rejected += 1
                continue

            sim.set_fill_price(next_open)
            key = make_idempotency_key(
                symbol=symbol,
                direction=intent_signal.direction,
                signal_ts_unix_ms=int(ts[i]),
                model_version_hash=self._inf.model_version_hash,
            )
            order_engine.submit(
                OrderIntent(
                    idempotency_key=key,
                    symbol=symbol,
                    direction=intent_signal.direction,
                    volume_lots=volume,
                    stop_loss_price=sl,
                    take_profit_price=tp,
                    max_slippage_pips=self._slippage_pips,
                )
            )

        realized = sim.force_close_all(closes[-1])
        equity += sum(realized)
        equity_curve.append(equity)

        trade_pnls = sim.closed_pnls
        metrics = compute_metrics(trade_pnls, starting_equity=self._starting_equity)
        _logger.info(
            "backtest_complete",
            symbol=symbol,
            trades=metrics.n_trades,
            total_pnl=metrics.total_pnl,
        )
        return BacktestResult(
            symbol=symbol,
            trade_pnls=trade_pnls,
            metrics=metrics,
            starting_equity=self._starting_equity,
            signals=signals,
            rejected=rejected,
            equity_curve=equity_curve,
        )
