# Cocoon Command Reference

A detailed description of every `cocoon` command: what it does, its arguments
and options, its side effects, its output, and how it fails. Companion
documents: `TERMINAL.md` (captured real output for every command) and
`TERMINAL_V2.md` (the terminal UI/UX standard the output follows).

Cocoon is a reference architecture for ML trading systems; the CLI is its
single entry point and composition root. The typical workflow is:

```
init → data import|fetch → dataset build → train run → model promote
     → backtest run → trade start --mode paper
```

---

## Global flags

Global flags go **before** the subcommand (`cocoon --output json model list`,
not `cocoon model list --output json`).

| Flag | Default | Description |
| ---- | ------- | ----------- |
| `--profile NAME` | `default` | Active config profile. Resolution precedence: built-in defaults → `config/base.yaml` → `config/profiles/<NAME>.yaml` → `COCOON_SECTION__KEY` environment variables. |
| `--config-file PATH` | — | Explicit config file; its parent directory becomes the config dir. |
| `--log-level LEVEL` | from config | `DEBUG\|INFO\|WARN\|ERROR` for the stderr/file log stream. |
| `--dry-run` | off | Mutating commands print a preview table (`dry_run True`, `action <verb>`, parameters) and exit 0 without doing anything. |
| `--yes` | off | Skip confirmation prompts (only `trade halt` prompts). |
| `--output MODE` | `table` | `table` renders themed blocks; `json` prints raw JSON with identical keys (objects for single results, arrays for lists) — the scripting contract. |

Results go to **stdout**; structured JSON logs and error blocks go to
**stderr**; exit codes come from a single catalogue (0 success — including
"not found" lookups; 1 generic; 10 config; 20 MT5 timeout; 21 reconciliation
conflict; 30 dataset; 31 training; 32 promotion; 40 risk hard-stop; 41 order
retry exhaustion; 50 protocol mismatch; 60 plugin; 130 clean SIGINT).

---

## `cocoon init`

**Purpose.** First-run scaffold: creates `config/` (+ `profiles/`), `data/`
(+ `raw/ features/ datasets/ models/ plugins/`), `logs/`, writes
`config/base.yaml` (the commented default config) and
`config/profiles/default.yaml` if missing.

**Behaviour.** Idempotent — re-running creates nothing and reports
`created 0`. Never overwrites existing files.

**Output.** `created` (count), `paths` (list of created paths).

```
cocoon init
```

---

## `cocoon config` — configuration management

### `config show [--profile P] [--resolved]`
Shows configuration as a key-value block, one row per section (`runtime`,
`mt5`, `feature_engineering`, `model`, `training`, `risk`, `order`,
`logging`) with nested keys flattened to `key = value` lines. With no
arguments (or `--resolved`) it shows the **fully merged** config; with
`--profile P` it shows that profile's **raw overrides only**.

### `config validate [--profile P]`
Re-resolves the configuration through the strict pydantic schema
(`extra="forbid"` — unknown keys, wrong types, and out-of-range values are
defects). Success prints `profile / valid ✓ True`; failure raises a config
error with **exit 10** before any engine is constructed.

### `config set <dot.path> <value> [--profile P]`
Writes a nested key (e.g. `risk.max_daily_loss_pct`) into the profile's YAML.
The value is parsed as JSON when possible (`1.5`, `true`, `["M5"]`), else
kept as a string. Creates the profile file if needed. Output echoes
`profile`, `key`, `value` after coercion.

```
cocoon config set training.walk_forward.train_window_days 5
```

### `config profile create <name> [--from OTHER]`
Creates `config/profiles/<name>.yaml`, optionally copying overrides from an
existing profile. An existing name is a **result** (`– already exists`,
exit 0), not an error.

### `config profile list`
Lists profile names found in `config/profiles/*.yaml`.

### `config profile delete <name>`
Deletes the profile file; a missing name reports `– not found` with exit 0.

---

