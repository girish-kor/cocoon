# Cocoon Terminal Reference

Every `cocoon` CLI command with its actual output, captured on 2026-07-26
(Windows 11, Python 3.12, no MetaTrader 5 terminal attached). All results
render as tables; add the global `--output json` flag for machine-readable
output and `--dry-run` to preview mutating commands.

Typical workflow: `init` -> `data import`/`data fetch` -> `dataset build`
-> `train run` -> `model promote` -> `backtest run` -> `trade start --mode paper`.

> Paper-trade PnL below is in-sample (the replayed cache overlaps the
> training data) - it demonstrates the pipeline, not real edge.


## Global flags

### Help

```console
$ cocoon --help
                                                                               
 Usage: cocoon [OPTIONS] COMMAND [ARGS]...                                     
                                                                               
 Cocoon — Forex Trading ML Model V1 CLI                                        
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --profile            TEXT  Active config profile [default: default]         │
│ --config-file        TEXT  Explicit config file path [default: None]        │
│ --log-level          TEXT  DEBUG|INFO|WARN|ERROR [default: None]            │
│ --dry-run                  Validate and print without executing             │
│ --yes                      Skip confirmation prompts                        │
│ --output             TEXT  table|json [default: table]                      │
│ --help                     Show this message and exit.                      │
└─────────────────────────────────────────────────────────────────────────────┘
┌─ Commands ──────────────────────────────────────────────────────────────────┐
│ backtest    Backtesting                                                     │
│ config      Configuration management                                        │
│ data        Market data ingestion & cache                                   │
│ dataset     Dataset construction                                            │
│ features    Feature engineering                                             │
│ init        First-run: scaffold config/, data/, logs/.                      │
│ menu        Interactive menu                                                │
│ model       Model registry                                                  │
│ plugin      Plugin management                                               │
│ positions   Position management                                             │
│ report      Reporting & export                                              │
│ trade       Live/paper trading                                              │
│ train       Model training                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### JSON output mode (any command)

> Every table-producing command honours `--output json` for scripting.

```console
$ cocoon --output json data cache stats
{
  "files": 3,
  "total_bytes": 148847,
  "root": "data\\raw"
}
```

### Dry-run mode (any mutating command)

```console
$ cocoon --dry-run trade start --mode paper
    trade start    
┌─────────┬───────┐
│ dry_run │ True  │
│ action  │ start │
│ mode    │ paper │
└─────────┴───────┘
```


## `cocoon init`

### Scaffold config/, data/, logs/

> Idempotent - shows 0 created when already initialised.

```console
$ cocoon init
    cocoon     
  initialised  
┌─────────┬───┐
│ created │ 0 │
│ paths   │   │
└─────────┴───┘
```


## `cocoon config`

### Show resolved config

```console
$ cocoon config show
                                resolved config                                
┌─────────────────────┬───────────────────────────────────────────────────────┐
│ profile             │ default                                               │
│ runtime             │ mode = paper                                          │
│                     │ log_level = INFO                                      │
│                     │ data_dir = ./data                                     │
│                     │ mt5_connect_timeout_ms = 5000                         │
│                     │ heartbeat_interval_ms = 1000                          │
│                     │ heartbeat_miss_threshold = 3                          │
│                     │ shutdown_grace_ms = 10,000                            │
│ mt5                 │ terminal_path = C:/Program Files/MetaTrader           │
│                     │ 5/terminal64.exe                                      │
│                     │ login = 110,125,169                                   │
│                     │ password = **********                                 │
│                     │ server = MetaQuotes-Demo                              │
│                     │ zmq_req_port = 5555                                   │
│                     │ zmq_pub_port = 5556                                   │
│ symbols             │ [{"name": "EURUSD", "timeframes": ["M1", "M5", "M15", │
│                     │ "H1"]}]                                               │
│ feature_engineering │ fractal_n = 5                                         │
│                     │ eq_tol_pips = 2                                       │
│                     │ sweep_confirm_bars = 3                                │
│                     │ lookback_bars = 500                                   │
│ model               │ active_registry_uri = mlflow.db                       │
│                     │ ensemble = lightgbm, xgboost, tabnet                  │
│                     │ ensemble_weights = 0.4, 0.4, 0.2                      │
│                     │ inference_batch_max_ms = 50                           │
│ training            │ walk_forward.train_window_days = 5                    │
│                     │ walk_forward.test_window_days = 1                     │
│                     │ walk_forward.step_days = 1                            │
│                     │ walk_forward.purge_bars = 50                          │
│                     │ walk_forward.embargo_bars = 20                        │
│                     │ hpo.n_trials = 200                                    │
│                     │ hpo.pruner = median                                   │
│                     │ hpo.timeout_sec = 14,400                              │
│ risk                │ max_daily_loss_pct = 2                                │
│                     │ max_position_risk_pct = 0.5                           │
│                     │ max_open_positions = 5                                │
│                     │ max_correlated_exposure_pct = 3                       │
│                     │ min_rr_ratio = 1.5                                    │
│                     │ min_confidence = 0.55                                 │
│                     │ regime_volatility_cap = 2                             │
│                     │ staleness_threshold_ms = 5000                         │
│ order               │ default_slippage_pips = 2                             │
│                     │ retry_max_attempts = 3                                │
│                     │ retry_backoff_ms = 200, 500, 1000                     │
│                     │ idempotency_ttl_sec = 300                             │
│ logging             │ format = json                                         │
│                     │ rotate_max_mb = 100                                   │
│                     │ rotate_backups = 10                                   │
│                     │ app_log_path = ./logs/app.log                         │
│                     │ audit_log_path = ./logs/audit.jsonl                   │
└─────────────────────┴───────────────────────────────────────────────────────┘
```

### Validate config

```console
$ cocoon config validate
   config validate   
