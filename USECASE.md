# Cocoon — Use Cases & Complete Command Reference

This is a hands-on walkthrough of the whole system, followed by a reference for
every single command. Everything here was run; the outputs are real.

Two rules that apply everywhere:

1. **Global flags go before the subcommand.** `cocoon --output json model list`
   works; `cocoon model list --output json` does not. The global flags are
   `--profile`, `--config-file`, `--log-level`, `--dry-run`, `--yes`,
   `--output`.
2. **Exit codes are meaningful** (from DOCUMENT.md §16): `0` success, `10`
   config invalid, `11` secret in config file, `20` MT5 connect timeout, `21`
   reconciliation conflict, `30` dataset build failure, `31` training failure,
   `32` model promotion failure, `40` risk hard-stop, `41` order retry
   exhausted, `50` bridge protocol mismatch, `60` plugin load failure, `130`
   clean SIGINT shutdown.

---

## Part 1 — End-to-end use case (offline, no MT5 terminal)

This is the full path from an empty directory to a trained model and a
backtest, using a CSV file to seed data (so you don't need MetaTrader 5).

### 1. Scaffold the project

```
cocoon init
```

Creates `config/base.yaml`, `config/profiles/default.yaml`, and the `data/` and
`logs/` trees. Idempotent — running it again only creates what's missing.

### 2. Check and adjust configuration

```
cocoon config validate
cocoon config show --resolved
```

`validate` prints `config for profile 'default' is valid` (exit 0) or fails with
exit 10. `show --resolved` prints the fully merged config (defaults + base.yaml +
profile + env + CLI).

Optionally make a profile and tweak a value:

```
cocoon config profile create scalping --from default
cocoon config set risk.max_daily_loss_pct 1.5 --profile scalping
cocoon config show --profile scalping
```

### 3. Get data into the cache

If you have MetaTrader 5 installed and a terminal running:

```
cocoon data fetch --symbol EURUSD --tf M5 --from 2024-01-01 --to 2024-06-01
```

If you don't (most people, most of the time), import a CSV or Parquet file:

```
cocoon data import --symbol EURUSD --tf M5 --file EURUSD_M5.csv
cocoon data import --symbol GBPUSD --tf M5 --file GBPUSD_M5.csv
```

The importer accepts common column layouts:
- a `ts_unix_ms` column (integer epoch milliseconds), or
- a `timestamp` / `datetime` column (parseable date-time string), or
- MetaTrader export style `<DATE>` + `<TIME>` columns (dotted dates like
  `2024.01.01` are handled),
- plus `open` / `high` / `low` / `close` and an optional volume column
  (`volume`, `tick_volume`, `<TICKVOL>`). Angle brackets and case don't matter.

Confirm what's cached:

```
cocoon data status
cocoon data cache stats
```

`data status` lists each symbol/timeframe with bar count and first/last
timestamps. If a later step says `"bars": 0`, this is the command that tells you
the cache is empty.

### 4. Inspect the feature set

```
cocoon features list
```

Prints the 25 point-in-time-safe features: `bos`, `choch`, `order_block`, `fvg`,
`liquidity_sweep`, `premium_discount_zone`, four EMA deviations, `rsi_14`,
`atr_14_rel`, `bb_pct_b_20`, `macd_hist_rel`, four session flags, seven
day-of-week flags.

Optionally materialise the feature frame to parquet (for your own inspection —
the dataset builder recomputes internally, so this is not a required step):

```
cocoon features build --symbol EURUSD --tf M5
```

### 5. Build a labelled, versioned dataset

```
cocoon dataset build --symbols EURUSD,GBPUSD --tf M5 --label-horizon 5 --deadband-bps 1.0
```

Joins features + forward-return labels, drops rows without a full label window,
content-hashes the result, and writes `data/datasets/<id>.parquet`. It prints a
`dataset_id` like `ds_bd69cd7c78420068`. `--deadband-bps` sets the neutral band
(returns within ±band are labelled 0 and dropped from training). Empty cache →
exit 30.

Grab the id for scripting:

```
DS=$(cocoon --output json dataset build --symbols EURUSD,GBPUSD --tf M5 --label-horizon 5 | jq -r .dataset_id)
cocoon dataset list
cocoon dataset describe "$DS"
```

### 6. Train a model

```
cocoon train run --dataset "$DS" --model lightgbm
```

`--model` is one of `lightgbm | xgboost | tabnet | ensemble`. Add `--hpo` to run
Optuna hyperparameter search (single-model only). Training fits on the full set,
runs purged walk-forward scoring, and registers a content-hashed artifact. It
prints a `run_id` like `lightgbm_0e80d8aeb573`.

Note on walk-forward metrics: the default windows (train 180 days, test 30 days)
need months of data. On a few weeks of bars you'll see `n_folds: 0` and
`walk_forward_auc_mean: 0.0`. The model still trains and registers; you just get
no cross-validated score. Feed more data or shrink `training.walk_forward` in
config.

Explicit walk-forward run, or check a run's stored record:

```
cocoon train walk-forward --dataset "$DS" --model xgboost
cocoon train status lightgbm_0e80d8aeb573
```

### 7. Manage the model registry

```
cocoon model list
cocoon model inspect lightgbm_0e80d8aeb573
cocoon model promote lightgbm_0e80d8aeb573 --stage production
```

`--stage` is `staging` or `production`. Promoting one model to production
demotes any previous production model of the same name to staging. `trade start`
and `backtest run` use whatever you point them at / promote.

### 8. Backtest

```
cocoon backtest run --model-version lightgbm_0e80d8aeb573 --symbols EURUSD,GBPUSD --tf M5
```

Runs the event-driven backtest (same signal/risk/order code as live, with a
simulated broker) over the cached bars. Optional `--from` / `--to` to slice by
date, `--equity` to set starting equity (default 10000). Prints a `backtest_id`.

Read the report, or export it:

```
cocoon backtest report bt_4783407931961192
cocoon backtest report bt_4783407931961192 --export csv
cocoon backtest report bt_4783407931961192 --export json
```

Reminder: backtest P&L on synthetic/random data is noise. The backtest proves
the machinery, not profitability.

### 9. Go live (needs a terminal + EA)

```
cocoon trade start --mode paper
```

Drives the state machine: loads config → connects to the EA over ZMQ →
reconciles positions/orders against the broker → runs the bar→infer→signal→
risk→order loop until you stop it. Requires a promoted model and an EA answering
on the configured ports; without one it exits 20 (`MT5ConnectTimeoutError`).

Control a running session from another shell:

```
cocoon trade status            # one-shot dashboard snapshot
cocoon trade status --watch    # live-refreshing dashboard
cocoon trade halt --yes        # enter SAFE_HALT (no new orders)
cocoon trade resume            # re-reconcile and resume
cocoon trade stop              # drain and shut down
```

Control commands write a flag file under `data/runtime/`; the running loop reads
it each tick. There is no background daemon — `trade start` runs in the
foreground.

### 10. Positions and reporting

```
cocoon positions list
cocoon positions close 123456 --partial 0.05
cocoon report daily --date 2026-07-03
cocoon report export --format json --out ./out/audit.json
```

`positions list` reads the local SQLite positions table. `positions close` sends
a close to the broker (needs a terminal). Reporting reads the SQLite audit
table.

### 11. Plugins

```
cocoon plugin list
cocoon plugin install ./my_indicator.py
cocoon plugin remove my_indicator
```

A local plugin is a `.py` file exposing a `build_features()` function that
returns one or more `FeatureFn` objects. Installing copies it into
`data/plugins/`; a non-conforming plugin fails with exit 60.

### 12. Interactive menu

```
cocoon menu
```

Arrow-key menu that re-invokes the exact same commands above, so nothing behaves
differently than the scripted form.

---

## Part 2 — Complete command reference

Every command, its arguments, its options, and what it does. `<x>` is a required
positional argument; `[--x]` is optional.

### Global options (before the subcommand)

| Flag | Meaning |
|---|---|
| `--profile NAME` | Active config profile (default `default`) |
| `--config-file PATH` | Explicit config file location |
| `--log-level LEVEL` | `DEBUG` / `INFO` / `WARN` / `ERROR` |
| `--dry-run` | Validate and print the intended action without executing |
| `--yes` | Skip confirmation prompts |
| `--output FMT` | `table` (default) or `json` |

### `cocoon init`
Scaffold `config/`, `data/`, `logs/` and write `config/base.yaml` +
`config/profiles/default.yaml`. Safe to re-run.
```
cocoon init
```

### `cocoon config`

- `cocoon config show [--profile NAME] [--resolved]`
  Show a profile's raw overrides, or the fully resolved config with `--resolved`
  (also the default when no profile is given).
  ```
  cocoon config show --resolved
  cocoon config show --profile scalping
  ```

- `cocoon config validate [--profile NAME]`
  Resolve and schema-validate a profile. Exit 0 valid, exit 10 invalid.
  ```
  cocoon config validate
  cocoon config validate --profile scalping
  ```

- `cocoon config set <dot.path> <value> [--profile NAME]`
  Set a nested key in a profile YAML (value is parsed as JSON when possible).
  ```
  cocoon config set risk.max_daily_loss_pct 1.5 --profile scalping
  cocoon config set symbols '[{"name":"EURUSD","timeframes":["M5"]}]' --profile scalping
  ```

- `cocoon config profile create <name> [--from NAME]`
  Create a new profile, optionally copied from an existing one.
  ```
  cocoon config profile create scalping --from default
  ```

- `cocoon config profile list`
  List profile names.
  ```
  cocoon config profile list
  ```

- `cocoon config profile delete <name>`
  Delete a profile file.
  ```
  cocoon config profile delete scalping
  ```

### `cocoon data`

- `cocoon data fetch --symbol SYM --tf TF --from DATE --to DATE`
  Bulk-fetch bars from MetaTrader 5 into the cache. Requires the `MetaTrader5`
  package and a running terminal; otherwise exit 1 with `DataError`.
  ```
  cocoon data fetch --symbol EURUSD --tf M5 --from 2024-01-01 --to 2024-06-01
  ```

- `cocoon data import --symbol SYM --tf TF --file PATH`
  Import bars from a CSV or Parquet file into the cache (offline alternative to
  `fetch`). Accepts `ts_unix_ms` / `timestamp` / `datetime`, or `<DATE>`+`<TIME>`
  columns, plus OHLC and optional volume.
  ```
  cocoon data import --symbol EURUSD --tf M5 --file EURUSD_M5.csv
  cocoon --dry-run data import --symbol EURUSD --tf M5 --file EURUSD_M5.parquet
  ```

- `cocoon data status`
  Coverage report per symbol/timeframe: bar count, first/last timestamp.
  ```
  cocoon data status
  ```

- `cocoon data cache clear [--symbol SYM]`
  Delete cached parquet for one symbol, or all symbols if omitted.
  ```
  cocoon data cache clear --symbol EURUSD
  cocoon data cache clear
  ```

- `cocoon data cache stats`
  Cache file count, total bytes, and root path.
  ```
  cocoon data cache stats
  ```

### `cocoon features`

- `cocoon features build --symbol SYM --tf TF [--from DATE] [--to DATE]`
  Compute the full feature frame for a symbol/timeframe and write it to
  `data/features/<symbol>/<tf>.parquet`. (`--from`/`--to` are accepted for
  interface symmetry; the build uses the cached range.)
  ```
  cocoon features build --symbol EURUSD --tf M5
  ```

- `cocoon features list`
  Print the registered FeatureFn catalogue (25 features).
  ```
  cocoon features list
  ```

### `cocoon dataset`

- `cocoon dataset build --symbols SYM[,SYM...] --tf TF --label-horizon N [--deadband-bps B]`
  Build a versioned, content-hashed dataset. `--tf` defaults to `M5`,
  `--deadband-bps` defaults to `0.0`. Exit 30 on integrity failure (e.g. empty
  cache).
  ```
  cocoon dataset build --symbols EURUSD,GBPUSD --tf M5 --label-horizon 5 --deadband-bps 1.0
  ```

- `cocoon dataset list`
  List built datasets (id, symbols, timeframe, rows, label horizon).
  ```
  cocoon dataset list
  ```

- `cocoon dataset describe <dataset_id>`
  Full metadata for a dataset: features, row count, path, build descriptor.
  ```
  cocoon dataset describe ds_bd69cd7c78420068
  ```

### `cocoon train`

- `cocoon train run --dataset ID --model {lightgbm|xgboost|tabnet|ensemble} [--hpo]`
  Train and register a model. `--hpo` runs Optuna search (single-model only;
  exit 31 if HPO exhausts with no valid trial).
  ```
  cocoon train run --dataset ds_bd69cd7c78420068 --model lightgbm
  cocoon train run --dataset ds_bd69cd7c78420068 --model xgboost --hpo
  cocoon train run --dataset ds_bd69cd7c78420068 --model ensemble
  ```

- `cocoon train walk-forward --dataset ID --model NAME`
  Run the purged walk-forward evaluation and register the result.
  ```
  cocoon train walk-forward --dataset ds_bd69cd7c78420068 --model lightgbm
  ```

- `cocoon train status <run_id>`
  Show a training run's stored record (model, dataset, stage, metrics).
  ```
  cocoon train status lightgbm_0e80d8aeb573
  ```

### `cocoon model`

- `cocoon model list`
  List registry entries (run_id, model, stage, dataset, hash).
  ```
  cocoon model list
  ```

- `cocoon model promote <run_id> --stage {staging|production}`
  Promote a model. Production is exclusive per model name. Exit 32 on failure.
  ```
  cocoon model promote lightgbm_0e80d8aeb573 --stage production
  ```

- `cocoon model inspect <run_id>`
  Full registry entry for one run (path, params, metrics).
  ```
  cocoon model inspect lightgbm_0e80d8aeb573
  ```

- `cocoon model delete <run_id>`
  Remove a run from the registry and delete its artifact files.
  ```
  cocoon model delete lightgbm_0e80d8aeb573
  ```

### `cocoon backtest`

- `cocoon backtest run --model-version ID --symbols SYM[,SYM...] [--tf TF] [--from DATE] [--to DATE] [--equity N]`
  Event-driven backtest over cached bars. `--tf` defaults `M5`, `--equity`
  defaults `10000`. Prints a `backtest_id`.
  ```
  cocoon backtest run --model-version lightgbm_0e80d8aeb573 --symbols EURUSD,GBPUSD --tf M5
  cocoon backtest run --model-version lightgbm_0e80d8aeb573 --symbols EURUSD --from 2024-03-01 --to 2024-05-01 --equity 25000
  ```

- `cocoon backtest report <backtest_id> [--export {csv|json}]`
  Print a saved backtest, or export it.
  ```
  cocoon backtest report bt_4783407931961192
  cocoon backtest report bt_4783407931961192 --export csv
  cocoon backtest report bt_4783407931961192 --export json
  ```

### `cocoon trade`

- `cocoon trade start [--mode {live|paper}] [--profile NAME]`
  Start the live/paper loop. Defaults to `runtime.mode` from config. Foreground;
  Ctrl-C stops. Exit 20 if the EA doesn't answer, exit 21 on reconciliation
  conflict. `--dry-run` (as a global flag, before `trade`) prints intent only.
  ```
  cocoon trade start --mode paper
  cocoon --dry-run trade start --mode live
  ```

- `cocoon trade stop`
  Signal a running session to drain and shut down.
  ```
  cocoon trade stop
  ```

- `cocoon trade halt [--yes]`
  Signal SAFE_HALT (block new orders, keep monitoring). Prompts for confirmation
  unless `--yes` (or the global `--yes`).
  ```
  cocoon trade halt --yes
  ```

- `cocoon trade resume`
  Signal a halted session to re-reconcile and resume.
  ```
  cocoon trade resume
  ```

- `cocoon trade status [--watch]`
  Show the dashboard once, or `--watch` for a live-refreshing view. With
  `--output json` it prints the raw runtime state instead.
  ```
  cocoon trade status
  cocoon trade status --watch
  cocoon --output json trade status
  ```

### `cocoon positions`

- `cocoon positions list`
  List open positions from the local SQLite table.
  ```
  cocoon positions list
  ```

- `cocoon positions close <ticket_id> [--partial LOTS]`
  Close a position (whole, or a partial lot size). Needs a terminal.
  ```
  cocoon positions close 123456
  cocoon positions close 123456 --partial 0.05
  ```

### `cocoon report`

- `cocoon report session <session_id>`
  Summary of audit events for a session id.
  ```
  cocoon report session cocoon-ea
  ```

- `cocoon report daily --date DATE`
  Order activity for a given date.
  ```
  cocoon report daily --date 2026-07-03
  ```

- `cocoon report export --format {csv|json} --out PATH`
  Export the audit event log to a file.
  ```
  cocoon report export --format json --out ./out/audit.json
  cocoon report export --format csv --out ./out/audit.csv
  ```
  Note: reporting reads the SQLite `audit_events` table; the live runtime's audit
  trail is written to `logs/audit.jsonl`, and the two sinks are not bridged, so
  exports can be empty even after activity.

### `cocoon plugin`

- `cocoon plugin list`
  List discovered plugins (entry-point and local-file).
  ```
  cocoon plugin list
  ```

- `cocoon plugin install <path>`
  Install a local `.py` plugin (must expose `build_features()`). Exit 60 if it
  doesn't conform.
  ```
  cocoon plugin install ./my_indicator.py
  ```

- `cocoon plugin remove <name>`
  Remove an installed local plugin by name.
  ```
  cocoon plugin remove my_indicator
  ```

### `cocoon menu`
Launch the interactive questionary menu, which re-invokes the commands above.
```
cocoon menu
```

---

## Part 3 — Two full scripted runs

### A. Offline, CSV-seeded, single symbol

```
cocoon init
cocoon data import --symbol EURUSD --tf M5 --file EURUSD_M5.csv
cocoon data status
DS=$(cocoon --output json dataset build --symbols EURUSD --tf M5 --label-horizon 5 --deadband-bps 1.0 | jq -r .dataset_id)
RUN=$(cocoon --output json train run --dataset "$DS" --model lightgbm | jq -r .run_id)
cocoon model promote "$RUN" --stage production
BT=$(cocoon --output json backtest run --model-version "$RUN" --symbols EURUSD --tf M5 | jq -r .backtest_id)
cocoon backtest report "$BT" --export csv
```

### B. Multi-symbol ensemble with HPO

```
cocoon init
cocoon data import --symbol EURUSD --tf M5 --file EURUSD_M5.csv
cocoon data import --symbol GBPUSD --tf M5 --file GBPUSD_M5.csv
DS=$(cocoon --output json dataset build --symbols EURUSD,GBPUSD --tf M5 --label-horizon 8 --deadband-bps 1.5 | jq -r .dataset_id)
cocoon train run --dataset "$DS" --model lightgbm --hpo
cocoon train run --dataset "$DS" --model xgboost --hpo
RUN=$(cocoon --output json train run --dataset "$DS" --model ensemble | jq -r .run_id)
cocoon model promote "$RUN" --stage production
cocoon backtest run --model-version "$RUN" --symbols EURUSD,GBPUSD --tf M5
```
