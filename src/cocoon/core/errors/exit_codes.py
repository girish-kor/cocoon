"""Exit code catalogue. Authoritative source: DOCUMENT.md §16.

No other module may hardcode an integer exit code; all exits reference
these constants so the mapping stays single-sourced.
"""

from __future__ import annotations

import enum


class ExitCode(enum.IntEnum):
    SUCCESS = 0
    GENERIC_ERROR = 1
    CONFIG_VALIDATION_FAILURE = 10
    SECRET_IN_CONFIG_FILE = 11
    MT5_CONNECT_TIMEOUT = 20
    RECONCILE_FAILED = 21
    DATASET_BUILD_FAILURE = 30
    TRAINING_FAILURE = 31
    MODEL_PROMOTION_FAILURE = 32
    RISK_HARD_STOP = 40
    ORDER_SUBMIT_FAILED_PERMANENT = 41
    BRIDGE_PROTOCOL_MISMATCH = 50
    PLUGIN_LOAD_FAILURE = 60
    SIGINT_CLEAN_SHUTDOWN = 130


EXIT_CODE_DESCRIPTIONS: dict[ExitCode, str] = {
    ExitCode.SUCCESS: "Success",
    ExitCode.GENERIC_ERROR: "Generic unhandled error",
    ExitCode.CONFIG_VALIDATION_FAILURE: "Config validation failure",
    ExitCode.SECRET_IN_CONFIG_FILE: "Secret found in config file",
    ExitCode.MT5_CONNECT_TIMEOUT: "MT5 connect timeout (INIT_FAILED)",
    ExitCode.RECONCILE_FAILED: "Reconciliation conflict requiring manual resolution",
    ExitCode.DATASET_BUILD_FAILURE: "Dataset build failure (integrity check failed)",
    ExitCode.TRAINING_FAILURE: "Training failure (HPO exhausted without valid trial)",
    ExitCode.MODEL_PROMOTION_FAILURE: "Model promotion failure (validation metrics below threshold)",
    ExitCode.RISK_HARD_STOP: "Risk engine hard-stop (daily loss limit hit mid-session)",
    ExitCode.ORDER_SUBMIT_FAILED_PERMANENT: "Order submission permanently failed after retry exhaustion",
    ExitCode.BRIDGE_PROTOCOL_MISMATCH: "Bridge protocol version mismatch (Python schema vs EA schema)",
    ExitCode.PLUGIN_LOAD_FAILURE: "Plugin load failure (invalid entry point / interface non-conformance)",
    ExitCode.SIGINT_CLEAN_SHUTDOWN: "SIGINT received, clean shutdown completed",
}
