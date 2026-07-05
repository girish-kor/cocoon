"""Exception hierarchy. Authoritative source: DOCUMENT.md §17.

Every exception carries a structured `.context: dict` because the audit
trail requirement (NFR §3, "every ... must be reconstructable from logs
alone") depends on structured context existing at the point an error is
raised, not reconstructed after the fact from a string message.

`CocoonError.__init__` requires a non-empty `context` mapping. This is a
deliberate hard constraint: `raise CocoonError("something broke")` with
no context is a defect, not a valid usage of this hierarchy, so the base
constructor rejects it rather than silently allowing message-only errors
to slip past code review.
"""

from __future__ import annotations

from typing import Any

from cocoon.core.errors.exit_codes import ExitCode


class CocoonError(Exception):
    """Base of the Cocoon exception hierarchy.

    Subclasses that terminate the process must define a class-level
    `exit_code: ExitCode | None`. Subclasses that are caught internally
    and never surface as a process exit (e.g. DuplicateSubmissionError)
    leave `exit_code = None`.
    """

    exit_code: ExitCode | None = None

    def __init__(self, message: str, *, context: dict[str, Any]) -> None:
        if not context:
            raise ValueError(
                f"{type(self).__name__} requires non-empty structured "
                f"context; bare string-only raises are not permitted "
                f"(DOCUMENT.md §17)."
            )
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = dict(context)

    def to_log_record(self) -> dict[str, Any]:
        return {
            "error_type": type(self).__name__,
            "message": self.message,
            "exit_code": int(self.exit_code) if self.exit_code is not None else None,
            "context": self.context,
        }


# ---------------------------------------------------------------------------
# ConfigError
# ---------------------------------------------------------------------------


class ConfigError(CocoonError):
    pass


class ConfigValidationError(ConfigError):
    exit_code = ExitCode.CONFIG_VALIDATION_FAILURE


class SecretInConfigFileError(ConfigError):
    exit_code = ExitCode.SECRET_IN_CONFIG_FILE


# ---------------------------------------------------------------------------
# BridgeError
# ---------------------------------------------------------------------------


class BridgeError(CocoonError):
    pass


class MT5ConnectTimeoutError(BridgeError):
    exit_code = ExitCode.MT5_CONNECT_TIMEOUT


class ReconciliationConflictError(BridgeError):
    exit_code = ExitCode.RECONCILE_FAILED


class ProtocolVersionMismatchError(BridgeError):
    exit_code = ExitCode.BRIDGE_PROTOCOL_MISMATCH


# ---------------------------------------------------------------------------
# DataError
# ---------------------------------------------------------------------------


class DataError(CocoonError):
    pass


class FeatureLeakageGuardError(DataError):
    """Raised if a FeatureFn attempts out-of-slice (future-index) access.

    No exit code: this must never occur in correct code (the pipeline
    prevents the physical possibility per §7.3), so if it fires it is a
    programming defect in a FeatureFn, surfaced immediately rather than
    silently caught, but it does not have a dedicated exit code in §16 —
    it propagates as DatasetIntegrityError context at the call site that
    catches it.
    """

    exit_code = None


class DatasetIntegrityError(DataError):
    exit_code = ExitCode.DATASET_BUILD_FAILURE


# ---------------------------------------------------------------------------
# TrainingError
# ---------------------------------------------------------------------------


class TrainingError(CocoonError):
    pass


class HPOExhaustedError(TrainingError):
    exit_code = ExitCode.TRAINING_FAILURE


# ---------------------------------------------------------------------------
# ModelError
# ---------------------------------------------------------------------------


class ModelError(CocoonError):
    pass


class ModelPromotionError(ModelError):
    exit_code = ExitCode.MODEL_PROMOTION_FAILURE


# ---------------------------------------------------------------------------
# RiskError
# ---------------------------------------------------------------------------


class RiskError(CocoonError):
    pass


class DailyLossLimitHitError(RiskError):
    """Not a bug — an intentional trading halt (DOCUMENT.md §17)."""

    exit_code = ExitCode.RISK_HARD_STOP


# ---------------------------------------------------------------------------
# OrderError
# ---------------------------------------------------------------------------


class OrderError(CocoonError):
    pass


class OrderRetryExhaustedError(OrderError):
    exit_code = ExitCode.ORDER_SUBMIT_FAILED_PERMANENT


class DuplicateSubmissionError(OrderError):
    """Caught internally at the idempotency layer; never surfaces as a
    process crash or exit-code path — it resolves to a no-op returning
    the cached prior result (§9.5)."""

    exit_code = None


# ---------------------------------------------------------------------------
# PluginError
# ---------------------------------------------------------------------------


class PluginError(CocoonError):
    pass


class PluginInterfaceError(PluginError):
    exit_code = ExitCode.PLUGIN_LOAD_FAILURE
