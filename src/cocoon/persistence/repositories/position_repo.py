"""Position repository. DOCUMENT.md §9.3, §9.6."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from cocoon.persistence.db import Database
from cocoon.persistence.models import Position


class PositionRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def upsert_by_ticket(self, **fields: Any) -> int:
        ticket = fields["broker_ticket_id"]
        with self._db.session() as s:
            existing = s.scalar(
                select(Position).where(Position.broker_ticket_id == ticket)
            )
            if existing is None:
                pos = Position(**fields)
                s.add(pos)
                s.flush()
                return int(pos.id)
            for name, value in fields.items():
                setattr(existing, name, value)
            s.flush()
            return int(existing.id)

    def close(self, ticket_id: int) -> None:
        with self._db.session() as s:
            pos = s.scalar(
                select(Position).where(Position.broker_ticket_id == ticket_id)
            )
            if pos is None:
                return
            pos.is_open = False
            pos.closed_at = datetime.now(timezone.utc)

    def get_by_ticket(self, ticket_id: int) -> dict[str, Any] | None:
        with self._db.session() as s:
            pos = s.scalar(
                select(Position).where(Position.broker_ticket_id == ticket_id)
            )
            return self._to_dict(pos) if pos else None

    def list_open(self) -> list[dict[str, Any]]:
        with self._db.session() as s:
            rows = s.scalars(
                select(Position).where(Position.is_open.is_(True))
            ).all()
            return [self._to_dict(p) for p in rows]

    def open_tickets(self) -> set[int]:
        return {int(p["broker_ticket_id"]) for p in self.list_open()}

    @staticmethod
    def _to_dict(pos: Position) -> dict[str, Any]:
        return {
            "id": pos.id,
            "broker_ticket_id": pos.broker_ticket_id,
            "symbol": pos.symbol,
            "direction": pos.direction,
            "volume_lots": pos.volume_lots,
            "open_price": pos.open_price,
            "stop_loss_price": pos.stop_loss_price,
            "take_profit_price": pos.take_profit_price,
            "unrealized_pnl": pos.unrealized_pnl,
            "origin": pos.origin,
            "is_open": pos.is_open,
        }