## `cocoon data` — market data ingestion & cache

The cache is parquet per series under `data/raw/<SYMBOL>/<TF>.parquet` with
schema `ts_unix_ms, open, high, low, close, volume`.

### `data fetch --symbol SYM --tf TF --from DATE --to DATE`
Bulk-fetches bars from a running MetaTrader 5 terminal (requires the
`MetaTrader5` package) and merges them into the cache (deduplicated by
timestamp). Timeframes: `M1|M5|M15|M30|H1|H4|D1`; dates are UTC. Without
MT5 this raises `DataError` (exit 1) — use `data import` instead. Honours
`--dry-run`.

**Output.** `symbol`, `tf`, `bars` (fetched), `path`.

### `data import --symbol SYM --tf TF --file PATH`
Seeds the cache from a local CSV/Parquet file — the offline substitute for
`fetch`. Accepts common layouts: a `ts_unix_ms` column, a
`timestamp`/`datetime` column, or MetaTrader-export `<DATE>` + `<TIME>`
pairs (dotted dates handled); OHLC aliases are case- and
angle-bracket-insensitive; volume is optional; seconds vs. milliseconds
epochs are auto-detected. Fails with `DataError` (exit 1) on a missing
file, missing OHLC columns, no recognizable timestamp, or zero usable rows.
Honours `--dry-run` (the file is still read and normalised for the preview).

### `data status`
Coverage table for every cached series: `symbol`, `tf`, `bars`, `first`,
`last` (ISO UTC), ordered by symbol then timeframe chronologically.

### `data cache stats`
Cache totals: `files`, `total_bytes`, `root`.

### `data cache clear [--symbol SYM]`
Deletes cached parquet files — scoped to one symbol, or **everything** when
`--symbol` is omitted. Reports `files_removed`; zero is a normal result.

---

## `cocoon dataset` — dataset construction

### `dataset build --symbols A,B --tf TF --label-horizon N [--deadband-bps X]`
Builds a versioned training dataset from cached bars: causal features (the
25-feature catalogue) plus a **forward-return direction label** N bars ahead;
returns within ±X basis points are labelled neutral (dropped for binary
training). Deterministic: identical inputs produce the identical
content-hashed `ds_*` id, so re-runs are idempotent. Symbols with
insufficient cache are skipped.

**Output.** `dataset_id`, `rows`, `features`, `path`
(`data/datasets/<id>.parquet`). Fails with exit 30 on integrity failure.

### `dataset list`
All datasets: `dataset_id`, `symbols`, `tf`, `rows`, `horizon`.

### `dataset describe <ds_id>`
Full metadata for one dataset: symbols, timeframe, label horizon, deadband,
row count, the complete ordered feature-name list, and path.

---

## `cocoon features` — feature engineering

### `features list`
The registered FeatureFn catalogue in **registration order** — which is the
exact column order of every dataset and model feature vector (the `#`
ordinal makes that explicit). Categories: smart money concepts (bos, choch,
order_block, fvg, liquidity_sweep, premium_discount_zone), trend
(ema_dev_20/50/100/200), oscillator (rsi_14, atr_14_rel, bb_pct_b_20,
macd_hist_rel), session flags, day-of-week flags, and any installed plugins.

### `features build --symbol SYM --tf TF [--from --to]`
Computes all features over the cached bars in one causal full-frame pass and
writes `data/features/<SYMBOL>/<TF>.parquet`. An empty cache is a result
(`cached_bars 0`, exit 0), not an error. `--from/--to` are accepted for
symmetry; the build uses the cached range.

---

## `cocoon train` — model training

