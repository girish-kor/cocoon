"""ZMQ-backed BrokerAdapter. DOCUMENT.md §6, §9, §13, §15.2, §18.

The single authoritative ZMQ client to the EA (§12: bridge/broker_adapter
owns request queuing, holds no trading decisions). All order flow funnels
through one instance with an internal single-flight REQ queue, satisfying
§1.2's "MT5 does not tolerate concurrent writers". Implements the L0
BrokerAdapter contract so the trading layer never knows it is talking ZMQ.
"""

from __future__ import annotations

import threading
import time

from cocoon.bridge.heartbeat import HeartbeatMonitor
from cocoon.bridge.protocol import MessageType
from cocoon.bridge.zmq_endpoint import ZmqEndpoint
from cocoon.core.errors.exceptions import MT5ConnectTimeoutError
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

_logger = get_logger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


class ZmqBrokerAdapter(BrokerAdapter):
    def __init__(
        self,
        *,
        endpoint: ZmqEndpoint,
        heartbeat: HeartbeatMonitor,
    ) -> None:
        self._endpoint = endpoint
        self._heartbeat = heartbeat
        self._connected = False
        self._session_id = ""
        self._bar_callback: BarCallback | None = None
        self._poll_thread: threading.Thread | None = None
        self._stop = threading.Event()

    def connect(self, timeout_ms: int) -> None:
        self._endpoint.connect(req_timeout_ms=timeout_ms)
        try:
            reply = self._endpoint.request(
                MessageType.HELLO, {"protocol": "cocoon"}, ts_unix_ms=_now_ms()
            )
        except Exception as exc:
            raise MT5ConnectTimeoutError(
                "MT5 EA did not ACK HELLO within timeout",
                context={"timeout_ms": timeout_ms, "error": str(exc)},
            ) from exc
        if reply.get("type") != MessageType.ACK.value:
            raise MT5ConnectTimeoutError(
                "Unexpected reply to HELLO handshake",
                context={"reply_type": reply.get("type")},
            )
        self._session_id = reply.get("session_id", "")
        self._endpoint.set_session_id(self._session_id)
        self._connected = True
        self._heartbeat.on_heartbeat(_now_ms())
        self._start_poll_loop()
        _logger.info("bridge_connected", session_id=self._session_id)

    def disconnect(self) -> None:
        self._stop.set()
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=2.0)
        self._endpoint.close()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def last_heartbeat_ts_unix_ms(self) -> int | None:
        return self._heartbeat.last_heartbeat_ms

    def submit_order(self, intent: OrderIntent) -> OrderResult:
        reply = self._endpoint.request(
            MessageType.ORDER_SUBMIT,
            {
                "idempotency_key": intent.idempotency_key,
                "symbol": intent.symbol,
                "direction": intent.direction.value,
                "volume_lots": intent.volume_lots,
                "stop_loss_price": intent.stop_loss_price,
                "take_profit_price": intent.take_profit_price,
                "max_slippage_pips": intent.max_slippage_pips,
            },
            ts_unix_ms=_now_ms(),
        )
        return self._parse_order_result(reply, intent.idempotency_key)

    def cancel_order(self, ticket_id: int) -> OrderResult:
        reply = self._endpoint.request(
            MessageType.ORDER_CANCEL,
            {"broker_ticket_id": ticket_id},
            ts_unix_ms=_now_ms(),
        )
        return self._parse_order_result(reply, "")

    def modify_order(
        self,
        ticket_id: int,
        *,
        stop_loss_price: float | None,
        take_profit_price: float | None,
    ) -> OrderResult:
        reply = self._endpoint.request(
            MessageType.ORDER_MODIFY,
            {
                "broker_ticket_id": ticket_id,
                "stop_loss_price": stop_loss_price,
                "take_profit_price": take_profit_price,
            },
            ts_unix_ms=_now_ms(),
        )
        return self._parse_order_result(reply, "")

    def get_positions(self) -> list[BrokerPosition]:
        reply = self._endpoint.request(
            MessageType.POSITIONS_QUERY, {}, ts_unix_ms=_now_ms()
        )
        rows = reply.get("payload", {}).get("positions", [])
        return [self._parse_position(r) for r in rows]

    def get_orders(self) -> list[BrokerOrder]:
        reply = self._endpoint.request(
            MessageType.ORDERS_QUERY, {}, ts_unix_ms=_now_ms()
        )
        rows = reply.get("payload", {}).get("orders", [])
        return [self._parse_order(r) for r in rows]

    def subscribe_bars(self, callback: BarCallback) -> None:
        self._bar_callback = callback

    def _start_poll_loop(self) -> None:
        self._stop.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop, name="cocoon-bridge-poll", daemon=True
        )
        self._poll_thread.start()

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                msg = self._endpoint.poll_pub(timeout_ms=100)
            except Exception as exc:
                _logger.warning("bridge_poll_error", error=str(exc))
                continue
            if msg is None:
                continue
            self._dispatch(msg)

    def _dispatch(self, msg: dict) -> None:
        msg_type = msg.get("type")
        if msg_type == MessageType.HEARTBEAT.value:
            self._heartbeat.on_heartbeat(msg.get("ts", _now_ms()))
        elif msg_type == MessageType.BAR_CLOSED.value and self._bar_callback:
            payload = msg.get("payload", {})
            bar = Bar(
                symbol=payload.get("symbol", ""),
                timeframe=payload.get("timeframe", ""),
                ts_unix_ms=int(msg.get("ts", 0)),
                open=float(payload.get("open", 0.0)),
                high=float(payload.get("high", 0.0)),
                low=float(payload.get("low", 0.0)),
                close=float(payload.get("close", 0.0)),
                volume=float(payload.get("volume", 0.0)),
            )
            self._bar_callback(bar)

    @staticmethod
    def _parse_order_result(reply: dict, fallback_key: str) -> OrderResult:
        payload = reply.get("payload", reply)
        return OrderResult(
            idempotency_key=payload.get("idempotency_key", fallback_key),
            status=OrderStatus(payload.get("status", OrderStatus.REJECTED_BY_BROKER.value)),
            broker_ticket_id=payload.get("broker_ticket_id"),
            filled_volume_lots=float(payload.get("filled_volume_lots", 0.0)),
            filled_price=payload.get("filled_price"),
            reject_reason=payload.get("reject_reason"),
        )

    @staticmethod
    def _parse_position(row: dict) -> BrokerPosition:
        return BrokerPosition(
            ticket_id=int(row["broker_ticket_id"]),
            symbol=row["symbol"],
            direction=OrderDirection(row["direction"]),
            volume_lots=float(row["volume_lots"]),
            open_price=float(row["open_price"]),
            current_price=float(row.get("current_price", row["open_price"])),
            stop_loss_price=row.get("stop_loss_price"),
            take_profit_price=row.get("take_profit_price"),
            unrealized_pnl=float(row.get("unrealized_pnl", 0.0)),
            origin=PositionOrigin(row.get("origin", PositionOrigin.INTERNAL.value)),
        )

    @staticmethod
    def _parse_order(row: dict) -> BrokerOrder:
        return BrokerOrder(
            ticket_id=int(row["broker_ticket_id"]),
            symbol=row["symbol"],
            direction=OrderDirection(row["direction"]),
            volume_lots=float(row["volume_lots"]),
            requested_price=float(row.get("requested_price", 0.0)),
            stop_loss_price=row.get("stop_loss_price"),
            take_profit_price=row.get("take_profit_price"),
            status=OrderStatus(row.get("status", OrderStatus.SUBMITTED.value)),
            origin=PositionOrigin(row.get("origin", PositionOrigin.INTERNAL.value)),
        )