┌─────────┬─────────┐
│ profile │ default │
│ valid   │ True    │
└─────────┴─────────┘
```

### Set a value in the active profile

```console
$ cocoon config set risk.min_confidence 0.55
           config set            
┌─────────┬─────────────────────┐
│ profile │ default             │
│ key     │ risk.min_confidence │
│ value   │ 0.55                │
└─────────┴─────────────────────┘
```

### Create a profile

```console
$ cocoon config profile create demo
            profile create             
┌─────────┬───────────────────────────┐
│ profile │ demo                      │
│ status  │ created                   │
│ path    │ config\profiles\demo.yaml │
└─────────┴───────────────────────────┘
```

### List profiles

```console
$ cocoon config profile list
          profiles          
┌──────────┬───────────────┐
│ profiles │ default, demo │
└──────────┴───────────────┘
```

### Delete a profile

```console
$ cocoon config profile delete demo
   profile delete    
┌─────────┬─────────┐
│ profile │ demo    │
│ status  │ deleted │
└─────────┴─────────┘
```


## `cocoon data`

### Fetch bars from MetaTrader 5

> Requires the MetaTrader5 package and a running terminal; the error below is the real result on a machine without MT5. Use `cocoon data import` to seed data instead.

```console
$ cocoon data fetch --symbol EURUSD --tf M5 --from 2024-01-01 --to 2024-01-02
{"symbol": "EURUSD", "timeframe": "M5", "bars": 3002, "event": "cache_stored", "level": "info", "logger": "cocoon.data.market_data.manager", "timestamp": "2026-07-26T00:51:10.398003Z"}
                fetched                
┌────────┬────────────────────────────┐
│ symbol │ EURUSD                     │
│ tf     │ M5                         │
│ bars   │ 1                          │
│ path   │ data\raw\EURUSD\M5.parquet │
└────────┴────────────────────────────┘
```

### Fetch (dry-run)

```console
$ cocoon --dry-run data fetch --symbol EURUSD --tf M5 --from 2024-01-01 --to 2024-06-01
       data fetch       
┌─────────┬────────────┐
│ dry_run │ True       │
│ action  │ fetch      │
│ symbol  │ EURUSD     │
│ tf      │ M5         │
│ from    │ 2024-01-01 │
│ to      │ 2024-06-01 │
└─────────┴────────────┘
```

### Coverage status

```console
$ cocoon data status
                                 data coverage                                 
┌────────┬─────┬──────┬───────────────────────────┬───────────────────────────┐
│ symbol │ tf  │ bars │ first                     │ last                      │
├────────┼─────┼──────┼───────────────────────────┼───────────────────────────┤
│ EURUSD │ M5  │ 3002 │ 2024-01-01T00:00:00+00:00 │ 2025-03-21T07:35:00+00:00 │
│ EURUSD │ M15 │ 3000 │ 2024-01-01T00:00:00+00:00 │ 2024-01-11T09:55:00+00:00 │
│ GBPUSD │ H1  │ 3000 │ 2024-01-01T00:00:00+00:00 │ 2024-01-11T09:55:00+00:00 │
└────────┴─────┴──────┴───────────────────────────┴───────────────────────────┘
```

### Cache stats

```console
$ cocoon data cache stats
       cache stats        
┌─────────────┬──────────┐
│ files       │ 3        │
│ total_bytes │ 148,847  │
│ root        │ data\raw │
└─────────────┴──────────┘
```

### Cache clear (scoped to a symbol)

> Omit --symbol to clear everything.

```console
$ cocoon data cache clear --symbol NONEXISTENT
          cache clear          
┌───────────────┬─────────────┐
│ symbol        │ NONEXISTENT │
│ files_removed │ 0           │
└───────────────┴─────────────┘
```


## `cocoon dataset`

### Build a labelled dataset

> Deterministic - same inputs produce the same ds_* id.

```console
$ cocoon dataset build --symbols EURUSD --tf M5 --label-horizon 12 --deadband-bps 2
{"dataset_id": "ds_782987baf2387d02", "rows": 2990, "symbols": ["EURUSD"], "event": "dataset_built", "level": "info", "logger": "cocoon.data.dataset.builder", "timestamp": "2026-07-26T00:51:21.198798Z"}
                      dataset built                       
┌────────────┬───────────────────────────────────────────┐
│ dataset_id │ ds_782987baf2387d02                       │
│ rows       │ 2990                                      │
│ features   │ 25                                        │
│ path       │ data\datasets\ds_782987baf2387d02.parquet │
└────────────┴───────────────────────────────────────────┘
```

### List datasets

```console
$ cocoon dataset list
                       datasets                        
┌─────────────────────┬─────────┬────┬──────┬─────────┐
│ dataset_id          │ symbols │ tf │ rows │ horizon │
├─────────────────────┼─────────┼────┼──────┼─────────┤
│ ds_26b1c5852ec04f93 │ EURUSD  │ M5 │ 2978 │      24 │
│ ds_6338e24304ee1b1b │ EURUSD  │ M5 │ 2996 │       6 │
│ ds_782987baf2387d02 │ EURUSD  │ M5 │ 2990 │      12 │
│ ds_8e8832903f6561ae │ EURUSD  │ M5 │ 2997 │       5 │
│ ds_cc50168a4067dc01 │ EURUSD  │ M5 │ 2995 │       5 │
└─────────────────────┴─────────┴────┴──────┴─────────┘
```

### Describe a dataset

```console
$ cocoon dataset describe ds_782987baf2387d02
                          dataset ds_782987baf2387d02                          