### `train run --dataset ds_* --model NAME [--hpo]`
Loads the dataset, converts it to a binary P(up) problem (neutral rows
dropped), scores **purged walk-forward folds** (per-fold ROC-AUC; window
sizes come from `training.walk_forward.*` in days, converted to bars by
timeframe — sparse caches need smaller windows or `n_folds` will be 0),
optionally runs Optuna HPO over those folds, fits the final artifact on the
full dataset, and registers it content-hashed. Models: `lightgbm`,
`xgboost`, `tabnet`, `ensemble` (weighted per `model.ensemble_weights`).
Deterministic: retraining re-registers the same `run_id`. The run is also
upserted into SQLite for `train status`.

**Output.** `run_id`, `model`, `metrics` (`walk_forward_auc_mean/std`,
`n_folds`, `n_samples`), `artifact_hash`. Exit 31 on training failure.

### `train walk-forward --dataset ds_* --model NAME`
Same pipeline surfaced with per-fold detail: `run_id`, `fold_scores` (list),
`metrics`.

### `train status <run_id>`
Registry/DB status for one run: `run_id`, `model`, `dataset_id`, `stage`,
`metrics` — or `found False` (exit 0) for an unknown id.

---

## `cocoon model` — model registry

### `model list`
Every registered run — `run_id`, `model`, `stage`, `dataset_id`, `hash`
(12 chars) — ordered deployables-first: production, then staging, then
unpromoted.

### `model inspect <run_id>`
The full registry entry (params, metrics, artifact hash, dataset) or
`found False`.

### `model promote <run_id> --stage staging|production`
Sets the run's stage. **Production is exclusive per model name**: promoting
demotes the previous production run of the same model to staging. The live
runtime picks its model by scanning for a production run in the order
`ensemble → <model.ensemble list>` — so to trade a specific model, make it
the *only* relevant production run. Exit 32 on promotion failure.

### `model delete <run_id>`
Removes the registry entry **and its artifact files**; reports
`deleted True|False`.

---

## `cocoon backtest` — backtesting

### `backtest run --model-version RUN_ID --symbols A,B [--tf TF] [--from --to] [--equity N]`
Event-driven backtest that runs the **same** Signal → Risk → Order engines as
live, with `SimulatedBrokerAdapter` swapped in behind the `BrokerAdapter`
contract: market orders fill at next-bar-open ± fixed slippage; SL/TP fill
conservatively when the bar range crosses the level; deterministic (no
wall-clock branching). Symbols with fewer than 300 usable bars are skipped
and reported in the result. The full payload is stored under
`data/backtests/<bt_id>.json`; the `bt_*` id is a content hash, so identical
runs produce the identical id.

**Output.** `backtest_id`, `total_trades`, `total_pnl`, and
`skipped (too few bars)` when applicable.

### `backtest report <bt_id> [--export csv|json]`
- **No flag:** a header block (model, symbols, timeframe, totals) plus a
  curated 80-column per-symbol table: `symbol, trades, win %, PF, pnl, dd %,
  sharpe, sig, rej`.
- **`--export json`:** the complete stored payload, full precision.
- **`--export csv` on a terminal:** a transposed full-detail table (14
  metric rows — trades, win rate, profit factor, avg win/loss, gross
  profit/loss, expectancy, total pnl, final equity, max drawdown, sharpe,
  signals, rejected — one column per symbol).
- **`--export csv` piped/redirected:** raw CSV (floats at 6 significant
  digits), bypassing the renderer so redirection is byte-safe.
- Unknown id → `found False`, exit 0.

---

## `cocoon trade` — live/paper trading

### `trade start [--mode live|paper] [--profile P] [--symbol SYM] [--tf TF] [--speed N] [--equity N] [--dashboard/--no-dashboard]`
The composition root of the trading loop. Drives the state machine (INIT →
… → RUNNING), connects a broker, **reconciles** broker state against SQLite
(conflicts exit 21; in paper mode stale local paper positions are auto-closed
instead), builds the engines around the production model (none promoted →
`ModelError` with a promote hint), then runs the bar-driven
inference → signal → risk → order pipeline. Runs in the foreground; Ctrl-C
stops cleanly.

