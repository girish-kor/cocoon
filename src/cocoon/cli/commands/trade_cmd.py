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
import time
from pathlib import Path

import typer

from cocoon.cli import console, get_context, guard, output_obj
from cocoon.core.errors.exceptions import ModelError
from cocoon.core.interfaces.broker_adapter import Bar, OrderDirection, OrderIntent
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
    def __init__(self, app_ctx, *, mode: str) -> None:
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
        self._running = True

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
            order_repo=None,
            audit_logger=self._audit,
        )

    def _reconcile(self) -> None:
        from cocoon.persistence.repositories import OrderRepository, PositionRepository
        from cocoon.trading.order.reconciliation import ReconciliationManager

        db = self._ctx.database()
        manager = ReconciliationManager(
            broker=self._broker,
            position_repo=PositionRepository(db),
            order_repo=OrderRepository(db),
        )
        manager.reconcile(raise_on_conflict=True)

    def _on_bar(self, bar: Bar) -> None:
        try:
            self._md.ingest_bar(bar, persist=False)
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
            return
        key = make_idempotency_key(
            symbol=bar.symbol,
            direction=sig.direction,
            signal_ts_unix_ms=bar.ts_unix_ms,
            model_version_hash=model_hash,
        )
        self._order.submit(
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

    def run(self) -> None:
        self._sm.fire(Event.CONFIG_VALIDATED)
        self._sm.fire(Event.CONNECT_ATTEMPT)
        self._broker = self._ctx.bridge_broker()
        self._broker.connect(self._ctx.config.runtime.mt5_connect_timeout_ms)
        self._sm.fire(Event.EA_ACK)
        self._sm.fire(Event.RECONCILE_START)
        self._reconcile()
        self._build_engines()
        self._portfolio.sync()
        self._broker.subscribe_bars(self._on_bar)
        self._sm.fire(Event.DIFF_RESOLVED)
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
                break
            if action == "halt" and self._sm.state == State.RUNNING:
                self._sm.fire(Event.MANUAL_HALT)
            elif action == "resume" and self._sm.state == State.SAFE_HALT:
                self._sm.fire(Event.HEARTBEAT_RESUMED)
                self._reconcile()
                self._sm.fire(Event.DIFF_RESOLVED)
                _set_control(self._ctx, "run")
            if self._sm.state == State.RUNNING and self._broker._heartbeat.is_stale():
                self._sm.fire(Event.HEARTBEAT_MISS_THRESHOLD)
            _write_state(self._ctx, state=self._sm.state.value, mode=self._mode)
            time.sleep(interval)

    def _shutdown(self) -> None:
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
    mode: str = typer.Option(None, "--mode", help="live|paper"),
    profile: str = typer.Option(None, "--profile"),
) -> None:
    app_ctx = get_context(ctx)
    run_mode = mode or app_ctx.config.runtime.mode.value
    if app_ctx.options.dry_run:
        console.print(f"[dim]dry-run: would start trading mode={run_mode}[/]")
        return
    runtime = LiveRuntime(app_ctx, mode=run_mode)
    signal_mod.signal(signal_mod.SIGINT, lambda *_a: runtime.request_stop())
    console.print(f"[bold cyan]Cocoon trading started[/] mode={run_mode} (Ctrl-C to stop)")
    runtime.run()


@app.command()
@guard
def stop(ctx: typer.Context) -> None:
    app_ctx = get_context(ctx)
    _set_control(app_ctx, "stop")
    console.print("[green]stop signal sent[/]")


@app.command()
@guard
def halt(
    ctx: typer.Context,
    yes: bool = typer.Option(False, "--yes"),
) -> None:
    app_ctx = get_context(ctx)
    if not (yes or app_ctx.options.yes):
        typer.confirm("Halt trading (SAFE_HALT)?", abort=True)
    _set_control(app_ctx, "halt")
    console.print("[yellow]halt signal sent[/]")


@app.command()
@guard
def resume(ctx: typer.Context) -> None:
    app_ctx = get_context(ctx)
    _set_control(app_ctx, "resume")
    console.print("[green]resume signal sent[/]")


@app.command()
@guard
def status(
    ctx: typer.Context,
    watch: bool = typer.Option(False, "--watch"),
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