┌───────────────┬─────────────────────────────────────────────────────────────┐
│ dataset_id    │ ds_782987baf2387d02                                         │
│ symbols       │ EURUSD                                                      │
│ timeframe     │ M5                                                          │
│ label_horizon │ 12                                                          │
│ deadband_bps  │ 2                                                           │
│ n_rows        │ 2990                                                        │
│ feature_names │ bos, choch, order_block, fvg, liquidity_sweep,              │
│               │ premium_discount_zone, ema_dev_20, ema_dev_50, ema_dev_100, │
│               │ ema_dev_200, rsi_14, atr_14_rel, bb_pct_b_20,               │
│               │ macd_hist_rel, session_sydney, session_tokyo,               │
│               │ session_london, session_newyork, dow_mon, dow_tue, dow_wed, │
│               │ dow_thu, dow_fri, dow_sat, dow_sun                          │
│ path          │ data\datasets\ds_782987baf2387d02.parquet                   │
└───────────────┴─────────────────────────────────────────────────────────────┘
```


## `cocoon features`

### List the registered feature catalogue

```console
$ cocoon features list
           registered FeatureFn catalogue            
┌────┬───────────────────────┬──────────────────────┐
│  # │ name                  │ category             │
├────┼───────────────────────┼──────────────────────┤
│  1 │ bos                   │ smart money concepts │
│  2 │ choch                 │ smart money concepts │
│  3 │ order_block           │ smart money concepts │
│  4 │ fvg                   │ smart money concepts │
│  5 │ liquidity_sweep       │ smart money concepts │
│  6 │ premium_discount_zone │ smart money concepts │
│  7 │ ema_dev_20            │ trend                │
│  8 │ ema_dev_50            │ trend                │
│  9 │ ema_dev_100           │ trend                │
│ 10 │ ema_dev_200           │ trend                │
│ 11 │ rsi_14                │ oscillator           │
│ 12 │ atr_14_rel            │ oscillator           │
│ 13 │ bb_pct_b_20           │ oscillator           │
│ 14 │ macd_hist_rel         │ oscillator           │
│ 15 │ session_sydney        │ session flag         │
│ 16 │ session_tokyo         │ session flag         │
│ 17 │ session_london        │ session flag         │
│ 18 │ session_newyork       │ session flag         │
│ 19 │ dow_mon               │ day-of-week flag     │
│ 20 │ dow_tue               │ day-of-week flag     │
│ 21 │ dow_wed               │ day-of-week flag     │
│ 22 │ dow_thu               │ day-of-week flag     │
│ 23 │ dow_fri               │ day-of-week flag     │
│ 24 │ dow_sat               │ day-of-week flag     │
│ 25 │ dow_sun               │ day-of-week flag     │
└────┴───────────────────────┴──────────────────────┘
```

### Build features for a cached symbol

```console
$ cocoon features build --symbol EURUSD --tf M5
                features built                
┌──────────┬─────────────────────────────────┐
│ symbol   │ EURUSD                          │
│ tf       │ M5                              │
│ rows     │ 3002                            │
│ features │ 25                              │
│ path     │ data\features\EURUSD\M5.parquet │
└──────────┴─────────────────────────────────┘
```


## `cocoon train`

### Train a model

> Deterministic - retraining re-registers the same run_id.

```console
$ cocoon train run --dataset ds_782987baf2387d02 --model lightgbm
{"run_id": "lightgbm_cda10e48681a", "hash": "cda10e48681a097b3f500ddfe4a1d38ec54cb3a68fb3edc7634681fbafeb54d2", "event": "model_registered", "level": "info", "logger": "cocoon.ml.registry.mlflow_client", "timestamp": "2026-07-26T00:51:53.712778Z"}
{"run_id": "lightgbm_cda10e48681a", "auc": 0.9917595715014995, "event": "training_complete", "level": "info", "logger": "cocoon.ml.training.orchestrator", "timestamp": "2026-07-26T00:51:53.714781Z"}
                               training complete                               
┌───────────────┬─────────────────────────────────────────────────────────────┐
│ run_id        │ lightgbm_cda10e48681a                                       │
│ model         │ lightgbm                                                    │
│ metrics       │ walk_forward_auc_mean = 0.99176                             │
│               │ walk_forward_auc_std = 0.00520865                           │
│               │ n_folds = 4                                                 │
│               │ n_samples = 2,752                                           │
│ artifact_hash │ cda10e48681a097b3f500ddfe4a1d38ec54cb3a68fb3edc7634681fbaf… │
└───────────────┴─────────────────────────────────────────────────────────────┘
```

### Walk-forward training

```console
$ cocoon train walk-forward --dataset ds_782987baf2387d02 --model lightgbm
{"run_id": "lightgbm_cda10e48681a", "hash": "cda10e48681a097b3f500ddfe4a1d38ec54cb3a68fb3edc7634681fbafeb54d2", "event": "model_registered", "level": "info", "logger": "cocoon.ml.registry.mlflow_client", "timestamp": "2026-07-26T00:52:24.614012Z"}
{"run_id": "lightgbm_cda10e48681a", "auc": 0.9917595715014995, "event": "training_complete", "level": "info", "logger": "cocoon.ml.training.orchestrator", "timestamp": "2026-07-26T00:52:24.616011Z"}
                             walk-forward complete                             
