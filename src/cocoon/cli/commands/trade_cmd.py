"""trade command group + live runtime. DOCUMENT.md §7.2, §9, §10, §14, §16.

`trade start` is the composition root for the live/paper trading loop: it
drives the §7.2 state machine, wires the bridge BrokerAdapter to the
Signal/Risk/Portfolio/Order engines, reconciles on startup (§9.6), and runs
the bar-driven inference->signal->risk->order pipeline (§7.1). halt/resume/
stop communicate with a running loop via a control file (no daemon
supervisor is specified — §0 — so control is file-based, single host).
"""

from __future__ import annotations

import json
import signal as signal_mod
import sys
import time
from pathlib import Path

import typer

from cocoon.cli import get_context, guard, output_obj
from cocoon.core.errors.exceptions import ModelError
from cocoon.core.interfaces.broker_adapter import (
    Bar,
    OrderDirection,
    OrderIntent,
    OrderStatus,
    PositionOrigin,
)
from cocoon.core.logging.setup import get_logger
from cocoon.core.state_machine.engine import StateMachine
from cocoon.core.state_machine.states import Event, State

app = typer.Typer(help="Live/paper trading", no_args_is_help=True)
_logger = get_logger(__name__)


def _runtime_dir(app_ctx) -> Path:
    d = app_ctx.data_dir / "runtime"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _state_path(app_ctx) -> Path:
    return _runtime_dir(app_ctx) / "state.json"


def _control_path(app_ctx) -> Path:
    return _runtime_dir(app_ctx) / "control.json"


def _write_state(app_ctx, **fields) -> None:
    _state_path(app_ctx).write_text(json.dumps(fields, default=str), encoding="utf-8")


def _read_state(app_ctx) -> dict:
    p = _state_path(app_ctx)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _set_control(app_ctx, action: str) -> None:
    _control_path(app_ctx).write_text(json.dumps({"action": action}), encoding="utf-8")


def _read_control(app_ctx) -> str | None:
    p = _control_path(app_ctx)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("action")
    except json.JSONDecodeError:
        return None


