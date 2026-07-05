"""Reconciliation. DOCUMENT.md §9.6.

On STATE_RECONCILING: fetch broker-reported open positions + pending orders,
diff against local SQLite by broker ticket id. Three outcomes:
  (a) match -> proceed;
  (b) broker has a position/order the local DB doesn't -> import as
      origin=external, do NOT auto-close;
  (c) local DB has an open order the broker doesn't recognise (crashed
      mid-submit) -> mark FAILED_PERMANENT locally, do NOT resubmit blindly
      (resubmission is only safe via the §9.5 idempotency path).

Unresolved conflict -> ReconciliationConflictError (exit 21).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cocoon.core.errors.exceptions import ReconciliationConflictError
from cocoon.core.interfaces.broker_adapter import (
    BrokerAdapter,
    OrderStatus,
    PositionOrigin,
)
from cocoon.core.logging.setup import get_logger

_logger = get_logger(__name__)


@dataclass
class ReconciliationReport:
    matched_positions: list[int] = field(default_factory=list)
    imported_external_positions: list[int] = field(default_factory=list)
    orphaned_local_orders: list[str] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.conflicts


class ReconciliationManager:
    def __init__(
        self,
        *,
        broker: BrokerAdapter,
        position_repo,
        order_repo,
    ) -> None:
        self._broker = broker
        self._positions = position_repo
        self._orders = order_repo

    def reconcile(self, *, raise_on_conflict: bool = True) -> ReconciliationReport:
        report = ReconciliationReport()
        broker_positions = {p.ticket_id: p for p in self._broker.get_positions()}
        broker_orders = {o.ticket_id for o in self._broker.get_orders()}
        local_open_tickets = self._positions.open_tickets()

        for ticket, pos in broker_positions.items():
            if ticket in local_open_tickets:
                report.matched_positions.append(ticket)
            else:
                self._positions.upsert_by_ticket(
                    broker_ticket_id=ticket,
                    symbol=pos.symbol,
                    direction=pos.direction.value,
                    volume_lots=pos.volume_lots,
                    open_price=pos.open_price,
                    stop_loss_price=pos.stop_loss_price,
                    take_profit_price=pos.take_profit_price,
                    unrealized_pnl=pos.unrealized_pnl,
                    origin=PositionOrigin.EXTERNAL.value,
                    is_open=True,
                )
                report.imported_external_positions.append(ticket)
                _logger.info("recon_imported_external", ticket=ticket)

        for ticket in local_open_tickets:
            if ticket not in broker_positions:
                report.conflicts.append(
                    {
                        "type": "local_position_missing_at_broker",
                        "ticket": ticket,
                    }
                )
                _logger.warning("recon_conflict_local_position", ticket=ticket)

        for order in self._orders.list_open():
            ticket = order.get("broker_ticket_id")
            if ticket is None or ticket not in broker_orders:
                if ticket is not None and ticket in broker_positions:
                    continue
                self._orders.set_status(
                    order["idempotency_key"],
                    OrderStatus.FAILED_PERMANENT.value,
                    reject_reason="orphaned_on_reconcile",
                )
                report.orphaned_local_orders.append(order["idempotency_key"])
                _logger.info(
                    "recon_orphaned_order", key=order["idempotency_key"]
                )

        if report.conflicts and raise_on_conflict:
            raise ReconciliationConflictError(
                "Unresolved reconciliation conflict requires manual resolution",
                context={"conflicts": report.conflicts},
            )
        return report