┌─────────────┬───────────────────────────────────────────────────────────────┐
│ run_id      │ lightgbm_cda10e48681a                                         │
│ fold_scores │ 0.9940753690753691, 0.9943267961070084, 0.9958236208236207,   │
│             │ 0.9828125                                                     │
│ metrics     │ walk_forward_auc_mean = 0.99176                               │
│             │ walk_forward_auc_std = 0.00520865                             │
│             │ n_folds = 4                                                   │
│             │ n_samples = 2,752                                             │
└─────────────┴───────────────────────────────────────────────────────────────┘
```

### Run status

```console
$ cocoon train status lightgbm_cda10e48681a
                    run status                    
┌────────────┬───────────────────────────────────┐
│ run_id     │ lightgbm_cda10e48681a             │
│ model      │ lightgbm                          │
│ dataset_id │ ds_782987baf2387d02               │
│ stage      │ none                              │
│ metrics    │ walk_forward_auc_mean = 0.99176   │
│            │ walk_forward_auc_std = 0.00520865 │
│            │ n_folds = 4                       │
│            │ n_samples = 2,752                 │
└────────────┴───────────────────────────────────┘
```


## `cocoon model`

### List registry

```console
$ cocoon model list
                                model registry                                 
┌───────────────────┬──────────┬────────────┬──────────────────┬──────────────┐
│ run_id            │ model    │ stage      │ dataset_id       │ hash         │
├───────────────────┼──────────┼────────────┼──────────────────┼──────────────┤
│ xgboost_994b45ad… │ xgboost  │ production │ ds_782987baf238… │ 994b45ad8576 │
│ lightgbm_d652fbf… │ lightgbm │ staging    │ ds_8e8832903f65… │ d652fbfd8c79 │
│ lightgbm_1bc4c9d… │ lightgbm │ none       │ ds_26b1c5852ec0… │ 1bc4c9d78c02 │
│ lightgbm_36e87f7… │ lightgbm │ none       │ ds_6338e24304ee… │ 36e87f7995cc │
│ lightgbm_532c402… │ lightgbm │ none       │ ds_cc50168a4067… │ 532c40238df8 │
│ lightgbm_cda10e4… │ lightgbm │ none       │ ds_782987baf238… │ cda10e48681a │
│ xgboost_08c8bf22… │ xgboost  │ none       │ ds_26b1c5852ec0… │ 08c8bf22c3dd │
└───────────────────┴──────────┴────────────┴──────────────────┴──────────────┘
```

### Inspect a run

```console
$ cocoon model inspect xgboost_994b45ad8576
                          model xgboost_994b45ad8576                           
┌───────────────┬─────────────────────────────────────────────────────────────┐
│ run_id        │ xgboost_994b45ad8576                                        │
│ model_name    │ xgboost                                                     │
│ dataset_id    │ ds_782987baf2387d02                                         │
│ artifact_path │ data\models\xgboost_994b45ad8576\artifact.pkl               │
│ artifact_hash │ 994b45ad8576800cbd6c903b6bc9853ca4e72179b86358c35bb34854c0… │
│ stage         │ production                                                  │
│ params        │                                                             │
│ metrics       │ n_folds = 4                                                 │
│               │ n_samples = 2,752                                           │
│               │ walk_forward_auc_mean = 0.990456                            │
│               │ walk_forward_auc_std = 0.00495972                           │
└───────────────┴─────────────────────────────────────────────────────────────┘
```

### Promote to a stage

> Promoting to production demotes any previous production model of the same name.

```console
$ cocoon model promote xgboost_994b45ad8576 --stage production
          model promote          
┌────────┬──────────────────────┐
│ run_id │ xgboost_994b45ad8576 │
│ stage  │ production           │
└────────┴──────────────────────┘
```

### Delete a run

```console
$ cocoon model delete no_such_run
      model delete       
┌─────────┬─────────────┐
│ run_id  │ no_such_run │
│ deleted │ False       │
└─────────┴─────────────┘
```


## `cocoon backtest`

### Run a backtest

```console
$ cocoon backtest run --model-version xgboost_994b45ad8576 --symbols EURUSD --tf M5
{"symbol": "EURUSD", "direction": "SELL", "confidence": 0.9984366907738149, "event": "signal_generated", "level": "info", "logger": "cocoon.trading.signal.engine", "timestamp": "2026-07-26T00:52:52.702601Z"}
{"symbol": "EURUSD", "event": "risk_approved", "level": "info", "logger": "cocoon.trading.risk.engine", "timestamp": "2026-07-26T00:52:52.704604Z"}
{"symbol": "EURUSD", "direction": "SELL", "confidence": 0.9995446446118876, "event": "signal_generated", "level": "info", "logger": "cocoon.trading.signal.engine", "timestamp": "2026-07-26T00:52:52.707604Z"}
{"symbol": "EURUSD", "trades": 907, "total_pnl": 1103535.4366473083, "event": "backtest_complete", "level": "info", "logger": "cocoon.trading.backtest.event_engine", "timestamp": "2026-07-26T00:52:55.348323Z"}
... (5,485 more signal_generated / risk_approved / risk_rejected log lines omitted) ...
          backtest complete           