class LiveRuntime:
    def __init__(
        self,
        app_ctx,
        *,
        mode: str,
        paper_symbol: str | None = None,
        paper_tf: str | None = None,
        paper_speed: float = 20.0,
        paper_equity: float = 10_000.0,
    ) -> None:
        self._ctx = app_ctx
        self._mode = mode
        self._audit = app_ctx.audit_logger()
        self._sm = StateMachine(audit_logger=self._audit)
        self._broker = None
        self._md = app_ctx.market_data()
        self._fe = None
        self._inference = None
        self._signal = None
        self._risk = None
        self._portfolio = None
        self._order = None
        self._pos_repo = None
        self._running = True
        self._paper_symbol = paper_symbol
        self._paper_tf = paper_tf
        self._paper_speed = paper_speed
        self._paper_equity = paper_equity
        self._feed_thread = None
        self.paper_result: dict | None = None
        # Live-view feed: `stats` is swapped wholesale (atomic reference)
        # and `equity_curve` is append-only, so a dashboard thread can
        # read both without locking against the feed thread.
        self.stats: dict = {}
        self.equity_curve: list[float] = []
        self._stat_signals = 0
        self._stat_rejected = 0

    @property
    def state_name(self) -> str:
        return self._sm.state.value

    def _build_engines(self) -> None:
        from cocoon.data.feature_eng.engine import FeatureEngine, build_feature_catalogue
        from cocoon.ml.inference.engine import InferenceEngine
        from cocoon.trading.order.engine import OrderEngine
        from cocoon.trading.order.idempotency import IdempotencyCache
        from cocoon.trading.portfolio.engine import PortfolioEngine
        from cocoon.trading.risk.engine import RiskEngine
        from cocoon.trading.signal.engine import SignalEngine

        registry = self._ctx.registry()
        entry = None
        for name in ("ensemble", *self._ctx.config.model.ensemble):
            entry = registry.production_run(name)
            if entry:
                break
        if entry is None:
            raise ModelError(
                "No production-stage model to trade; promote one first",
                context={"hint": "cocoon model promote <run_id> --stage production"},
            )
        self._inference = InferenceEngine.from_registry(registry, entry.run_id)
        self._fe = FeatureEngine()
        self._fe.register_all(build_feature_catalogue(self._ctx.config.feature_engineering))
        from cocoon.persistence.repositories import OrderRepository, PositionRepository

        db = self._ctx.database()
        self._pos_repo = PositionRepository(db)
        self._signal = SignalEngine(risk_config=self._ctx.config.risk)
        self._risk = RiskEngine(audit_logger=self._audit)
        self._portfolio = PortfolioEngine(
            broker=self._broker,
            staleness_threshold_ms=self._ctx.config.risk.staleness_threshold_ms,
        )
        self._order = OrderEngine(
            broker=self._broker,
            order_config=self._ctx.config.order,
            idempotency=IdempotencyCache(ttl_sec=self._ctx.config.order.idempotency_ttl_sec),
            order_repo=OrderRepository(db),
            audit_logger=self._audit,
        )

    def _reconcile(self) -> None:
        from cocoon.persistence.repositories import OrderRepository, PositionRepository
        from cocoon.trading.order.reconciliation import ReconciliationManager

        db = self._ctx.database()
        pos_repo = PositionRepository(db)
        manager = ReconciliationManager(
            broker=self._broker,
            position_repo=pos_repo,
            order_repo=OrderRepository(db),
        )
        # Paper broker starts empty, so local open positions left by a
        # crashed paper session are simulations, not real money — close
        # them instead of demanding manual resolution (exit 21).
        report = manager.reconcile(raise_on_conflict=self._mode != "paper")
        if self._mode == "paper":
            for conflict in report.conflicts:
                if conflict.get("type") == "local_position_missing_at_broker":
                    pos_repo.close(conflict["ticket"])
                    _logger.info("paper_stale_position_closed", ticket=conflict["ticket"])

    def _on_bar(self, bar: Bar) -> None:
        try:
            self._md.ingest_bar(bar, persist=False)
            # SAFE_HALT means no new trades — but keep ingesting so the
            # feature window is warm when trading resumes.
            if self._sm.state != State.RUNNING:
                return
            lookback = self._ctx.config.feature_engineering.lookback_bars
            window = self._md.get_window(bar.symbol, bar.timeframe, lookback)
            if window.height < 60:
                return
            feats = self._fe.compute_point(window, window.height - 1)
            result = self._inference.predict_one(feats)
            atr_price = feats.get("atr_14_rel", 0.0) * bar.close
            intent_signal = self._signal.evaluate(
                symbol=bar.symbol,
                probability_up=result.probability_up,
                ts_unix_ms=bar.ts_unix_ms,
                model_version_hash=result.model_version_hash,
            )
            if intent_signal is not None:
                self._stat_signals += 1
            if intent_signal is None or atr_price <= 0:
                return
            self._submit(intent_signal, bar, atr_price, result.model_version_hash)
        except Exception as exc:  # a bad bar must not crash the loop
            _logger.warning("live_bar_error", error=str(exc), symbol=bar.symbol)

    def _submit(self, sig, bar: Bar, atr_price: float, model_hash: str) -> None:
        from cocoon.trading.order.idempotency import make_idempotency_key
        from cocoon.trading.risk.checks import CheckContext, ProposedOrder

        rc = self._ctx.config.risk
        stop_dist = 1.5 * atr_price
        if sig.direction == OrderDirection.BUY:
            sl, tp = bar.close - stop_dist, bar.close + stop_dist * rc.min_rr_ratio
        else:
            sl, tp = bar.close + stop_dist, bar.close - stop_dist * rc.min_rr_ratio
        account = self._portfolio.account_state()
        risk_amount = (rc.max_position_risk_pct / 100.0) * max(account.equity, 1.0)
        volume = max(0.01, risk_amount / (stop_dist * 100_000.0))
        proposed = ProposedOrder(
            symbol=bar.symbol,
            direction=sig.direction,
            volume_lots=volume,
            entry_price=bar.close,
            stop_loss_price=sl,
            take_profit_price=tp,
            spread_pips=self._ctx.config.order.default_slippage_pips,
            ts_unix_ms=bar.ts_unix_ms,
        )
        ctx = CheckContext(
            risk=rc,
            account=account,
            open_positions=self._portfolio.get_positions(),
        )
        decision = self._risk.evaluate(proposed, ctx)
        if not decision.approved:
            self._stat_rejected += 1
            return
        key = make_idempotency_key(
            symbol=bar.symbol,
            direction=sig.direction,
            signal_ts_unix_ms=bar.ts_unix_ms,
            model_version_hash=model_hash,
        )
        result = self._order.submit(
            OrderIntent(
                idempotency_key=key,
                symbol=bar.symbol,
                direction=sig.direction,
                volume_lots=volume,
                stop_loss_price=sl,
                take_profit_price=tp,
                max_slippage_pips=self._ctx.config.order.default_slippage_pips,
            ),
            signal_ts_unix_ms=bar.ts_unix_ms,
            model_version_hash=model_hash,
        )
        if (
            result.status in (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED)
            and result.broker_ticket_id is not None
        ):
            self._pos_repo.upsert_by_ticket(
                broker_ticket_id=result.broker_ticket_id,
                symbol=bar.symbol,
                direction=sig.direction.value,
                volume_lots=result.filled_volume_lots,
                open_price=result.filled_price or bar.close,
                stop_loss_price=sl,
                take_profit_price=tp,
                unrealized_pnl=0.0,
                origin=PositionOrigin.INTERNAL.value,
                is_open=True,
            )
            # A fill invalidates cached portfolio state; resync so the
            # very next risk decision sees the new position.
            self._portfolio.sync()

    # ---- paper mode: replay cached bars through the live pipeline with a
    # SimulatedBrokerAdapter behind the same L0 BrokerAdapter contract, so
    # no MT5 terminal/EA is needed (§15.2 anti-divergence mechanism).

    def _paper_broker(self):
        from cocoon.trading.backtest.event_engine import SimulatedBrokerAdapter

        return SimulatedBrokerAdapter(
            slippage_pips=self._ctx.config.order.default_slippage_pips
        )

    def _resolve_paper_source(self) -> tuple[str, str]:
        from cocoon.core.errors.exceptions import DataError

        rows = self._md.coverage_status()
        if self._paper_symbol:
            rows = [r for r in rows if r["symbol"] == self._paper_symbol]
        if self._paper_tf:
            rows = [r for r in rows if r["tf"] == self._paper_tf]
        if not rows:
            raise DataError(
                "No cached bars to replay for paper trading",
                context={"symbol": self._paper_symbol, "tf": self._paper_tf,
                         "hint": "cocoon data fetch / cocoon data import"},
            )
        best = max(rows, key=lambda r: r["bars"])
        return best["symbol"], best["tf"]

    def _start_paper_feed(self) -> None:
        import threading

        symbol, tf = self._resolve_paper_source()
        _logger.info("paper_replay_start", symbol=symbol, tf=tf, speed=self._paper_speed)
        self._feed_thread = threading.Thread(
            target=self._paper_feed, args=(symbol, tf), daemon=True
        )
        self._feed_thread.start()

    def _paper_feed(self, symbol: str, tf: str) -> None:
        frame = self._md.load_cache(symbol, tf).sort("ts_unix_ms")
        # The replay IS the cache: start from an empty window so features
        # see bars strictly in replay order (no cache seed = no lookahead).
        self._md.reset_buffer(symbol, tf)
        delay = 1.0 / self._paper_speed if self._paper_speed > 0 else 0.0
        equity = self._paper_equity
        last_close = 0.0
        bars_fed = 0
        for row in frame.iter_rows(named=True):
            while self._running and self._sm.state != State.RUNNING:
                time.sleep(0.2)
            if not self._running:
                break
            bar = Bar(
                symbol=symbol,
                timeframe=tf,
                ts_unix_ms=int(row["ts_unix_ms"]),
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row.get("volume") or 0.0,
            )
            last_close = bar.close
            bars_fed += 1
            open_before = {p.ticket_id for p in self._broker.get_positions()}
            realized = self._broker.on_bar(bar)
            if realized:
                equity += sum(realized)
                self._portfolio.set_account(
                    equity=equity, realized_pnl_today=equity - self._paper_equity
                )
                still_open = {p.ticket_id for p in self._broker.get_positions()}
                for ticket in open_before - still_open:
                    self._pos_repo.close(ticket)
                self._portfolio.sync()
            self._broker.set_fill_price(bar.close)
            self._on_bar(bar)
            positions = self._broker.get_positions()
            unrealized = sum(p.unrealized_pnl for p in positions)
            closed = self._broker.closed_pnls
            self.equity_curve.append(equity + unrealized)
            self.stats = {
                "symbol": symbol,
                "tf": tf,
                "bars_total": frame.height,
                "bars_done": bars_fed,
                "equity": equity,
                "unrealized": unrealized,
                "starting_equity": self._paper_equity,
                "trades": len(closed),
                "wins": sum(1 for pnl in closed if pnl > 0),
                "open_positions": [
                    (p.symbol, p.direction.value, p.volume_lots, p.open_price, p.unrealized_pnl)
                    for p in positions
                ],
                "signals": self._stat_signals,
                "rejected": self._stat_rejected,
            }
            if delay:
                time.sleep(delay)
        if last_close:
            for pos in self._broker.get_positions():
                self._pos_repo.close(pos.ticket_id)
            equity += sum(self._broker.force_close_all(last_close))
        self.paper_result = {
            "symbol": symbol,
            "tf": tf,
            "bars_replayed": bars_fed,
            "trades": len(self._broker.closed_pnls),
            "starting_equity": self._paper_equity,
            "final_equity": round(equity, 2),
            "total_pnl": round(equity - self._paper_equity, 2),
        }
        _logger.info("paper_replay_complete", **self.paper_result)
        self._running = False

    def run(self) -> None:
        self._sm.fire(Event.CONFIG_VALIDATED)
        self._sm.fire(Event.CONNECT_ATTEMPT)
        self._broker = self._paper_broker() if self._mode == "paper" else self._ctx.bridge_broker()
        self._broker.connect(self._ctx.config.runtime.mt5_connect_timeout_ms)
        self._sm.fire(Event.EA_ACK)
        self._sm.fire(Event.RECONCILE_START)
        self._reconcile()
        self._build_engines()
        self._portfolio.sync()
        self._broker.subscribe_bars(self._on_bar)
        self._sm.fire(Event.DIFF_RESOLVED)
        if self._mode == "paper":
            self._portfolio.set_account(
                equity=self._paper_equity, equity_session_start=self._paper_equity
            )
            self._start_paper_feed()
        _write_state(self._ctx, state=self._sm.state.value, mode=self._mode, started_ms=int(time.time() * 1000))
        _set_control(self._ctx, "run")
        _logger.info("trade_running", mode=self._mode)
        try:
            self._loop()
        finally:
            self._shutdown()

    def _loop(self) -> None:
        interval = self._ctx.config.runtime.heartbeat_interval_ms / 1000.0
        while self._running:
            action = _read_control(self._ctx)
            if action == "stop":
                # Also stop the paper feed thread, which watches _running.
                self._running = False
                break
            if action == "halt" and self._sm.state == State.RUNNING:
                self._sm.fire(Event.MANUAL_HALT)
            elif action == "resume" and self._sm.state == State.SAFE_HALT:
                self._sm.fire(Event.HEARTBEAT_RESUMED)
                self._reconcile()
                self._sm.fire(Event.DIFF_RESOLVED)
                _set_control(self._ctx, "run")
            # Paper replay has no EA heartbeat to miss.
            if (
                self._mode != "paper"
                and self._sm.state == State.RUNNING
                and self._broker._heartbeat.is_stale()
            ):
                self._sm.fire(Event.HEARTBEAT_MISS_THRESHOLD)
            _write_state(self._ctx, state=self._sm.state.value, mode=self._mode)
            time.sleep(interval)

    def _shutdown(self) -> None:
        if self._feed_thread is not None:
            self._feed_thread.join(timeout=5.0)
        if not self._sm.is_terminal and self._sm.state != State.SHUTTING_DOWN:
            try:
                self._sm.fire(Event.SHUTDOWN_CMD)
            except Exception:
                pass
        if self._broker is not None:
            self._broker.disconnect()
        try:
            self._sm.fire(Event.SHUTDOWN_COMPLETE)
        except Exception:
            pass
        _write_state(self._ctx, state=self._sm.state.value, mode=self._mode)
        _logger.info("trade_stopped")

    def request_stop(self) -> None:
        self._running = False


