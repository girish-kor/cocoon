"""Signal Engine. DOCUMENT.md §9.1, §7.1.

Consumes the ensemble P(up) + live features. Applies:
  - threshold filter: max(p, 1-p) >= min_confidence
  - regime filter: blocks when atr(14)/atr_sma(14,50) > regime_volatility_cap
Emits SignalIntent{symbol, direction, confidence, ts, model_version_hash}.
"""

from __future__ import annotations

from dataclasses import dataclass

from cocoon.core.config.schema import RiskConfig
from cocoon.core.interfaces.broker_adapter import OrderDirection
from cocoon.core.logging.setup import get_logger

_logger = get_logger(__name__)


@dataclass(frozen=True)
class SignalIntent:
    symbol: str
    direction: OrderDirection
    confidence: float
    ts_unix_ms: int
    model_version_hash: str


class SignalEngine:
    def __init__(self, *, risk_config: RiskConfig) -> None:
        self._min_confidence = risk_config.min_confidence
        self._regime_cap = risk_config.regime_volatility_cap

    def evaluate(
        self,
        *,
        symbol: str,
        probability_up: float,
        ts_unix_ms: int,
        model_version_hash: str,
        atr: float | None = None,
        atr_sma: float | None = None,
    ) -> SignalIntent | None:
        if atr is not None and atr_sma is not None and atr_sma > 0:
            regime = atr / atr_sma
            if regime > self._regime_cap:
                _logger.info(
                    "signal_blocked_regime",
                    symbol=symbol,
                    regime=regime,
                    cap=self._regime_cap,
                )
                return None

        if probability_up >= 0.5:
            direction = OrderDirection.BUY
            confidence = probability_up
        else:
            direction = OrderDirection.SELL
            confidence = 1.0 - probability_up

        if confidence < self._min_confidence:
            _logger.debug(
                "signal_below_threshold",
                symbol=symbol,
                confidence=confidence,
                threshold=self._min_confidence,
            )
            return None

        intent = SignalIntent(
            symbol=symbol,
            direction=direction,
            confidence=confidence,
            ts_unix_ms=ts_unix_ms,
            model_version_hash=model_version_hash,
        )
        _logger.info(
            "signal_generated",
            symbol=symbol,
            direction=direction.value,
            confidence=confidence,
        )
        return intent
