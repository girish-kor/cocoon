"""Risk Engine. DOCUMENT.md §9.2, §12.

Runs the §9.2 pre-trade check sequence; the first failure short-circuits and
logs the reason. Pass/fail decision only — it never submits orders (§12).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cocoon.core.logging.audit import AuditLogger
from cocoon.core.logging.setup import get_logger
from cocoon.trading.risk.checks import (
    CHECK_SEQUENCE,
    CheckContext,
    CheckResult,
    ProposedOrder,
)

_logger = get_logger(__name__)


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    results: list[CheckResult] = field(default_factory=list)
    rejected_by: str | None = None
    reason: str | None = None


class RiskEngine:
    def __init__(self, *, audit_logger: AuditLogger | None = None) -> None:
        self._audit = audit_logger

    def evaluate(self, order: ProposedOrder, ctx: CheckContext) -> RiskDecision:
        results: list[CheckResult] = []
        for check in CHECK_SEQUENCE:
            result = check(order, ctx)
            results.append(result)
            if not result.passed:
                decision = RiskDecision(
                    approved=False,
                    results=results,
                    rejected_by=result.name,
                    reason=result.reason,
                )
                _logger.info(
                    "risk_rejected",
                    symbol=order.symbol,
                    check=result.name,
                    reason=result.reason,
                )
                self._audit_decision(order, decision)
                return decision

        decision = RiskDecision(approved=True, results=results)
        _logger.info("risk_approved", symbol=order.symbol)
        self._audit_decision(order, decision)
        return decision

    def _audit_decision(self, order: ProposedOrder, decision: RiskDecision) -> None:
        if self._audit is None:
            return
        self._audit.record(
            "RISK_DECISION",
            {
                "symbol": order.symbol,
                "direction": order.direction.value,
                "approved": decision.approved,
                "rejected_by": decision.rejected_by,
                "reason": decision.reason,
                "checks": [
                    {"name": r.name, "passed": r.passed, "reason": r.reason}
                    for r in decision.results
                ],
            },
        )