@app.command()
@guard
def start(
    ctx: typer.Context,
    mode: str = typer.Option(None, "--mode", help="live|paper (default: runtime.mode from config)"),
    profile: str = typer.Option(None, "--profile", help="Config profile to trade with"),
    symbol: str = typer.Option(None, "--symbol", help="Paper mode: cached symbol to replay (default: largest cache)"),
    tf: str = typer.Option(None, "--tf", help="Paper mode: cached timeframe to replay"),
    speed: float = typer.Option(20.0, "--speed", help="Paper mode: replay speed in bars/second (0 = as fast as possible)"),
    equity: float = typer.Option(10_000.0, "--equity", help="Paper mode: starting account equity"),
    dashboard: bool | None = typer.Option(None, "--dashboard/--no-dashboard", help="Paper mode: live progress dashboard (default: auto when on a terminal)"),
) -> None:
    app_ctx = get_context(ctx)
    run_mode = mode or app_ctx.config.runtime.mode.value
    if app_ctx.options.dry_run:
        output_obj(ctx, {"dry_run": True, "action": "start", "mode": run_mode}, title="trade start")
        return
    runtime = LiveRuntime(
        app_ctx,
        mode=run_mode,
        paper_symbol=symbol,
        paper_tf=tf,
        paper_speed=speed,
        paper_equity=equity,
    )
    signal_mod.signal(signal_mod.SIGINT, lambda *_a: runtime.request_stop())
    use_dashboard = (
        run_mode == "paper"
        and app_ctx.options.output != "json"
        and (dashboard if dashboard is not None else sys.stdout.isatty())
    )
    if use_dashboard:
        from cocoon.cli.dashboard.paper_view import run_paper_dashboard
        from cocoon.core.logging.setup import quiet_console_logging

        quiet_console_logging()
        run_paper_dashboard(runtime)
    else:
        output_obj(ctx, {"mode": run_mode, "status": "started", "stop": "Ctrl-C"}, title="trade start")
        runtime.run()
    if runtime.paper_result is not None:
        output_obj(ctx, runtime.paper_result, title="paper session summary")


