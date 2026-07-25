"""Config schema. Authoritative source: DOCUMENT.md §8.

Every section of the resolved config is a pydantic model so that
`cocoon config validate` is a schema check, not a smoke test: an unknown
key, a wrong type, or an out-of-range value fails resolution (exit 10)
before any engine is constructed. Defaults here mirror the scaffolded
`config/base.yaml` (cli/main.py `_BASE_YAML`) so a bare `resolve()` with
no files present yields a valid paper-mode config.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class LogLevel(str, enum.Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class RunMode(str, enum.Enum):
    PAPER = "paper"
    LIVE = "live"


class _StrictModel(BaseModel):
    """Unknown keys are config defects, not extensions — reject them so a
    typo (`max_dialy_loss_pct`) fails validation instead of silently
    falling back to the default it was meant to override."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class RuntimeConfig(_StrictModel):
    mode: RunMode = RunMode.PAPER
    log_level: LogLevel = LogLevel.INFO
    data_dir: str = "./data"
    mt5_connect_timeout_ms: int = Field(5000, ge=0)
    heartbeat_interval_ms: int = Field(1000, gt=0)
    heartbeat_miss_threshold: int = Field(3, gt=0)
    shutdown_grace_ms: int = Field(10000, ge=0)


class MT5Config(_StrictModel):
    terminal_path: str = "C:/Program Files/MetaTrader 5/terminal64.exe"
    login: int = 0
    # Reaches the model ONLY via COCOON_MT5__PASSWORD (env / .env) — the
    # loader's secret scan rejects it in any YAML file (exit 11). SecretStr
    # keeps it masked in `config show --resolved` and log records.
    password: SecretStr = SecretStr("")
    server: str = ""
    zmq_req_port: int = Field(5555, gt=0, lt=65536)
    zmq_pub_port: int = Field(5556, gt=0, lt=65536)


class SymbolConfig(_StrictModel):
    name: str
    timeframes: list[str] = Field(default_factory=lambda: ["M5"])


class FeatureEngineeringConfig(_StrictModel):
    fractal_n: int = Field(5, gt=0)
    eq_tol_pips: float = Field(2.0, ge=0)
    sweep_confirm_bars: int = Field(3, gt=0)
    lookback_bars: int = Field(500, gt=0)


class ModelConfig(_StrictModel):
    active_registry_uri: str = "mlflow.db"
    ensemble: list[str] = Field(
        default_factory=lambda: ["lightgbm", "xgboost", "tabnet"]
    )
    ensemble_weights: list[float] = Field(default_factory=lambda: [0.4, 0.4, 0.2])
    inference_batch_max_ms: int = Field(50, gt=0)

    @model_validator(mode="after")
    def _weights_match_members(self) -> "ModelConfig":
        if len(self.ensemble_weights) != len(self.ensemble):
            raise ValueError(
                f"ensemble_weights has {len(self.ensemble_weights)} entries "
                f"for {len(self.ensemble)} ensemble members"
            )
        if self.ensemble_weights and sum(self.ensemble_weights) <= 0:
            raise ValueError("ensemble_weights must sum to a positive value")
        return self


class WalkForwardConfig(_StrictModel):
    train_window_days: int = Field(180, gt=0)
    test_window_days: int = Field(30, gt=0)
    step_days: int = Field(30, gt=0)
    purge_bars: int = Field(50, ge=0)
    embargo_bars: int = Field(20, ge=0)


class HPOConfig(_StrictModel):
    n_trials: int = Field(200, gt=0)
    pruner: str = "median"
    timeout_sec: int = Field(14400, gt=0)


class TrainingConfig(_StrictModel):
    walk_forward: WalkForwardConfig = Field(default_factory=WalkForwardConfig)
    hpo: HPOConfig = Field(default_factory=HPOConfig)


class RiskConfig(_StrictModel):
    max_daily_loss_pct: float = Field(2.0, gt=0)
    max_position_risk_pct: float = Field(0.5, gt=0)
    max_open_positions: int = Field(5, gt=0)
    max_correlated_exposure_pct: float = Field(3.0, gt=0)
    min_rr_ratio: float = Field(1.5, gt=0)
    min_confidence: float = Field(0.55, ge=0.5, le=1.0)
    regime_volatility_cap: float = Field(2.0, gt=0)
    staleness_threshold_ms: int = Field(5000, gt=0)


class OrderConfig(_StrictModel):
    default_slippage_pips: float = Field(2, ge=0)
    retry_max_attempts: int = Field(3, gt=0)
    retry_backoff_ms: list[int] = Field(default_factory=lambda: [200, 500, 1000])
    idempotency_ttl_sec: int = Field(300, gt=0)


class LoggingConfig(_StrictModel):
    format: str = Field("json", pattern="^(json|console)$")
    rotate_max_mb: int = Field(100, gt=0)
    rotate_backups: int = Field(10, ge=0)
    app_log_path: str = "./logs/app.log"
    audit_log_path: str = "./logs/audit.jsonl"


class ConfigModel(_StrictModel):
    profile: str = "default"
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    mt5: MT5Config = Field(default_factory=MT5Config)
    symbols: list[SymbolConfig] = Field(
        default_factory=lambda: [SymbolConfig(name="EURUSD")]
    )
    feature_engineering: FeatureEngineeringConfig = Field(
        default_factory=FeatureEngineeringConfig
    )
    model: ModelConfig = Field(default_factory=ModelConfig)
    training: TrainingConfig = Field(default_factory=TrainingConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    order: OrderConfig = Field(default_factory=OrderConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