┌──────────────┬─────────────────────┐
│ backtest_id  │ bt_f134011ec58bc1be │
│ total_trades │ 907                 │
│ total_pnl    │ 1.10354e+06         │
└──────────────┴─────────────────────┘
```
### Report a backtest

> Add --export csv|json for full-precision export.

```console
$ cocoon backtest report bt_f134011ec58bc1be
      backtest bt_f134011ec58bc1be      
┌───────────────┬──────────────────────┐
│ model_version │ xgboost_994b45ad8576 │
│ symbols       │ EURUSD               │
│ timeframe     │ M5                   │
│ total_trades  │ 907                  │
│ total_pnl     │ 1.10354e+06          │
│ backtest_id   │ bt_f134011ec58bc1be  │
└───────────────┴──────────────────────┘
                              per-symbol metrics                              
┌────────┬────────┬───────┬──────┬─────────────┬──────┬────────┬──────┬──────┐
│ symbol │ trades │ win % │   PF │         pnl │ dd % │ sharpe │  sig │  rej │
├────────┼────────┼───────┼──────┼─────────────┼──────┼────────┼──────┼──────┤
│ EURUSD │    907 │  91.7 │ 9.93 │ 1.10354e+06 │ 1.86 │  18.62 │ 2744 │ 1837 │
└────────┴────────┴───────┴──────┴─────────────┴──────┴────────┴──────┴──────┘
```


## `cocoon trade`

### Start paper trading (replays cached bars, no MT5 needed)

> On a real terminal the dashboard is live (progress bar, equity sparkline, open positions); captured here is the final frame. --speed 20 replays 20 bars/second; live mode (--mode live) needs the MT5 EA bridge.

```console
$ cocoon trade start --mode paper --speed 0 --dashboard
┌─────────────────────────────── PAPER TRADING ───────────────────────────────┐
│ Cocoon PAPER  EURUSD M5   state: TERMINATED                                 │
│ -------------------------------------------- 3,002/3,002 bars  100.0%       │
│ ┌──────────────┬─────────────┬────────┬───────┬──────┬─────────┬──────────┐ │
│ │       EQUITY │         P&L │ TRADES │ WIN % │ OPEN │ SIGNALS │ REJECTED │ │
│ ├──────────────┼─────────────┼────────┼───────┼──────┼─────────┼──────────┤ │
│ │ 1,565,900.71 │ +1,555,900… │    964 │   92% │    1 │    2935 │     1970 │ │
│ └──────────────┴─────────────┴────────┴───────┴──────┴─────────┴──────────┘ │
│ equity  1,565,901 max · 9,931 min                                           │
│ ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▂▂▂▂▂▂▂▂▂▃▃▃▃▃▃▄▄▄▅▅▅▆▆▇▇█            │
│ ┌──────────────┬─────────┬───────────┬───────────────┬────────────────────┐ │
│ │       SYMBOL │     DIR │      LOTS │         ENTRY │         UNREAL P&L │ │
│ ├──────────────┼─────────┼───────────┼───────────────┼────────────────────┤ │
│ │       EURUSD │     BUY │      6.52 │       1.08237 │              +0.00 │ │
│ └──────────────┴─────────┴───────────┴───────────────┴────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘      paper session summary      
┌─────────────────┬─────────────┐
│ symbol          │ EURUSD      │
│ tf              │ M5          │
│ bars_replayed   │ 3002        │
│ trades          │ 965         │
│ starting_equity │ 10,000      │
│ final_equity    │ 1.56577e+06 │
│ total_pnl       │ 1.55577e+06 │
└─────────────────┴─────────────┘
```

### Status (one-shot)

> --watch gives a live-refreshing dashboard.

```console
$ cocoon trade status
┌─────────────────────────────────── LIVE ────────────────────────────────────┐
│ Cocoon — PAPER  profile:default  state:TERMINATED                           │
│ Open Positions: 0/5   Unrealized P&L: +0.00   Daily Loss Budget: 2.0%       │
│ ┌────────────┬───────┬─────────┬──────────┬──────┬──────┬───────┬─────────┐ │
│ │ SYMBOL     │ DIR   │ LOTS    │ ENTRY    │ SL   │ TP   │ P&L   │ ORIGIN  │ │
│ ├────────────┼───────┼─────────┼──────────┼──────┼──────┼───────┼─────────┤ │
│ └────────────┴───────┴─────────┴──────────┴──────┴──────┴───────┴─────────┘ │
│ Bridge: —   Model: ['lightgbm', 'xgboost', 'tabnet']                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Halt (SAFE_HALT)

```console
$ cocoon trade halt --yes
   trade halt    
┌────────┬──────┐
│ signal │ halt │
│ status │ sent │
└────────┴──────┘
```

### Resume

```console
$ cocoon trade resume
   trade resume    
┌────────┬────────┐
│ signal │ resume │
│ status │ sent   │
└────────┴────────┘
```

### Stop

```console
$ cocoon trade stop
   trade stop    
┌────────┬──────┐
│ signal │ stop │
│ status │ sent │
└────────┴──────┘
```


## `cocoon positions`

### List open positions

```console
$ cocoon positions list
open positions
```

### Close a ticket (dry-run)

```console
$ cocoon --dry-run positions close 12345
  positions close   
┌─────────┬────────┐
│ dry_run │ True   │
│ action  │ close  │
│ ticket  │ 12,345 │
│ partial │ None   │
└─────────┴────────┘
```

### Close a ticket (real - needs the MT5 bridge)

> The timeout below is the real result without a running EA.

