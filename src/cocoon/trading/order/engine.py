"""Order Engine. DOCUMENT.md §9.4, §9.5, §12.

Owns the order lifecycle, idempotency, and retry/backoff. Does NOT decide
risk (§12) — it receives an already-approved OrderIntent. All broker contact
is through the L0 BrokerAdapter interface, so the same engine runs against
the live ZMQ bridge or the SimulatedBrokerAdapter unchanged.
"""

from __future__ import annotations

import time
from typing import Callable

from cocoon.core.config.schema import OrderConfig
from cocoon.core.errors.exceptions import OrderRetryExhaustedError
from cocoon.core.interfaces.broker_adapter import (
    BrokerAdapter,
    OrderIntent,
    OrderResult,
    OrderStatus,
)
from cocoon.core.logging.audit import AuditLogger
from cocoon.core.logging.setup import get_logger
from cocoon.trading.order.idempotency import IdempotencyCache

_logger = get_logger(__name__)

_TERMINAL_OK = {
    OrderStatus.ACKNOWLEDGED,
    OrderStatus.FILLED,
    OrderStatus.PARTIALLY_FILLED,
}


class OrderEngine:
    def __init__(
        self,
        *,
        broker: BrokerAdapter,
        order_config: OrderConfig,
        idempotency: IdempotencyCache,
        order_repo=None,
        audit_logger: AuditLogger | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._broker = broker
        self._cfg = order_config
        self._idem = idempotency
        self._repo = order_repo
        self._audit = audit_logger
        self._sleep = sleep

    def submit(
        self,
        intent: OrderIntent,
        *,
        signal_ts_unix_ms: int | None = None,
        model_version_hash: str | None = None,
    ) -> OrderResult:
        cached = self._idem.get(intent.idempotency_key)
        if cached is not None:
            _logger.info("order_idempotent_hit", key=intent.idempotency_key)
            return cached

        self._persist(
            intent,
            OrderStatus.SUBMITTED,
            signal_ts_unix_ms=signal_ts_unix_ms,
            model_version_hash=model_version_hash,
        )

        attempts = max(1, self._cfg.retry_max_attempts)
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                result = self._broker.submit_order(intent)
            except Exception as exc:  # ambiguous failure -> retry path
                last_error = exc
                _logger.warning(
                    "order_submit_error",
                    key=intent.idempotency_key,
                    attempt=attempt,
                    error=str(exc),
                )
                self._persist(intent, OrderStatus.SUBMIT_TIMEOUT)
                if attempt < attempts - 1:
                    self._persist(intent, OrderStatus.RETRYING)
                    self._backoff(attempt)
                continue

            if result.status == OrderStatus.REJECTED_BY_BROKER:
                self._persist_result(intent, result)
                self._idem.put(intent.idempotency_key, result)
                self._audit_order(intent, result, attempt)
                return result

            if result.status in _TERMINAL_OK:
                self._persist_result(intent, result)
                self._idem.put(intent.idempotency_key, result)
                self._audit_order(intent, result, attempt)
                return result

            # unknown/timeout-like status -> retry
            self._persist(intent, OrderStatus.SUBMIT_TIMEOUT)
            if attempt < attempts - 1:
                self._persist(intent, OrderStatus.RETRYING)
                self._backoff(attempt)

        self._persist(intent, OrderStatus.FAILED_PERMANENT)
        raise OrderRetryExhaustedError(
            "Order submission permanently failed after retry exhaustion",
            context={
                "idempotency_key": intent.idempotency_key,
                "symbol": intent.symbol,
                "attempts": attempts,
                "last_error": str(last_error) if last_error else None,
            },
        )

    def cancel(self, ticket_id: int) -> OrderResult:
        result = self._broker.cancel_order(ticket_id)
        if self._repo is not None:
            self._repo.get_by_ticket(ticket_id)
        return result

    def modify(
        self,
        ticket_id: int,
        *,
        stop_loss_price: float | None,
        take_profit_price: float | None,
    ) -> OrderResult:
        return self._broker.modify_order(
            ticket_id,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
        )

    def _backoff(self, attempt: int) -> None:
        backoff = self._cfg.retry_backoff_ms
        ms = backoff[attempt] if attempt < len(backoff) else backoff[-1]
        self._sleep(ms / 1000.0)

    def _persist(
        self,
        intent: OrderIntent,
        status: OrderStatus,
        *,
        signal_ts_unix_ms: int | None = None,
        model_version_hash: str | None = None,
    ) -> None:
        if self._repo is None:
            return
        self._repo.upsert_by_idempotency_key(
            idempotency_key=intent.idempotency_key,
            symbol=intent.symbol,
            direction=intent.direction.value,
            volume_lots=intent.volume_lots,
            stop_loss_price=intent.stop_loss_price,
            take_profit_price=intent.take_profit_price,
            status=status.value,
            signal_ts_unix_ms=signal_ts_unix_ms,
            model_version_hash=model_version_hash,
        )

    def _persist_result(self, intent: OrderIntent, result: OrderResult) -> None:
        if self._repo is None:
            return
        self._repo.set_status(
            intent.idempotency_key,
            result.status.value,
            broker_ticket_id=result.broker_ticket_id,
            filled_volume_lots=result.filled_volume_lots,
            filled_price=result.filled_price,
            reject_reason=result.reject_reason,
        )

    def _audit_order(
        self, intent: OrderIntent, result: OrderResult, attempt: int
    ) -> None:
        if self._audit is None:
            return
        self._audit.record_order(
            {
                "idempotency_key": intent.idempotency_key,
                "symbol": intent.symbol,
                "direction": intent.direction.value,
                "volume_lots": intent.volume_lots,
                "status": result.status.value,
                "broker_ticket_id": result.broker_ticket_id,
                "filled_volume_lots": result.filled_volume_lots,
                "filled_price": result.filled_price,
                "reject_reason": result.reject_reason,
                "attempt": attempt,
            }
        )
