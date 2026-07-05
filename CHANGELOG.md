# Changelog

All notable changes to Cocoon are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/); versioning follows [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Public launch scaffolding: README rewrite, `LICENSE` (MIT), `CONTRIBUTING`, `SECURITY`,
  `CODE_OF_CONDUCT`, GitHub issue/PR templates, and CI (compile + import + CLI smoke).

## [0.1.0] — Reference architecture

Initial reference implementation of the full pipeline.

### Added
- **Data (L1):** OHLCV ingest to parquet cache + ring buffer; 25 point-in-time-safe
  features (6 SMC: BOS, CHoCH, FVG, liquidity sweep, order block, premium/discount; plus
  moving averages, oscillators, session/day flags); forward-return labeling;
  content-hashed, versioned datasets.
- **ML (L2):** LightGBM, XGBoost, TabNet, and weighted ensemble models; walk-forward
  training with Optuna HPO; artifact-hash registry over MLflow; promote to staging/production; inference engine.
- **Trading (L3):** signal → risk → portfolio → order pipeline; event-driven backtester
  that reuses the exact live code path behind a simulated broker.
- **Bridge (L4):** ZMQ + msgpack protocol, heartbeat, broker adapter; reference MQL5 EA skeleton.
- **CLI (L5):** `cocoon` entry point with `--output json` and meaningful exit codes;
  interactive `menu`; dashboard.
- **Core (L0):** config with guarded secrets, structured logging, error taxonomy, state
  machine, interfaces; runtime layer-import tripwire.

### Known limitations
- No test suite; no validation against a real MT5 terminal or real capital; no demonstrated
  predictive edge. See the README "Status" section.