```console
$ cocoon positions close 12345
{"req": 5555, "pub": 5556, "event": "zmq_connected", "level": "info", "logger": "cocoon.bridge.zmq_endpoint", "timestamp": "2026-07-26T00:57:11.287240Z"}
{"error_type": "MT5ConnectTimeoutError", "message": "MT5 EA did not ACK HELLO within timeout", "exit_code": 20, "context": {"timeout_ms": 5000, "error": "Resource temporarily unavailable"}, "event": "cli_error", "level": "error", "logger": "cocoon.cli", "timestamp": "2026-07-26T00:57:16.293518Z"}
MT5ConnectTimeoutError: MT5 EA did not ACK HELLO within timeout
context: {"timeout_ms": 5000, "error": "Resource temporarily unavailable"}
```

_Exit code: 20_


## `cocoon report`

### Daily order report

```console
$ cocoon report daily --date 2026-07-26
                             orders for 2026-07-26                             
┌───────┬───────┬───────┬───────┬───────┬───────┬──────┬───────┬──────┬───────┐
│ idem… │ symb… │ dire… │ volu… │ stat… │ brok… │ fil… │ fill… │ rej… │ atte… │
├───────┼───────┼───────┼───────┼───────┼───────┼──────┼───────┼──────┼───────┤
│ d2eb… │ EURU… │ BUY   │ 6.81… │ FILL… │   466 │ 6.8… │ 1.10… │ None │     0 │
│ 4a51… │ EURU… │ BUY   │ 6.82… │ FILL… │   467 │ 6.8… │ 1.10… │ None │     0 │
│ 6db5… │ EURU… │ BUY   │ 7.09… │ FILL… │   468 │ 7.0… │ 1.10… │ None │     0 │
│ db87… │ EURU… │ BUY   │ 7.02… │ FILL… │   469 │ 7.0… │ 1.10… │ None │     0 │
│ 5182… │ EURU… │ BUY   │ 6.87… │ FILL… │   470 │ 6.8… │ 1.10… │ None │     0 │
│ 731a… │ EURU… │ BUY   │ 6.88… │ FILL… │   471 │ 6.8… │ 1.10… │ None │     0 │
│ ab6b… │ EURU… │ SELL  │ 6.91… │ FILL… │   472 │ 6.9… │ 1.10… │ None │     0 │
│ 33d1… │ EURU… │ SELL  │ 6.94… │ FILL… │   473 │ 6.9… │ 1.10… │ None │     0 │
│ b4ea… │ EURU… │ SELL  │ 7.00… │ FILL… │   474 │ 7.0… │ 1.10… │ None │     0 │
│ fae0… │ EURU… │ SELL  │ 7.30… │ FILL… │   475 │ 7.3… │ 1.10… │ None │     0 │
│ 4e5e… │ EURU… │ SELL  │ 7.79… │ FILL… │   476 │ 7.7… │ 1.10… │ None │     0 │
│ a967… │ EURU… │ SELL  │ 7.38… │ FILL… │   477 │ 7.3… │ 1.10… │ None │     0 │
│ 376c… │ EURU… │ SELL  │ 7.13… │ FILL… │   478 │ 7.1… │ 1.10… │ None │     0 │
│ 0626… │ EURU… │ SELL  │ 6.64… │ FILL… │   479 │ 6.6… │ 1.10… │ None │     0 │
│ 049a… │ EURU… │ SELL  │ 6.90… │ FILL… │   480 │ 6.9… │ 1.10… │ None │     0 │
│ 1318… │ EURU… │ SELL  │ 7.63… │ FILL… │   481 │ 7.6… │ 1.10… │ None │     0 │
│ a99c… │ EURU… │ SELL  │ 7.84… │ FILL… │   482 │ 7.8… │ 1.10… │ None │     0 │
│ f3c6… │ EURU… │ SELL  │ 8.16… │ FILL… │   483 │ 8.1… │ 1.10… │ None │     0 │
│ 81fd… │ EURU… │ SELL  │ 8.08… │ FILL… │   484 │ 8.0… │ 1.10… │ None │     0 │
│ fff1… │ EURU… │ SELL  │ 8.08… │ FILL… │   485 │ 8.0… │ 1.10… │ None │     0 │
│ 85ee… │ EURU… │ SELL  │ 8.08… │ FILL… │   486 │ 8.0… │ 1.10… │ None │     0 │
│ 5ed1… │ EURU… │ BUY   │ 7.69… │ FILL… │   487 │ 7.6… │ 1.10… │ None │     0 │
│ 86ed… │ EURU… │ BUY   │ 7.58… │ FILL… │   488 │ 7.5… │ 1.10… │ None │     0 │
│ 0f7d… │ EURU… │ BUY   │ 7.27… │ FILL… │   489 │ 7.2… │ 1.10… │ None │     0 │
│ 9a68… │ EURU… │ BUY   │ 7.27… │ FILL… │   490 │ 7.2… │ 1.10… │ None │     0 │
│ 1b8b… │ EURU… │ BUY   │ 7.32… │ FILL… │   491 │ 7.3… │ 1.10… │ None │     0 │
│ cf37… │ EURU… │ BUY   │ 7.44… │ FILL… │   492 │ 7.4… │ 1.10… │ None │     0 │
│ 7a57… │ EURU… │ BUY   │ 7.54… │ FILL… │   493 │ 7.5… │ 1.10… │ None │     0 │
│ 1101… │ EURU… │ BUY   │ 7.63… │ FILL… │   494 │ 7.6… │ 1.10… │ None │     0 │
│ 6f65… │ EURU… │ BUY   │ 7.70… │ FILL… │   495 │ 7.7… │ 1.10… │ None │     0 │
│ 9ad7… │ EURU… │ BUY   │ 10.8… │ FILL… │   496 │ 10.… │ 1.10… │ None │     0 │
│ 47ea… │ EURU… │ BUY   │ 9.57… │ FILL… │   497 │ 9.5… │ 1.10… │ None │     0 │
│ 04e0… │ EURU… │ BUY   │ 9.13… │ FILL… │   498 │ 9.1… │ 1.10… │ None │     0 │
│ 1913… │ EURU… │ BUY   │ 8.62… │ FILL… │   499 │ 8.6… │ 1.10… │ None │     0 │
│ 2957… │ EURU… │ BUY   │ 8.22… │ FILL… │   500 │ 8.2… │ 1.10… │ None │     0 │
│ d4af… │ EURU… │ BUY   │ 7.88… │ FILL… │   501 │ 7.8… │ 1.10… │ None │     0 │
│ aea7… │ EURU… │ BUY   │ 7.63… │ FILL… │   502 │ 7.6… │ 1.10… │ None │     0 │
│ 7da9… │ EURU… │ BUY   │ 7.27… │ FILL… │   503 │ 7.2… │ 1.10… │ None │     0 │
│ dbf7… │ EURU… │ SELL  │ 7.33… │ FILL… │   504 │ 7.3… │ 1.10… │ None │     0 │
│ f379… │ EURU… │ SELL  │ 7.42… │ FILL… │   505 │ 7.4… │ 1.10… │ None │     0 │
│ d893… │ EURU… │ SELL  │ 7.48… │ FILL… │   506 │ 7.4… │ 1.10… │ None │     0 │
│ e763… │ EURU… │ SELL  │ 7.66… │ FILL… │   507 │ 7.6… │ 1.10… │ None │     0 │
│ 0f97… │ EURU… │ BUY   │ 8.20… │ FILL… │   508 │ 8.2… │ 1.10… │ None │     0 │
│ 088e… │ EURU… │ SELL  │ 8.45… │ FILL… │   509 │ 8.4… │ 1.10… │ None │     0 │
│ 2471… │ EURU… │ SELL  │ 7.78… │ FILL… │   510 │ 7.7… │ 1.10… │ None │     0 │
│ 79fc… │ EURU… │ SELL  │ 7.21… │ FILL… │   511 │ 7.2… │ 1.10… │ None │     0 │
│ 4972… │ EURU… │ SELL  │ 7.36… │ FILL… │   512 │ 7.3… │ 1.10… │ None │     0 │
│ 9e1f… │ EURU… │ BUY   │ 7.90… │ FILL… │   513 │ 7.9… │ 1.10… │ None │     0 │
│ 7c8f… │ EURU… │ SELL  │ 9.06… │ FILL… │   514 │ 9.0… │ 1.10… │ None │     0 │
│ acf5… │ EURU… │ SELL  │ 9.88… │ FILL… │   515 │ 9.8… │ 1.10… │ None │     0 │
│ 8455… │ EURU… │ BUY   │ 9.93… │ FILL… │   516 │ 9.9… │ 1.10… │ None │     0 │
│ 1404… │ EURU… │ BUY   │ 9.48… │ FILL… │   517 │ 9.4… │ 1.10… │ None │     0 │
│ b2e7… │ EURU… │ BUY   │ 9.11… │ FILL… │   518 │ 9.1… │ 1.10… │ None │     0 │
│ 6cf4… │ EURU… │ BUY   │ 9.05… │ FILL… │   519 │ 9.0… │ 1.10… │ None │     0 │
│ b841… │ EURU… │ BUY   │ 9.00… │ FILL… │   520 │ 9.0… │ 1.10… │ None │     0 │
│ 74c9… │ EURU… │ BUY   │ 8.88… │ FILL… │   521 │ 8.8… │ 1.10… │ None │     0 │
│ 9786… │ EURU… │ BUY   │ 9.11… │ FILL… │   522 │ 9.1… │ 1.10… │ None │     0 │
│ a5b5… │ EURU… │ BUY   │ 8.60… │ FILL… │   523 │ 8.6… │ 1.10… │ None │     0 │
│ dd53… │ EURU… │ BUY   │ 8.58… │ FILL… │   524 │ 8.5… │ 1.10… │ None │     0 │
│ 0fdc… │ EURU… │ BUY   │ 8.60… │ FILL… │   525 │ 8.6… │ 1.10… │ None │     0 │
│ aa6e… │ EURU… │ BUY   │ 8.64… │ FILL… │   526 │ 8.6… │ 1.10… │ None │     0 │
│ 86a7… │ EURU… │ BUY   │ 8.72… │ FILL… │   527 │ 8.7… │ 1.10… │ None │     0 │
│ b89a… │ EURU… │ BUY   │ 8.90… │ FILL… │   528 │ 8.9… │ 1.10… │ None │     0 │
│ 6863… │ EURU… │ BUY   │ 9.99… │ FILL… │   529 │ 9.9… │ 1.10… │ None │     0 │
│ 0599… │ EURU… │ BUY   │ 9.56… │ FILL… │   530 │ 9.5… │ 1.10… │ None │     0 │
│ 214d… │ EURU… │ BUY   │ 9.36… │ FILL… │   531 │ 9.3… │ 1.10… │ None │     0 │
│ 3a06… │ EURU… │ BUY   │ 9.43… │ FILL… │   532 │ 9.4… │ 1.10… │ None │     0 │
│ 8b1c… │ EURU… │ SELL  │ 9.67… │ FILL… │   533 │ 9.6… │ 1.10… │ None │     0 │
│ 08ab… │ EURU… │ SELL  │ 9.93… │ FILL… │   534 │ 9.9… │ 1.10… │ None │     0 │
│ 45bb… │ EURU… │ SELL  │ 10.0… │ FILL… │   535 │ 10.… │ 1.10… │ None │     0 │
│ 1b4a… │ EURU… │ SELL  │ 10.2… │ FILL… │   536 │ 10.… │ 1.10… │ None │     0 │
│ 0b6f… │ EURU… │ SELL  │ 10.6… │ FILL… │   537 │ 10.… │ 1.10… │ None │     0 │
│ 8d14… │ EURU… │ SELL  │ 10.5… │ FILL… │   538 │ 10.… │ 1.10… │ None │     0 │
│ a313… │ EURU… │ SELL  │ 10.2… │ FILL… │   539 │ 10.… │ 1.10… │ None │     0 │
│ 0773… │ EURU… │ SELL  │ 9.98… │ FILL… │   540 │ 9.9… │ 1.10… │ None │     0 │
│ 380d… │ EURU… │ SELL  │ 9.41… │ FILL… │   541 │ 9.4… │ 1.10… │ None │     0 │
│ 555b… │ EURU… │ SELL  │ 9.33… │ FILL… │   542 │ 9.3… │ 1.10… │ None │     0 │
│ fac3… │ EURU… │ SELL  │ 9.38… │ FILL… │   543 │ 9.3… │ 1.10… │ None │     0 │
│ 22c4… │ EURU… │ SELL  │ 9.47… │ FILL… │   544 │ 9.4… │ 1.10… │ None │     0 │
│ 3c77… │ EURU… │ SELL  │ 10.2… │ FILL… │   545 │ 10.… │ 1.10… │ None │     0 │
│ 91eb… │ EURU… │ SELL  │ 9.75… │ FILL… │   546 │ 9.7… │ 1.10… │ None │     0 │
│ 41a4… │ EURU… │ BUY   │ 9.78… │ FILL… │   547 │ 9.7… │ 1.10… │ None │     0 │
│ 5473… │ EURU… │ BUY   │ 10.0… │ FILL… │   548 │ 10.… │ 1.10… │ None │     0 │
│ 238f… │ EURU… │ BUY   │ 10.4… │ FILL… │   549 │ 10.… │ 1.10… │ None │     0 │
│ 866d… │ EURU… │ BUY   │ 10.8… │ FILL… │   550 │ 10.… │ 1.10… │ None │     0 │
│ 6353… │ EURU… │ BUY   │ 11.1… │ FILL… │   551 │ 11.… │ 1.10… │ None │     0 │
│ c8a6… │ EURU… │ BUY   │ 11.5… │ FILL… │   552 │ 11.… │ 1.10… │ None │     0 │
│ 197c… │ EURU… │ BUY   │ 10.3… │ FILL… │   553 │ 10.… │ 1.10… │ None │     0 │
│ e479… │ EURU… │ BUY   │ 10.1… │ FILL… │   554 │ 10.… │ 1.10… │ None │     0 │
│ 27f1… │ EURU… │ BUY   │ 10.0… │ FILL… │   555 │ 10.… │ 1.10… │ None │     0 │
│ ae88… │ EURU… │ BUY   │ 9.99… │ FILL… │   556 │ 9.9… │ 1.10… │ None │     0 │
│ b7c3… │ EURU… │ BUY   │ 10.0… │ FILL… │   557 │ 10.… │ 1.10… │ None │     0 │
│ 3a02… │ EURU… │ BUY   │ 10.5… │ FILL… │   558 │ 10.… │ 1.10… │ None │     0 │
│ eb02… │ EURU… │ BUY   │ 10.5… │ FILL… │   559 │ 10.… │ 1.10… │ None │     0 │
│ ef63… │ EURU… │ BUY   │ 10.6… │ FILL… │   560 │ 10.… │ 1.10… │ None │     0 │
│ 287e… │ EURU… │ BUY   │ 13.1… │ FILL… │   561 │ 13.… │ 1.10… │ None │     0 │
│ 58a5… │ EURU… │ BUY   │ 13.6… │ FILL… │   562 │ 13.… │ 1.10… │ None │     0 │
│ 2613… │ EURU… │ BUY   │ 13.6… │ FILL… │   563 │ 13.… │ 1.10… │ None │     0 │
│ 1761… │ EURU… │ BUY   │ 13.1… │ FILL… │   564 │ 13.… │ 1.10… │ None │     0 │
│ 946d… │ EURU… │ BUY   │ 12.6… │ FILL… │   565 │ 12.… │ 1.10… │ None │     0 │
└───────┴───────┴───────┴───────┴───────┴───────┴──────┴───────┴──────┴───────┘
```

### Session report

> Audit payloads carry no session id yet, so this always reports 0 (known gap).

```console
$ cocoon report session cocoon-ea
    session cocoon-ea     
┌────────────┬───────────┐
│ session_id │ cocoon-ea │
│ events     │ 0         │
│ orders     │ 0         │
└────────────┴───────────┘
```

### Export the audit trail

```console
$ cocoon report export --format csv --out ./out/audit.csv
      report export       
┌────────┬───────────────┐
│ events │ 5000          │
│ format │ csv           │
│ path   │ out\audit.csv │
└────────┴───────────────┘
```


## `cocoon plugin`

### List plugins

```console
$ cocoon plugin list
plugins
```