@app.command()
@guard
def stop(ctx: typer.Context) -> None:
    app_ctx = get_context(ctx)
    _set_control(app_ctx, "stop")
    output_obj(ctx, {"signal": "stop", "status": "sent"}, title="trade stop")


@app.command()
@guard
def halt(
    ctx: typer.Context,
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt"),
) -> None:
    app_ctx = get_context(ctx)
    if not (yes or app_ctx.options.yes):
        typer.confirm("Halt trading (SAFE_HALT)?", abort=True)
    _set_control(app_ctx, "halt")
    output_obj(ctx, {"signal": "halt", "status": "sent"}, title="trade halt")


@app.command()
@guard
def resume(ctx: typer.Context) -> None:
    app_ctx = get_context(ctx)
    _set_control(app_ctx, "resume")
    output_obj(ctx, {"signal": "resume", "status": "sent"}, title="trade resume")


@app.command()
@guard
def status(
    ctx: typer.Context,
    watch: bool = typer.Option(False, "--watch", help="Live-refreshing dashboard instead of a one-shot view"),
) -> None:
    app_ctx = get_context(ctx)
    from cocoon.cli.dashboard.live_view import render_once, watch_dashboard

    if watch:
        watch_dashboard(app_ctx)
    else:
        state = _read_state(app_ctx)
        if app_ctx.options.output == "json":
            output_obj(ctx, state, title="trade status")
        else:
            render_once(app_ctx)