- **`--mode paper` (default via `runtime.mode`):** no MT5 needed. The
  backtest's simulated broker is substituted and a feed thread **replays
  cached bars** through the full live pipeline, starting from an *empty*
  feature window so features see bars strictly in replay order (no
  lookahead). Fills at bar close ± slippage; SL/TP exit on bar range;
  realized PnL feeds back into account state so the daily-loss breaker and
  position limits operate honestly; leftovers are force-closed at the last
  price. Options: `--symbol/--tf` select the replayed cache (default: the
  largest), `--speed` bars/second (default 20; `0` = as fast as possible),
  `--equity` starting account (default 10 000). On a terminal a **live
  dashboard** renders at 5 Hz (progress bar, equity/PnL stat row, equity
  sparkline, open-positions table) with console logs diverted to
  `logs/app.log`; a `paper session summary` block prints at the end.
- **`--mode live`:** connects the ZMQ/msgpack bridge to the MetaTrader 5 EA;
  without a compatible EA the HELLO handshake times out (**exit 20**). Note
  the shipped `CocoonEA.mq5` is a JSON-speaking skeleton — live mode requires
  porting it to msgpack.

### `trade status [--watch]`
One-shot rounded panel (or 2 Hz live view with `--watch`): mode, profile,
state, open positions vs. limit, unrealized P&L, daily-loss budget, the
positions table, bridge connectivity, and the configured ensemble. Reads the
file-backed `data/runtime/state.json`, so it works from any terminal on the
host. `--output json` returns the raw state object.

### `trade halt [--yes]`
Prompts `Halt trading (SAFE_HALT)?` (skipped with `--yes`), then writes the
control file. The running loop transitions to SAFE_HALT: **no new trades**,
but market data keeps ingesting so the feature window stays warm; a paper
replay pauses.

### `trade resume`
Signals the halted loop to reconcile and return to RUNNING (a paper replay
continues).

### `trade stop`
Signals a clean shutdown from any terminal (control is file-based — no
daemon).

---

## `cocoon positions` — position management

### `positions list`
Open positions from SQLite: `ticket`, `symbol`, `dir`, `lots`, `entry`,
`pnl`, `origin` (`internal` = ours; `external` = imported at reconciliation,
never auto-closed). Empty is the one-line `– none` state.

### `positions close <ticket> [--partial LOTS]`
Requests a close through the broker bridge and marks the DB position closed.
Requires a reachable EA (exit 20 otherwise). Honours `--dry-run`.

---

## `cocoon report` — reporting & export

Reads the SQLite mirror of the audit trail (every ORDER/SIGNAL/
STATE_TRANSITION/ERROR event is written to `logs/audit.jsonl` **and**
mirrored to the DB with the same monotonic `seq`).

### `report daily --date YYYY-MM-DD`
ORDER audit payloads filtered to that UTC day (max 100 rows):
idempotency key, symbol, direction, lots, status, ticket, filled volume and
price, reject reason, attempt.

### `report session <id>`
Event/order counts for a session id. **Known gap:** audit payloads carry no
session id yet, so this currently always reports 0.

### `report export --format csv|json --out PATH`
Dumps up to 5 000 audit events to a file (JSON pretty-printed, or CSV with
`seq, ts_unix_ms, event_type, payload`). Unknown format → status result with
exit 1.

---

## `cocoon plugin` — feature plugins

### `plugin list`
Discovered plugins — entry-point packages and local files: `name`, `kind`,
`source`.

### `plugin install <path.py>`
Installs a local feature plugin: a `.py` file exposing `build_features()`
returning FeatureFn object(s), copied into `data/plugins/`. Installed
features join the catalogue (category `plugin`). Non-conforming files fail
with **exit 60**.

### `plugin remove <name>`
Removes an installed local plugin by name; reports `removed True|False`.

---

## `cocoon menu`

An interactive, questionary-driven nested menu that is a thin presentation
layer re-invoking the same commands above — so the interactive UI cannot
drift from the CLI's behaviour.
