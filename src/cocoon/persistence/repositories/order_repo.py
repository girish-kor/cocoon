"""Order repository. DOCUMENT.md §9.4, §9.5, §9.6."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from cocoon.persistence.db import Database
from cocoon.persistence.models import Order


class OrderRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def upsert_by_idempotency_key(self, **fields: Any) -> int:
        key = fields["idempotency_key"]
        with self._db.session() as s:
            existing = s.scalar(
                select(Order).where(Order.idempotency_key == key)
            )
            if existing is None:
                order = Order(**fields)
                s.add(order)
                s.flush()
                return int(order.id)
            for name, value in fields.items():
                setattr(existing, name, value)
            s.flush()
            return int(existing.id)

    def set_status(
        self,
        idempotency_key: str,
        status: str,
        *,
        broker_ticket_id: int | None = None,
        filled_volume_lots: float | None = None,
        filled_price: float | None = None,
        reject_reason: str | None = None,
    ) -> None:
        with self._db.session() as s:
            order = s.scalar(
                select(Order).where(Order.idempotency_key == idempotency_key)
            )
            if order is None:
                return
            order.status = status
            if broker_ticket_id is not None:
                order.broker_ticket_id = broker_ticket_id
            if filled_volume_lots is not None:
                order.filled_volume_lots = filled_volume_lots
            if filled_price is not None:
                order.filled_price = filled_price
            if reject_reason is not None:
                order.reject_reason = reject_reason

    def get_by_idempotency_key(self, key: str) -> dict[str, Any] | None:
        with self._db.session() as s:
            order = s.scalar(select(Order).where(Order.idempotency_key == key))
            return self._to_dict(order) if order else None

    def get_by_ticket(self, ticket_id: int) -> dict[str, Any] | None:
        with self._db.session() as s:
            order = s.scalar(
                select(Order).where(Order.broker_ticket_id == ticket_id)
            )
            return self._to_dict(order) if order else None

    def list_open(self) -> list[dict[str, Any]]:
        open_states = (
            "SUBMITTED",
            "ACKNOWLEDGED",
            "RETRYING",
            "PARTIALLY_FILLED",
        )
        with self._db.session() as s:
            rows = s.scalars(
                select(Order).where(Order.status.in_(open_states))
            ).all()
            return [self._to_dict(o) for o in rows]

    def list_all(self) -> list[dict[str, Any]]:
        with self._db.session() as s:
            rows = s.scalars(select(Order).order_by(Order.id)).all()
            return [self._to_dict(o) for o in rows]

    @staticmethod
    def _to_dict(order: Order) -> dict[str, Any]:
        return {
            "id": order.id,
            "idempotency_key": order.idempotency_key,
            "symbol": order.symbol,
            "direction": order.direction,
            "volume_lots": order.volume_lots,
            "stop_loss_price": order.stop_loss_price,
            "take_profit_price": order.take_profit_price,
            "status": order.status,
            "broker_ticket_id": order.broker_ticket_id,
            "filled_volume_lots": order.filled_volume_lots,
            "filled_price": order.filled_price,
            "reject_reason": order.reject_reason,
            "origin": order.origin,
            "signal_ts_unix_ms": order.signal_ts_unix_ms,
            "model_version_hash": order.model_version_hash,
        }
