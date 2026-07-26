# TERMINAL_COMMANDS.md — Standardized Machine Learning Trading System

Every terminal command for operating Cocoon from a clean machine to
production-style operations, organized by lifecycle. Authoritative
references: `ARCHITECTURE.md` (system contract) and `ARCHITECTURE.mmd`
(diagram). Output follows the v2.1 terminal standard (`TERMINAL_V2.md`);
captured real outputs live in `TERMINAL.md`.

**Honesty rule (per architecture):** every command below is real and
executable against this repository. Where a lifecycle area has no shipped
implementation (Docker, Kubernetes, external message brokers, a test suite),
this document says so explicitly instead of inventing commands — see
Part 16.

**Shell conventions.** Commands are shown for PowerShell (Windows) and Bash
(Linux/macOS) when they differ; `cocoon …` commands are identical in both.
Global flags go **before** the subcommand: `cocoon --output json model list`.

**Master execution order:**

```
[1 Setup] → [2 Init/Config] → [3 Data] → [4 Features] → [5 Dataset]
→ [6 Train/HPO] → [7 Model mgmt] → [8 Backtest] → [9 Paper trading]
→ [10 Live trading] → [11 Monitor/Logs] → [12 DB/Backup] (any time)
→ [13 Dev/CI] (any time) → [14 Maintenance] → [15 Diagnostics] (as needed)
```

**Exit-code catalogue (used throughout):**
`0` success (including not-found lookups) · `1` generic error · `10` config
validation · `11` secret in config file · `20` MT5 connect timeout · `21`
reconciliation conflict · `30` dataset build failure · `31` training failure
· `32` model promotion failure · `40` risk hard-stop · `41` order retry
exhaustion · `50` bridge protocol mismatch · `60` plugin load failure ·
`130` clean SIGINT shutdown.

---

# Part 1 — Setup & Environment

## 1.1 Clone the repository

- **Purpose.** Obtain the source tree.
- **Prerequisites.** `git` installed; network access.
- **Command.**
  ```powershell
  git clone https://github.com/<owner>/cocoon.git ; cd cocoon
  ```
  ```bash
  git clone https://github.com/<owner>/cocoon.git && cd cocoon
  ```
- **Breakdown.** `clone` copies the repo; `cd` enters it (all later commands
  run from the repo root).
- **Expected output.** Git progress ending `Resolving deltas: 100%`.
- **Terminal UI.**
  ```console
  $ git clone https://github.com/<owner>/cocoon.git
  Cloning into 'cocoon'...
  Resolving deltas: 100% (…), done.
  ```
- **Generates.** `./cocoon/` working tree.
- **Exit codes.** 0 ok; 128 bad URL/auth.
- **Verify.** `git -C cocoon log --oneline -1`
- **Failures.**

  | Failure | Error message | Resolution |
  | --- | --- | --- |
  | Bad URL / no access | `fatal: repository … not found` | Fix URL; authenticate (`gh auth login`) |
  | Proxy/network | `fatal: unable to access …` | Configure proxy / retry |
- **Best practices.** Clone over SSH for push access; never work directly on
  `main` for changes.
- **Related.** 13.4 (CI triggers on push).
- **Order.** Step 1 of setup.

## 1.2 Verify Python version

- **Purpose.** Cocoon requires Python `>=3.11,<=3.12.10` (pyproject).
- **Prerequisites.** Python installed.
- **Command.**
  ```powershell
  python --version
  ```
  ```bash
  python3 --version
  ```
- **Breakdown.** Prints interpreter version; must report 3.11.x or 3.12.x.
- **Expected output.** `Python 3.12.x`.
- **Terminal UI.**
  ```console
  $ python --version
  Python 3.12.10
  ```
- **Generates.** Nothing.
- **Exit codes.** 0; 9009/127 if not on PATH.
- **Verify.** `python -c "import sys; print(sys.version_info[:2])"` → `(3, 12)` or `(3, 11)`.
- **Failures.**

  | Failure | Error message | Resolution |
  | --- | --- | --- |
  | Not installed / not on PATH | `'python' is not recognized` / `command not found` | Install 3.11/3.12; on Windows try `py -3.12 --version` |
  | Wrong version | `Python 3.13.x` | Install a supported version; create the venv with it explicitly |
- **Best practices.** Pin the interpreter when creating the venv (1.3).
- **Related.** 1.3.
- **Order.** Step 2 of setup.

## 1.3 Create a virtual environment

- **Purpose.** Isolate Cocoon's pinned dependencies.
- **Prerequisites.** 1.2 passed.
- **Command.**
  ```powershell
  python -m venv .venv
  ```
  ```bash
  python3 -m venv .venv
  ```
- **Breakdown.** `-m venv` runs the stdlib venv module; `.venv` is the target
  directory.
- **Expected output.** Silent on success.
- **Terminal UI.**
  ```console
  $ python -m venv .venv
  $
  ```
- **Generates.** `.venv/` (interpreter, `Scripts/`|`bin/`, `pyvenv.cfg`).
- **Exit codes.** 0; 1 on permission/disk errors.
- **Verify.** PowerShell `Test-Path .venv\Scripts\python.exe` → `True`; Bash `test -x .venv/bin/python && echo ok`.
- **Failures.**

  | Failure | Error message | Resolution |
  | --- | --- | --- |
  | ensurepip missing (Debian) | `ensurepip is not available` | `sudo apt install python3.12-venv` |
  | Permissions | `PermissionError: [Errno 13]` | Create in a user-writable path |
- **Best practices.** One venv per checkout; never commit `.venv/`.
- **Related.** 1.4, 1.6.
- **Order.** Step 3 of setup.

## 1.4 Activate the virtual environment

- **Purpose.** Put the venv's `python`/`cocoon` first on PATH.
- **Prerequisites.** 1.3.
- **Command.**
  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```
  ```bash
  source .venv/bin/activate
  ```
- **Breakdown.** Sourcing the activation script prepends the venv to PATH and
  sets `VIRTUAL_ENV`.
- **Expected output.** Prompt gains a `(.venv)` prefix.
- **Terminal UI.**
  ```console
  PS C:\…\cocoon> .\.venv\Scripts\Activate.ps1
  (.venv) PS C:\…\cocoon>
  ```
- **Generates.** Nothing (session state only).
- **Exit codes.** 0.
- **Verify.** `python -c "import sys; print(sys.prefix)"` → path ends in `.venv`.
- **Failures.**

  | Failure | Error message | Resolution |
  | --- | --- | --- |
  | PS execution policy | `…Activate.ps1 cannot be loaded because running scripts is disabled` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
- **Best practices.** Activate in every new shell before running `cocoon`.
- **Related.** 1.6.
- **Order.** Step 4 of setup.

## 1.5 Upgrade pip

- **Purpose.** Avoid resolver bugs in old pip when installing pinned deps.
- **Prerequisites.** 1.4.
- **Command.**
  ```powershell
  python -m pip install --upgrade pip
  ```
- **Breakdown.** Upgrades pip inside the venv only (same command in CI).
- **Expected output.** `Successfully installed pip-<version>` or
  `Requirement already satisfied`.
- **Terminal UI.**
  ```console
  $ python -m pip install --upgrade pip
  Successfully installed pip-25.x
  ```
- **Generates.** Updated `pip` in `.venv`.
- **Exit codes.** 0; 1 on network failure.
- **Verify.** `pip --version`.
- **Failures.** Network/proxy → `Could not find a version …` → configure
  index/proxy, retry.
- **Best practices.** Always `python -m pip` (never bare `pip`) so the venv's
  pip is used.
- **Related.** 1.6.
- **Order.** Step 5 of setup.

## 1.6 Install Cocoon (editable)

- **Purpose.** Install the package and its pinned dependency set
  (typer/rich/pydantic/polars/lightgbm/xgboost/pytorch-tabnet/optuna/mlflow/
  pyzmq/msgpack/sqlalchemy/structlog/apscheduler/numpy/scikit-learn/pyyaml),
  and register the `cocoon` console script
  (`cocoon = cocoon.cli.main:entrypoint`).
- **Prerequisites.** 1.4, 1.5; ~2 GB disk (torch via pytorch-tabnet).
- **Command.**
  ```powershell
  pip install -e .
  ```
- **Breakdown.** `-e` = editable/development install: source edits take
  effect without reinstalling; `.` = the repo root's `pyproject.toml`
  (hatchling build backend).
- **Expected output.** Dependency resolution ending
  `Successfully installed cocoon-0.1.0 …`.
- **Terminal UI.**
  ```console
  $ pip install -e .
  Successfully installed cocoon-0.1.0 lightgbm-4.5.* polars-1.* …
  ```
- **Generates.** `.venv` site-packages; `cocoon` executable in
  `.venv/Scripts/` (Windows) or `.venv/bin/`.
- **Exit codes.** 0; 1 on resolution/build failure.
- **Verify.** `cocoon --help` prints the command groups (1.7).
- **Failures.**

  | Failure | Error message | Resolution |
  | --- | --- | --- |
  | Unsupported Python | `Package … requires a different Python` | Recreate venv with 3.11/3.12 (1.2–1.3) |
  | Compiler/network for a wheel | `Failed building wheel for …` | Upgrade pip (1.5); use a platform with prebuilt wheels |
- **Best practices.** Editable install is the development *and* single-host
  operations mode; re-run after `git pull` (14.5).
- **Related.** 1.7, 14.5.
- **Order.** Step 6 of setup.

## 1.7 Smoke-test the CLI

- **Purpose.** Prove the entry point loads (same gate CI runs).
- **Prerequisites.** 1.6.
- **Command.**
  ```powershell
  cocoon --help
  ```
- **Breakdown.** Loads the typer app and prints global flags + command
  groups: `init config data dataset features train model backtest trade
  positions report plugin menu`.
- **Expected output.** Usage text listing all groups; exit 0.
- **Terminal UI.**
  ```console
  $ cocoon --help
  Usage: cocoon [OPTIONS] COMMAND [ARGS]...
  Cocoon — Forex Trading ML Model V1 CLI
  ╭─ Commands ─────────────────────────────────────────╮
  │ init  config  data  dataset  features  train  …    │
  ╰────────────────────────────────────────────────────╯
  ```
- **Generates.** Nothing.
- **Exit codes.** 0.
- **Verify.** `cocoon --help; echo $LASTEXITCODE` (PS) / `echo $?` (bash) → 0.
- **Failures.** `'cocoon' is not recognized` → venv not activated (1.4) or
  install failed (1.6).
- **Best practices.** Run after every upgrade.
- **Related.** 13.1–13.3 (CI parity).
- **Order.** Step 7 of setup.

## 1.8 Install the MetaTrader 5 package (live fetch only — optional)

- **Purpose.** Enables `cocoon data fetch` and is a prerequisite of the live
  bridge host. Not needed for the offline pipeline or paper trading.
- **Prerequisites.** Windows + an installed MetaTrader 5 terminal.
- **Command.**
  ```powershell
  pip install MetaTrader5
  ```
- **Breakdown.** Installs the broker terminal's Python API (Windows-only
  wheels).
- **Expected output.** `Successfully installed MetaTrader5-5.x`.
- **Terminal UI.**
  ```console
  $ pip install MetaTrader5
  Successfully installed MetaTrader5-5.0.x
  ```
- **Generates.** Site-packages entry.
- **Exit codes.** 0; 1 (no wheel on non-Windows).
- **Verify.** `python -c "import MetaTrader5 as mt5; print(mt5.__version__)"`.
- **Failures.** `No matching distribution` on Linux/macOS → expected; use
  `cocoon data import` instead (3.1).
- **Best practices.** Keep optional; the pipeline is designed to run offline.
- **Related.** 3.2, 10.x.
- **Order.** Optional; before 3.2.

## 1.9 Dependency health check

- **Purpose.** Detect broken/conflicting installs.
- **Prerequisites.** 1.6.
- **Command.**
  ```powershell
  pip check ; pip list --format=freeze > pip-freeze.txt
  ```
- **Breakdown.** `pip check` validates declared dependency constraints;
  `pip list --format=freeze` snapshots exact versions for reproducibility.
- **Expected output.** `No broken requirements found.`
- **Terminal UI.**
  ```console
  $ pip check
  No broken requirements found.
  ```
- **Generates.** `pip-freeze.txt` (environment snapshot — keep with backups).
- **Exit codes.** 0 clean; 1 conflicts.
- **Verify.** Inspect `pip-freeze.txt` for the pinned majors from
  `pyproject.toml`.
- **Failures.** Conflict lines like `pkg X has requirement Y` → reinstall
  from a clean venv (14.6).
- **Best practices.** Snapshot before every upgrade; store beside backups
  (12.4).
- **Related.** 12.4, 14.5.
- **Order.** End of setup; before upgrades.

## 1.10 Seed environment-variable configuration (optional)

- **Purpose.** Configure via environment instead of YAML —
  `COCOON_SECTION__KEY` overrides everything (highest precedence).
- **Prerequisites.** None.
- **Command.**
  ```powershell
  Copy-Item .env.example .env    # then edit; or set directly:
  $env:COCOON_RUNTIME__MODE = "paper"
  ```
  ```bash
  cp .env.example .env
  export COCOON_RUNTIME__MODE=paper
  ```
- **Breakdown.** Double underscore separates section and key
  (`runtime.mode` → `COCOON_RUNTIME__MODE`). `.env` is loaded at startup.
- **Expected output.** None (state change).
- **Terminal UI.**
  ```console
  $ export COCOON_RUNTIME__MODE=paper
  $ cocoon config show | grep mode
  runtime  mode = paper
  ```
- **Generates.** `.env` (never commit it).
- **Exit codes.** 0.
- **Verify.** `cocoon config show` reflects the override.
- **Failures.** Wrong shape (`COCOON_RUNTIME_MODE`, single underscore) →
  silently ignored → use `__`.
- **Best practices.** Secrets belong in env/`.env` only — a secret found in a
  config *file* is exit 11 by design.
- **Related.** 2.3, 2.4.
- **Order.** Any time before running commands.

---

# Part 2 — Project Initialization & Configuration

## 2.1 `cocoon init`

- **Purpose.** First-run scaffold: `config/` (+ `profiles/`), `data/`
  (+ `raw/ features/ datasets/ models/ plugins/`), `logs/`, a commented
  `config/base.yaml`, and `config/profiles/default.yaml`.
- **Prerequisites.** 1.6; run from the directory that should own the
  workspace.
- **Command.**
  ```powershell
  cocoon init
  ```
- **Breakdown.** No arguments. Idempotent: creates only what is missing,
  never overwrites.
- **Expected output.** `created` count and the `paths` list (0/empty on
  re-run).
- **Terminal UI.**
  ```console
  $ cocoon init
  cocoon initialised
    created  11
    paths    config, config/profiles, data, data/raw, …
  ```
- **Generates.** `config/`, `data/`, `logs/` trees; `config/base.yaml`;
  `config/profiles/default.yaml`.
- **Exit codes.** 0.
- **Verify.** `cocoon config validate` (2.2).
- **Failures.** Read-only directory → `PermissionError` (exit 1) → run in a
  writable path.
- **Best practices.** One workspace per strategy/account; keep `config/`
  under version control, keep `data/` and `logs/` out of it.
- **Order.** Step 1 after setup.

## 2.2 `cocoon config validate [--profile P]`

- **Purpose.** Schema-check the fully resolved configuration before any
  engine is constructed. Unknown keys, wrong types, out-of-range values all
  fail.
- **Prerequisites.** 2.1.
- **Command.**
  ```powershell
  cocoon config validate
  ```
- **Breakdown.** `--profile P` validates another profile (default: active).
- **Expected output.** `profile default / valid ✓ True`.
- **Terminal UI.**
  ```console
  $ cocoon config validate
  config validate
    profile  default
    valid    ✓ True
  ```
- **Generates.** Nothing.
- **Exit codes.** 0 valid; **10** invalid.
- **Verify.** Exit code 0.
- **Failures.**

  | Failure | Error message | Resolution |
  | --- | --- | --- |
  | Typo'd key in YAML | `✗ ConfigError: … Extra inputs are not permitted` | Fix or remove the key (`extra="forbid"` is intentional) |
  | Out-of-range value | pydantic range error | Respect the field constraint shown |
- **Best practices.** Run after **every** `config set` and after upgrades;
  CI runs it on every push.
- **Related.** 2.3, 2.4, 13.4.
- **Order.** Immediately after 2.1 and after any config change.

## 2.3 `cocoon config show [--profile P] [--resolved]`

- **Purpose.** Inspect configuration: fully merged (default/`--resolved`) or
  a single profile's raw overrides (`--profile P`).
- **Prerequisites.** 2.1.
- **Command.**
  ```powershell
  cocoon config show
  cocoon --output json config show    # scripting form
  ```
- **Breakdown.** Eight sections (`runtime mt5 feature_engineering model
  training risk order logging`), nested keys flattened to `key = value`.
- **Expected output.** One row per section.
- **Terminal UI.**
  ```console
  $ cocoon config show
  resolved config
    runtime  mode = paper
             log_level = INFO
             …
  ```
- **Generates.** Nothing.
- **Exit codes.** 0.
- **Verify.** Cross-check a known override appears.
- **Failures.** Missing profile file with `--profile` → empty block (result,
  not error).
- **Best practices.** `--output json config show > resolved-config.json`
  before every live/paper session — it is your audit snapshot.
- **Related.** 2.4, 11.4.
- **Order.** Any time.

## 2.4 `cocoon config set <dot.path> <value> [--profile P]`

- **Purpose.** Write one nested key into a profile YAML.
- **Prerequisites.** 2.1.
- **Command.**
  ```powershell
  cocoon config set risk.max_daily_loss_pct 2.0
  cocoon config set training.walk_forward.train_window_days 5
  ```
- **Breakdown.** `dot.path` navigates sections; value parsed as JSON when
  possible (`1.5`, `true`, `["M5"]`), else string.
- **Expected output.** Echo of `profile`, `key`, `value`.
- **Terminal UI.**
  ```console
  $ cocoon config set risk.max_daily_loss_pct 2.0
  config set
    profile  default
    key      risk.max_daily_loss_pct
    value    2.0
  ```
- **Generates.** Updates `config/profiles/<P>.yaml`.
- **Exit codes.** 0 (validation happens at next resolve).
- **Verify.** `cocoon config validate` then `cocoon config show`.
- **Failures.** Setting an unknown key succeeds at write time but fails
  validation with exit 10 → remove it.
- **Best practices.** Always follow with 2.2; keep profiles in git so config
  rollback = `git checkout -- config/`.
- **Related.** 2.2, 2.5, 12.4.
- **Order.** As needed; before sessions.

## 2.5 `cocoon config profile create|list|delete`

- **Purpose.** Manage named configuration profiles (e.g., `paper`, `prod`).
- **Prerequisites.** 2.1.
- **Command.**
  ```powershell
  cocoon config profile create prod --from default
  cocoon config profile list
  cocoon config profile delete prod
  ```
- **Breakdown.** `create --from X` copies overrides; `delete` removes the
  YAML file; selection happens per-invocation via the global `--profile`.
- **Expected output.** `✓ created` / list / `✓ deleted`; duplicates and
  missing names are dim results with exit 0.
- **Terminal UI.**
  ```console
  $ cocoon config profile create prod --from default
  profile create
    profile  prod
    status   ✓ created
    path     config\profiles\prod.yaml
  ```
- **Generates.** `config/profiles/<name>.yaml`.
- **Exit codes.** 0.
- **Verify.** `cocoon --profile prod config validate`.
- **Failures.** None fatal; `– already exists` / `– not found` are results.
- **Best practices.** One profile per environment; run live sessions with an
  explicit `--profile`.
- **Related.** 2.2–2.4.
- **Order.** Before first paper/live session.

---

# Part 3 — Data (Cache & Storage)

## 3.1 `cocoon data import` — seed the cache offline

- **Purpose.** Load OHLCV bars from CSV/Parquet into the parquet cache —
  the offline substitute for MT5 fetch; the whole pipeline runs from it.
- **Prerequisites.** 2.1; a bar file.
- **Command.**
  ```powershell
  cocoon data import --symbol EURUSD --tf M5 --file .\bars.csv
  cocoon --dry-run data import --symbol EURUSD --tf M5 --file .\bars.csv
  ```
- **Breakdown.** `--symbol/--tf` file the bars under a series;
  `--file` accepts CSV or Parquet with: `ts_unix_ms` **or**
  `timestamp`/`datetime` **or** MT5-export `<DATE>`+`<TIME>` columns
  (dotted dates ok); OHLC aliases case/bracket-insensitive; volume optional;
  seconds-vs-ms epochs auto-detected.
- **Expected output.** `symbol, tf, bars, path`.
- **Terminal UI.**
  ```console
  $ cocoon data import --symbol EURUSD --tf M5 --file .\bars.csv
  imported
    symbol  EURUSD
    tf      M5
    bars    3002
    path    data\raw\EURUSD\M5.parquet
  ```
- **Generates.** `data/raw/<SYMBOL>/<TF>.parquet` (merged, deduped by
  timestamp).
- **Exit codes.** 0; **1** (`DataError`) on bad input.
- **Verify.** `cocoon data status` shows the series with the expected bar
  count and range.
- **Failures.**

  | Failure | Error message | Resolution |
  | --- | --- | --- |
  | Wrong path | `✗ DataError: Import file not found` | Fix `--file` |
  | Missing OHLC | `✗ DataError: Import file is missing required OHLC columns` | Context lists `missing` vs `found`; rename columns |
  | No timestamp | `✗ DataError: Import file has no recognizable timestamp column` | Provide one of the accepted layouts |
  | Empty after parse | `✗ DataError: Import file produced zero usable rows` | Check delimiter/encoding |
- **Best practices.** Import **out-of-sample** data (a range the model never
  trained on) before trusting any paper-trade PnL.
- **Related.** 3.3, 5.1, 9.1.
- **Order.** First data step (offline path).

## 3.2 `cocoon data fetch` — pull bars from MetaTrader 5

- **Purpose.** Bulk-fetch bars from a running MT5 terminal into the cache.
- **Prerequisites.** 1.8; MT5 terminal running and logged in.
- **Command.**
  ```powershell
  cocoon data fetch --symbol EURUSD --tf M5 --from 2024-01-01 --to 2024-06-01
  cocoon --dry-run data fetch --symbol EURUSD --tf M5 --from 2024-01-01 --to 2024-06-01
  ```
- **Breakdown.** `--tf` ∈ `M1|M5|M15|M30|H1|H4|D1`; dates UTC; result merges
  into the cache (dedup by timestamp).
- **Expected output.** `symbol, tf, bars, path`.
- **Terminal UI.**
  ```console
  $ cocoon data fetch --symbol EURUSD --tf M5 --from 2024-01-01 --to 2024-06-01
  fetched
    symbol  EURUSD
    tf      M5
    bars    42,816
    path    data\raw\EURUSD\M5.parquet
  ```
- **Generates.** Same cache file as 3.1.
- **Exit codes.** 0; **1** (`DataError`) without the package/terminal.
- **Verify.** `cocoon data status`.
- **Failures.** `✗ DataError: …MetaTrader5…` → install 1.8, start the
  terminal; or use 3.1.
- **Best practices.** Fetch once, then work from the cache — the pipeline is
  cache-first by design.
- **Related.** 3.1, 3.3.
- **Order.** First data step (online path).

## 3.3 `cocoon data status`

- **Purpose.** Coverage inventory of the cache.
- **Prerequisites.** Data present (3.1/3.2).
- **Command.**
  ```powershell
  cocoon data status
  ```
- **Breakdown.** One row per series: `symbol, tf, bars, first, last`
  (ISO UTC), ordered symbol → timeframe chronologically.
- **Expected output / Terminal UI.**
  ```console
  $ cocoon data status
  data coverage
    SYMBOL  TF   BARS  FIRST                      LAST
    EURUSD  M5   3002  2024-01-01T00:00:00+00:00  2025-03-21T07:35:00+00:00
  ```
- **Generates.** Nothing.
- **Exit codes.** 0.
- **Verify.** Bar counts match what was imported/fetched.
- **Failures.** Empty cache → `data coverage  – none`.
- **Best practices.** Check `first`/`last` for gaps before building datasets
  — a sparse cache changes walk-forward windowing (6.3 note).
- **Related.** 3.4, 5.1.
- **Order.** After every ingest.

## 3.4 `cocoon data cache stats`

- **Purpose.** Cache size totals.
- **Command.**
  ```powershell
  cocoon data cache stats
  ```
- **Expected output / Terminal UI.**
  ```console
  $ cocoon data cache stats
  cache stats
    files        3
    total_bytes  148,847
    root         data\raw
  ```
- **Prerequisites / Generates / Exit codes.** 2.1 / nothing / 0.
- **Verify.** Matches `data status` series count.
- **Failures.** None.
- **Best practices.** Watch growth; prune with 3.5.
- **Related.** 3.5, 14.x.
- **Order.** Any time.

## 3.5 `cocoon data cache clear [--symbol SYM]`

- **Purpose.** Delete cached parquet files (one symbol, or **all** when
  unscoped).
- **Prerequisites.** Nothing running that reads the cache.
- **Command.**
  ```powershell
  cocoon data cache clear --symbol GBPUSD
  ```
- **Breakdown.** Omit `--symbol` to wipe every series — destructive.
- **Expected output / Terminal UI.**
  ```console
  $ cocoon data cache clear --symbol GBPUSD
  cache clear
    symbol         GBPUSD
    files_removed  1
  ```
- **Generates.** Removes `data/raw/<SYMBOL>/*.parquet`.
- **Exit codes.** 0 (0 removals is a normal result).
- **Verify.** `cocoon data status` no longer lists the series.
- **Failures.** File locked by a running replay → stop it (9.3) first.
- **Best practices.** Back up (12.4) before an unscoped clear; datasets/models
  already built are unaffected (they are separate artifacts).
- **Related.** 3.3, 12.4.
- **Order.** Maintenance only.

---

# Part 4 — Feature Engineering & Plugins

## 4.1 `cocoon features list`

- **Purpose.** The registered feature catalogue in **registration order** —
  which *is* the feature-vector column order for every dataset and model.
- **Command.**
  ```powershell
  cocoon features list
  ```
- **Expected output / Terminal UI.**
  ```console
  $ cocoon features list
  registered FeatureFn catalogue
     #  NAME         CATEGORY
     1  bos          smart money concepts
    12  atr_14_rel   oscillator
    25  dow_6        day-of-week flag
  ```
- **Prerequisites / Generates / Exit codes.** 1.6 / nothing / 0.
- **Verify.** 25 rows (plus any installed plugins).
- **Failures.** A broken installed plugin → exit 60 → remove it (4.3).
- **Best practices.** Never reorder features between training and serving —
  the ordinal column exists to make drift visible.
- **Related.** 4.2, 4.3, 5.1.
- **Order.** Before first dataset build; after plugin changes.

## 4.2 `cocoon features build --symbol SYM --tf TF`

- **Purpose.** One causal full-frame feature pass over cached bars, written
  to a parquet for inspection/analysis.
- **Prerequisites.** 3.1/3.2.
- **Command.**
  ```powershell
  cocoon features build --symbol EURUSD --tf M5
  ```
- **Breakdown.** `--from/--to` accepted for symmetry; the cached range is
  used.
- **Expected output / Terminal UI.**
  ```console
  $ cocoon features build --symbol EURUSD --tf M5
  features built
    symbol    EURUSD
    tf        M5
    rows      3002
    features  25
    path      data\features\EURUSD\M5.parquet
  ```
- **Generates.** `data/features/<SYMBOL>/<TF>.parquet`.
- **Exit codes.** 0 (an empty cache prints `cached_bars 0` and exits 0).
- **Verify.** Row count equals cache bar count.
- **Failures.** No cached bars → `cached_bars 0` → ingest first (3.1).
- **Best practices.** Use this artifact for feature QA; dataset build (5.1)
  recomputes features itself — this file is not an input to it.
- **Related.** 4.1, 5.1.
- **Order.** Optional QA step after ingest.

## 4.3 `cocoon plugin install|list|remove`

- **Purpose.** Extend the feature catalogue at runtime with local `.py`
  plugins (a `build_features()` returning FeatureFn object(s)) or
  entry-point packages.
- **Prerequisites.** 2.1.
- **Command.**
  ```powershell
  cocoon plugin install .\my_indicator.py
  cocoon plugin list
  cocoon plugin remove my_indicator
  ```
- **Breakdown.** `install` copies the file into `data/plugins/` after
  interface validation; `remove` deletes by name.
- **Expected output / Terminal UI.**
  ```console
  $ cocoon plugin install .\my_indicator.py
  plugin install
    name    my_indicator
    source  data\plugins\my_indicator.py
    status  ✓ installed
  ```
- **Generates.** `data/plugins/<name>.py`.
- **Exit codes.** 0; **60** on a non-conforming plugin.
- **Verify.** `cocoon features list` shows the new feature(s), category
  `plugin`, appended at the end.
- **Failures.** `✗ PluginError: …` (exit 60) → plugin must expose
  `build_features()` returning FeatureFn object(s).
- **Best practices.** Installing a plugin **changes the feature vector** —
  rebuild datasets and retrain before trading; never add plugins mid-session.
- **Related.** 4.1, 5.1, 6.1.
- **Order.** Before dataset build, never after training.

---

# Part 5 — Dataset Management

## 5.1 `cocoon dataset build`

- **Purpose.** Build a content-hashed, versioned training dataset: causal
  features + forward-return direction labels.
- **Prerequisites.** Cached bars (3.x).
- **Command.**
  ```powershell
  cocoon dataset build --symbols EURUSD --tf M5 --label-horizon 12 --deadband-bps 2
  ```
- **Breakdown.** `--symbols` comma-separated; `--label-horizon N` = bars
  ahead for the forward return; `--deadband-bps X` labels returns within ±X
  bps as neutral (dropped in binary training). Deterministic: identical
  inputs → identical `ds_*` id.
- **Expected output / Terminal UI.**
  ```console
  $ cocoon dataset build --symbols EURUSD --tf M5 --label-horizon 12 --deadband-bps 2
  dataset built
    dataset_id  ds_782987baf2387d02
    rows        2990
    features    25
    path        data\datasets\ds_782987baf2387d02.parquet
  ```
- **Generates.** `data/datasets/<ds_id>.parquet` + metadata.
- **Exit codes.** 0; **30** on integrity failure.
- **Verify.** `cocoon dataset describe <ds_id>`; re-run the same command —
  the id must not change.
- **Failures.** Too little cache → fewer rows than expected → ingest more
  data; symbol missing from cache → skipped.
- **Best practices.** Sweep horizon/deadband as separate datasets and compare
  by walk-forward AUC + backtest — ids keep them distinguishable forever.
- **Related.** 5.2, 5.3, 6.1.
- **Order.** After data, before training.

## 5.2 `cocoon dataset list`

- **Command.** `cocoon dataset list`
- **Purpose.** Inventory: `dataset_id, symbols, tf, rows, horizon`.
- **Terminal UI.**
  ```console
  $ cocoon dataset list
  datasets
    DATASET ID           SYMBOLS  TF  ROWS  HORIZON
    ds_782987baf2387d02  EURUSD   M5  2990       12
  ```
- **Prerequisites / Generates / Exit codes / Failures.** 5.1 / nothing / 0 /
  empty → `– none`.
- **Verify / Best practices / Related / Order.** Ids match built artifacts /
  prune abandoned experiments by deleting their parquet files / 5.1, 5.3 /
  any time.

## 5.3 `cocoon dataset describe <ds_id>`

- **Command.** `cocoon dataset describe ds_782987baf2387d02`
- **Purpose.** Full metadata: symbols, timeframe, horizon, deadband, rows,
  the complete **ordered** feature-name list, path.
- **Terminal UI.**
  ```console
  $ cocoon dataset describe ds_782987baf2387d02
  dataset ds_782987baf2387d02
    label_horizon  12
    deadband_bps   2
    feature_names  bos, choch, order_block, …
  ```
- **Exit codes / Failures.** 0 / unknown id raises (exit 1) — copy ids from
  5.2.
- **Best practices.** Diff `feature_names` between two datasets before
  comparing their models.
- **Related / Order.** 5.1, 6.1 / before training.

---

# Part 6 — Model Training, HPO & Evaluation

## 6.1 `cocoon train run`

- **Purpose.** Train + evaluate + register one model: purged walk-forward
  fold AUCs, final fit on the full dataset, content-hashed registry entry.
- **Prerequisites.** 5.1.
- **Command.**
  ```powershell
  cocoon train run --dataset ds_782987baf2387d02 --model lightgbm
  ```
- **Breakdown.** `--model` ∈ `lightgbm|xgboost|tabnet|ensemble`.
  Deterministic: retraining re-registers the same `run_id`.
- **Expected output / Terminal UI.**
  ```console
  $ cocoon train run --dataset ds_782987baf2387d02 --model lightgbm
  training complete
    run_id         lightgbm_cda10e48681a
    metrics        walk_forward_auc_mean = 0.99176
                   n_folds = 4
    artifact_hash  cda10e48681a…
  ```
- **Generates.** `data/models/<run_id>/…` artifact + registry entry + SQLite
  model-run row.
- **Exit codes.** 0; **31** on training failure.
- **Verify.** `cocoon train status <run_id>`; `cocoon model list` shows it.
- **Failures.**

  | Failure | Symptom | Resolution |
  | --- | --- | --- |
  | Windows too big for the data | `n_folds = 0`, AUC 0 | `cocoon config set training.walk_forward.train_window_days 5` (and `test_window_days 1`, `step_days 1`), retrain |
  | Suspiciously high AUC (~0.99) | not an error — it is a warning | The model is memorizing; validate on out-of-sample data before trusting anything |
- **Best practices.** Treat `walk_forward_auc_mean` as the **only** honest
  number from training; the final fit is in-sample by definition.
- **Related.** 6.2, 6.3, 7.3, 8.1.
- **Order.** After dataset build.

## 6.2 `cocoon train run --hpo` (hyperparameter optimization)

- **Purpose.** Optuna search over the model's parameter space, scored on the
  purged walk-forward folds, then final fit with the best params.
- **Prerequisites.** 6.1 works; `training.hpo.*` configured
  (`n_trials`, `timeout_sec`, `pruner`).
- **Command.**
  ```powershell
  cocoon train run --dataset ds_782987baf2387d02 --model lightgbm --hpo
  ```
- **Breakdown.** Single-model only (not `ensemble`).
- **Expected output.** Same shape as 6.1; `params` reflect the best trial.
- **Terminal UI.** As 6.1 (Optuna trial logs stream to stderr).
- **Generates / Exit codes.** As 6.1 / 0, **31** when HPO exhausts without a
  valid trial.
- **Verify.** `cocoon model inspect <run_id>` shows tuned params.
- **Failures.** `✗ TrainingError …` (exit 31) → raise `n_trials`/timeout or
  fix fold windows first (6.1).
- **Best practices.** Fix walk-forward windows **before** spending HPO
  budget; HPO on 0 folds optimizes noise.
- **Related.** 6.1, 6.3.
- **Order.** After a plain 6.1 baseline.

## 6.3 `cocoon train walk-forward`

- **Purpose.** The evaluation-focused surface: per-fold scores explicitly.
- **Command.**
  ```powershell
  cocoon train walk-forward --dataset ds_782987baf2387d02 --model lightgbm
  ```
- **Terminal UI.**
  ```console
  $ cocoon train walk-forward --dataset ds_… --model lightgbm
  walk-forward complete
    run_id       lightgbm_cda10e48681a
    fold_scores  0.985437, 0.994192, 0.99479, 0.992619
  ```
- **Prerequisites / Generates / Exit codes.** as 6.1.
- **Verify.** Fold variance is small; a wild spread means regime instability.
- **Failures.** Same `n_folds = 0` trap as 6.1 — windows are sized in *days
  assuming dense bars*; sparse caches need smaller windows.
- **Best practices.** Purge/embargo (`purge_bars`, `embargo_bars`) exist to
  stop label leakage across fold boundaries — do not zero them.
- **Related / Order.** 6.1 / model selection.

## 6.4 `cocoon train status <run_id>`

- **Command.** `cocoon train status lightgbm_cda10e48681a`
- **Purpose.** Run record from SQLite: model, dataset, stage, metrics.
- **Terminal UI.**
  ```console
  $ cocoon train status lightgbm_cda10e48681a
  run status
    stage    none
    metrics  walk_forward_auc_mean = 0.99176 …
  ```
- **Exit codes / Failures.** 0 / unknown id → `found False` (exit 0).
- **Related / Order.** 6.1, 7.x / any time.

---

# Part 7 — Model Management (Strategy Deploy/Rollback)

## 7.1 `cocoon model list`

- **Command.** `cocoon model list`
- **Purpose.** Registry inventory, deployables first
  (production → staging → none).
- **Terminal UI.**
  ```console
  $ cocoon model list
  model registry
    RUN ID                 MODEL     STAGE       DATASET ID           HASH
    xgboost_994b45ad8576   xgboost   production  ds_782987baf2387d02  994b45ad8576
  ```
- **Exit codes.** 0.
- **Verify (critical).** Exactly **one** production run among the model
  names the runtime scans (`ensemble` → the `model.ensemble` list order) —
  the live loop takes the **first** production hit in that order, so a stray
  production lightgbm silently outranks your xgboost.
- **Best practices.** Audit before every `trade start`.
- **Related / Order.** 7.3, 9.1 / before sessions.

## 7.2 `cocoon model inspect <run_id>`

- **Command.** `cocoon model inspect xgboost_994b45ad8576`
- **Purpose.** Full entry: params, metrics, artifact hash, dataset id.
- **Exit codes / Failures.** 0 / unknown → `found False`.
- **Best practices.** Record the `artifact_hash` in your session notes; it
  travels with every signal and order in the audit trail.
- **Related / Order.** 7.1 / before promotion.

## 7.3 `cocoon model promote <run_id> --stage production` (deploy)

- **Purpose.** Make a run the serving model. Production is **exclusive per
  model name**: the previous production run of that name demotes to staging
  automatically.
- **Prerequisites.** 6.x; 7.1 audit.
- **Command.**
  ```powershell
  cocoon model promote xgboost_994b45ad8576 --stage production
  ```
- **Terminal UI.**
  ```console
  $ cocoon model promote xgboost_994b45ad8576 --stage production
  model promote
    run_id  xgboost_994b45ad8576
    stage   ✓ production
  ```
- **Generates.** Registry stage change (+ DB row update).
- **Exit codes.** 0; **32** on promotion failure.
- **Verify.** `cocoon model list` — one production run in scan order (7.1).
- **Failures.** Cross-name shadowing (see 7.1 verify) → demote the other
  name: `cocoon model promote <other_run> --stage staging`.
- **Best practices.** Promote → verify → backtest (8.1) → paper (9.1) before
  live.
- **Related.** 7.4, 8.1.
- **Order.** After model selection.

## 7.4 Rollback a promotion

- **Purpose.** Return to the previous model instantly.
- **Prerequisites.** The previous run still registered (it will be — it was
  auto-demoted to staging).
- **Command.**
  ```powershell
  cocoon model promote lightgbm_d652fbfd8c79 --stage production
  ```
- **Breakdown.** Rollback **is** promotion of the previous run; the bad run
  demotes to staging by the exclusivity rule.
- **Expected output / Exit codes / Verify.** As 7.3 / 0 / `cocoon model list`.
- **Failures.** Previous run deleted → retrain: determinism reproduces the
  identical `run_id` from the same dataset (6.1).
- **Best practices.** Never `model delete` a run that was ever production
  until its replacement has survived paper trading.
- **Related / Order.** 7.3, 7.5 / incident response.

## 7.5 `cocoon model delete <run_id>`

- **Command.** `cocoon model delete lightgbm_532c40238df8`
- **Purpose.** Remove a registry entry **and its artifact files**.
- **Terminal UI.**
  ```console
  $ cocoon model delete lightgbm_532c40238df8
  model delete
    run_id   lightgbm_532c40238df8
    deleted  True
  ```
- **Exit codes / Failures.** 0 / unknown id → `deleted False` (exit 0).
- **Best practices.** Only delete `stage none` experiments (see 7.4).
- **Related / Order.** 7.1 / maintenance.

---

# Part 8 — Backtesting

## 8.1 `cocoon backtest run`

- **Purpose.** Event-driven backtest through the **same** signal → risk →
  order engines as live, with the simulated broker (fills next-bar-open ±
  slippage; SL/TP on bar range, conservative).
- **Prerequisites.** A registered model (6.x) and cached bars (3.x).
- **Command.**
  ```powershell
  cocoon backtest run --model-version xgboost_994b45ad8576 --symbols EURUSD --tf M5
  ```
- **Breakdown.** Optional `--from/--to` (UTC), `--equity` (default 10 000).
  Symbols with <300 usable bars are skipped and reported. `bt_*` id is a
  content hash — identical run, identical id.
- **Expected output / Terminal UI.**
  ```console
  $ cocoon backtest run --model-version xgboost_994b45ad8576 --symbols EURUSD --tf M5
  backtest complete
    backtest_id   bt_f134011ec58bc1be
    total_trades  907
    total_pnl     1.10354e+06
  ```
- **Generates.** `data/backtests/<bt_id>.json` (full payload).
- **Exit codes.** 0; 1 on unknown model.
- **Verify.** `cocoon backtest report <bt_id>` renders.
- **Failures.** All symbols skipped → result shows them → ingest more bars.
- **Best practices.** A backtest on the training range is in-sample noise —
  the honest read needs `--from/--to` outside the training window.
- **Related.** 8.2, 9.1.
- **Order.** After promotion, before paper.

## 8.2 `cocoon backtest report <bt_id> [--export csv|json]`

- **Purpose.** Render or export stored results.
- **Command.**
  ```powershell
  cocoon backtest report bt_f134011ec58bc1be
  cocoon backtest report bt_f134011ec58bc1be --export json > bt.json
  cocoon backtest report bt_f134011ec58bc1be --export csv  > report.csv
  ```
- **Breakdown.** No flag → header block + curated 80-col per-symbol table
  (`trades, win %, PF, pnl, dd %, sharpe, sig, rej`). `--export csv` on a
  TTY → transposed 14-metric detail table; piped → raw CSV (6 sig digits).
  `--export json` → full payload.
- **Terminal UI.**
  ```console
  $ cocoon backtest report bt_f134011ec58bc1be
  per-symbol metrics
    SYMBOL  TRADES  WIN %    PF          PNL  DD %  SHARPE   SIG   REJ
    EURUSD     907   91.8  30.5  1,103,535.4  1.14    0.61  2745  1838
  ```
- **Exit codes / Failures.** 0; unknown id → `found False` (exit 0).
- **Verify.** CSV opens with a header row; JSON parses.
- **Best practices.** Archive the JSON export with the model hash in your
  run log.
- **Related / Order.** 8.1 / analysis.

---

# Part 9 — Paper Trading

## 9.1 `cocoon trade start --mode paper`

- **Purpose.** Run the **full live pipeline without MT5**: state machine,
  reconciliation, feature window, inference, signal, risk, portfolio, order —
  against the simulated broker, replaying cached bars chronologically from an
  empty feature window (no lookahead).
- **Prerequisites.** Cached bars (3.x); a production model (7.3); no
  conflicting session.
- **Command.**
  ```powershell
  cocoon trade start --mode paper --speed 20
  cocoon trade start --mode paper --symbol EURUSD --tf M5 --speed 0 --equity 10000
  cocoon --dry-run trade start --mode paper
  ```
- **Breakdown.** `--symbol/--tf` choose the replayed series (default:
  largest cache); `--speed` bars/second (`0` = unpaced, full replay in
  ~1–2 min for 3 000 bars); `--equity` starting account;
  `--dashboard/--no-dashboard` overrides TTY autodetection. Foreground;
  Ctrl-C stops cleanly.
- **Expected output.** Live dashboard (progress bar, EQUITY/P&L/TRADES/WIN %/
  OPEN/SIGNALS/REJECTED stat row, equity sparkline, open-positions table),
  then a `paper session summary`.
- **Terminal UI.**
  ```console
  $ cocoon trade start --mode paper --speed 20
  ╭─ PAPER TRADING ────────────────────────────────────────────╮
  │ Cocoon · PAPER · EURUSD M5 · RUNNING                       │
  │ ━━━━━━━━━━╸─────────────  1,472/3,002 bars   49.0%         │
  │  EQUITY      P&L      TRADES  WIN %  OPEN  SIGNALS  REJ…   │
  ╰────────────────────────────────────────────────────────────╯
  paper session summary
    bars_replayed    3002
    trades           965
    total_pnl        +…
  ```
- **Generates.** `data/runtime/state.json` + `control.json`; orders/positions
  in SQLite; audit events (JSONL + DB); log lines in `logs/app.log`.
- **Exit codes.** 0 on clean end/stop; **21** only in live-style conflicts
  (paper auto-closes stale local paper positions instead); 1 on
  `ModelError`.
- **Verify.** `cocoon trade status` during the run; after:
  `cocoon positions list` (empty — all closed), `cocoon report daily --date
  <today>` shows the fills.
- **Failures.**

  | Failure | Error message | Resolution |
  | --- | --- | --- |
  | No production model | `✗ ModelError: No production-stage model to trade; promote one first` | 7.3 |
  | No cached bars | `✗ DataError: No cached bars to replay for paper trading` | 3.1/3.2 |
  | Wrong model picked up | (no error — wrong hash in audit) | 7.1 verify: one production run in scan order |
- **Best practices.** Replay **out-of-sample** data; in-sample profit is
  memorization (the architecture doc says this explicitly). Watch REJECTED —
  a healthy risk engine rejects.
- **Related.** 9.2–9.5, 7.1.
- **Order.** After backtest, before live.

## 9.2 `cocoon trade status [--watch]`

- **Purpose.** Session panel: mode, profile, state, open vs. limit,
  unrealized P&L, daily-loss budget, positions, bridge, model.
- **Prerequisites.** A session ran/running (state file exists).
- **Command.**
  ```powershell
  cocoon trade status
  cocoon trade status --watch          # 2 Hz live panel
  cocoon --output json trade status    # {"state": …, "mode": …, "started_ms": …}
  ```
- **Terminal UI.**
  ```console
  $ cocoon trade status
  ╭─ LIVE ─────────────────────────────────────────╮
  │ Cocoon · PAPER · profile default · RUNNING     │
  │ open 1/5 · unrealized +14.20 · daily loss …    │
  ╰────────────────────────────────────────────────╯
  ```
- **Generates / Exit codes.** Nothing / 0.
- **Verify.** State matches expectation (RUNNING / SAFE_HALT / TERMINATED).
- **Failures.** Stale `state.json` after a crash → shows an old state → 15.2.
- **Best practices.** Works from **any** terminal on the host — control is
  file-based, no daemon.
- **Related / Order.** 9.3 / during sessions.

## 9.3 `cocoon trade halt|resume|stop`

- **Purpose.** Control a running loop from another terminal via the control
  file: SAFE_HALT (no new trades; data keeps ingesting; replay pauses) →
  resume (re-reconcile, back to RUNNING) → stop (clean shutdown).
- **Prerequisites.** A running session.
- **Command.**
  ```powershell
  cocoon trade halt --yes
  cocoon trade resume
  cocoon trade stop
  ```
- **Breakdown.** `halt` prompts `Halt trading (SAFE_HALT)?` unless `--yes`.
- **Terminal UI.**
  ```console
  $ cocoon trade halt --yes
  trade halt
    signal  halt
    status  ✓ sent
  ```
- **Generates.** `data/runtime/control.json`.
- **Exit codes.** 0 (send is fire-and-forget; the loop applies it within one
  heartbeat interval).
- **Verify.** `cocoon trade status` shows SAFE_HALT / RUNNING / TERMINATED.
- **Failures.** No loop running → signal sent but nothing consumes it →
  harmless; delete the control file if it confuses the next start (15.2).
- **Best practices.** Halt (not stop) for news events — the window stays
  warm.
- **Related / Order.** 9.2 / operations.

## 9.4 `cocoon positions list`

- **Command.** `cocoon positions list`
- **Purpose.** Open positions from SQLite: ticket, symbol, dir, lots, entry,
  pnl, origin (`internal` ours / `external` imported at reconciliation —
  never auto-closed).
- **Terminal UI.**
  ```console
  $ cocoon positions list
  open positions  – none
  ```
- **Exit codes / Failures.** 0 / none.
- **Verify.** Empty after a clean paper session (everything force-closed).
- **Related / Order.** 9.1, 10.3 / during/after sessions.

## 9.5 Session P&L and order review

- **Purpose.** Post-session review from the audit mirror.
- **Command.**
  ```powershell
  cocoon report daily --date 2026-07-26
  cocoon report export --format csv --out .\out\audit.csv
  ```
- **Expected output.** The day's ORDER payloads (≤100 rows); full export to
  file (≤5 000 events).
- **Terminal UI.**
  ```console
  $ cocoon report export --format csv --out .\out\audit.csv
  report export
    events  3011
    format  csv
    path    out\audit.csv
  ```
- **Exit codes.** 0; **1** on unknown `--format`.
- **Failures.** `report session <id>` always returns 0 events — known gap
  (audit payloads carry no session id yet).
- **Best practices.** Export CSV per session and archive with the config
  snapshot (2.3) and model hash (7.2).
- **Related / Order.** 11.x / after every session.

---

# Part 10 — Live Trading & the Messaging Bridge

**Prerequisite reality (from `ARCHITECTURE.md`):** live mode needs the MT5
Expert Advisor speaking the **msgpack** protocol. The shipped
`mql5/CocoonEA.mq5` is a JSON-speaking skeleton — port it before expecting
anything below to fill a real order. Everything else (ports, handshake,
control) is operational today and fails exactly as documented.

## 10.1 Verify bridge ports are reachable

- **Purpose.** Confirm the ZMQ endpoints (REQ 5555, PUB 5556 by default —
  `mt5.zmq_req_port` / `mt5.zmq_pub_port`) are open on the EA host.
- **Prerequisites.** EA attached to a chart with matching ports.
- **Command.**
  ```powershell
  Test-NetConnection -ComputerName 127.0.0.1 -Port 5555
  ```
  ```bash
  nc -zv 127.0.0.1 5555
  ```
- **Expected output.** `TcpTestSucceeded : True` / `succeeded!`.
- **Terminal UI.**
  ```console
  $ Test-NetConnection 127.0.0.1 -Port 5555
  TcpTestSucceeded : True
  ```
- **Generates / Exit codes.** Nothing / 0 reachable, 1 not.
- **Verify.** Both ports pass.
- **Failures.** `False` → EA not attached, wrong ports, firewall → align
  `cocoon config show` (mt5 section) with the EA inputs.
- **Best practices.** Check before every live start; a passed port test with
  a failed HELLO (below) means the EA is listening but not speaking the
  protocol.
- **Related / Order.** 10.2 / first live step.

## 10.2 `cocoon trade start --mode live`

- **Purpose.** The real loop: ZMQ HELLO handshake → reconcile broker vs.
  SQLite → engines around the production model → bar-driven trading with
  heartbeat supervision (missed beats → SAFE_HALT).
- **Prerequisites.** 10.1; msgpack-capable EA; 7.1 verified; demo account
  first.
- **Command.**
  ```powershell
  cocoon --profile prod trade start --mode live
  cocoon --dry-run trade start --mode live
  ```
- **Expected output.** State transitions to RUNNING (JSON logs on stderr),
  then bar-driven activity; control via 9.2/9.3.
- **Terminal UI (without a compatible EA — the real current behaviour).**
  ```console
  $ cocoon trade start --mode live
  ✗ MT5ConnectTimeoutError: MT5 EA did not ACK HELLO within timeout
    context: {"timeout_ms": 5000, "error": "Resource temporarily unavailable"}
  ```
- **Generates.** Same runtime/DB/audit artifacts as 9.1.
- **Exit codes.** 0 clean stop; **20** HELLO timeout; **21** reconciliation
  conflict; **50** protocol version mismatch
  (`Bridge protocol version mismatch between Python and EA`); **41** order
  retry exhaustion mid-session; 130 SIGINT.
- **Verify.** `cocoon trade status` RUNNING; `cocoon positions list` after
  fills.
- **Failures.**

  | Exit | Error | Resolution |
  | --- | --- | --- |
  | 20 | `MT5 EA did not ACK HELLO within timeout` | 10.1; EA attached & ports match; EA speaks msgpack |
  | 21 | `Unresolved reconciliation conflict requires manual resolution` | Inspect context tickets; close/repair in DB or at broker; restart |
  | 50 | protocol mismatch | Rebuild EA against `bridge/protocol.py` `PROTOCOL_VERSION = 1` |
- **Best practices.** Demo account until the EA port + risk/order code have a
  test suite (the repo says this about itself); keep 9.3 controls one
  terminal away.
- **Related / Order.** 10.1, 10.3, 9.2–9.3 / after paper sign-off.

## 10.3 `cocoon positions close <ticket> [--partial LOTS]`

- **Purpose.** Manually close (or partially close) a broker position through
  the bridge and mark it closed in SQLite.
- **Prerequisites.** Reachable EA (10.1).
- **Command.**
  ```powershell
  cocoon positions close 12345
  cocoon --dry-run positions close 12345 --partial 0.30
  ```
- **Terminal UI.**
  ```console
  $ cocoon --dry-run positions close 12345 --partial 0.30
  positions close
    dry_run  True
    action   close
    ticket   12345
    partial  0.3
  ```
- **Generates.** DB position update on success.
- **Exit codes.** 0; **20** without a reachable EA.
- **Verify.** `cocoon positions list` no longer shows the ticket.
- **Failures.** Exit 20 → 10.1/10.2 checklist.
- **Best practices.** Prefer `trade halt` first, then close, so the loop
  doesn't immediately re-enter.
- **Related / Order.** 9.4 / manual intervention.

---

# Part 11 — Monitoring, Logging & Observability

## 11.1 Tail the application log

- **Purpose.** Live view of the structured JSON log (also where console logs
  divert while a dashboard owns the terminal).
- **Command.**
  ```powershell
  Get-Content .\logs\app.log -Wait -Tail 50
  ```
  ```bash
  tail -f -n 50 logs/app.log
  ```
- **Expected output.** JSON lines (`state_transition`, `signal_generated`,
  `risk_rejected`, `order_idempotent_hit`, `paper_replay_complete`, …).
- **Terminal UI.**
  ```console
  $ tail -f logs/app.log
  {"event": "risk_rejected", "check": "daily_loss_check", …}
  ```
- **Generates / Exit codes.** Nothing / 0 (Ctrl-C to leave).
- **Verify.** Events appear while a session runs.
- **Failures.** Missing file → no session has logged yet.
- **Best practices.** Rotation is automatic (`logging.rotate_max_mb`,
  `rotate_backups`) — never truncate the live file by hand.
- **Related.** 11.2, 9.1.
- **Order.** Alongside any session.

## 11.2 Tail the audit trail

- **Purpose.** The forensic stream — every ORDER/SIGNAL/STATE_TRANSITION/
  ERROR with a monotonic `seq`.
- **Command.**
  ```powershell
  Get-Content .\logs\audit.jsonl -Wait -Tail 20
  ```
  ```bash
  tail -f -n 20 logs/audit.jsonl
  ```
- **Expected output.** Ordered JSONL records; `seq` strictly increasing.
- **Exit codes.** 0.
- **Verify.** `seq` never repeats or decreases across restarts.
- **Failures.** Gap between JSONL and DB counts → the DB mirror is
  best-effort by design; JSONL is authoritative.
- **Best practices.** Back this file up (12.4); it is the compliance
  artifact.
- **Related / Order.** 9.5, 12.4 / always-on.

## 11.3 Live dashboards

- **Purpose.** Human monitoring surfaces.
- **Command.**
  ```powershell
  cocoon trade status --watch      # 2 Hz session panel
  # the paper dashboard is built into 9.1 (5 Hz)
  ```
- **Expected output.** Rounded state-coloured panels (cyan RUNNING, yellow
  SAFE_HALT, dim TERMINATED).
- **Exit codes.** 0 (Ctrl-C exits the watch).
- **Failures.** Piped output prints a single frame — by design.
- **Best practices.** One terminal for the session, one for `--watch`, one
  for logs (11.1).
- **Related / Order.** 9.2 / during sessions.

## 11.4 Machine-readable monitoring (scripting)

- **Purpose.** Poll state and results from scripts — every command has a
  JSON twin with identical keys.
- **Command.**
  ```powershell
  (cocoon --output json trade status | ConvertFrom-Json).state
  ```
  ```bash
  cocoon --output json trade status | jq -r .state
  ```
- **Expected output.** `RUNNING` / `SAFE_HALT` / `TERMINATED`.
- **Terminal UI.**
  ```console
  $ cocoon --output json trade status | jq -r .state
  RUNNING
  ```
- **Exit codes.** 0.
- **Verify.** Matches `trade status` panel.
- **Failures.** Parsing table output instead of `--output json` → always use
  the JSON twin; table layout is not a contract.
- **Best practices.** JSON keys are the stable scripting contract
  (`TERMINAL_V2.md` §11).
- **Related / Order.** 9.2 / automation.

---

# Part 12 — Database, Backup, Restore & Migration

## 12.1 SQLite integrity check

- **Purpose.** Validate `data/cocoon.db` (orders, positions, model runs,
  audit mirror).
- **Prerequisites.** No running session (or accept read-during-write).
- **Command.**
  ```powershell
  python -m sqlite3 data\cocoon.db "PRAGMA integrity_check;"
  ```
  ```bash
  python -m sqlite3 data/cocoon.db "PRAGMA integrity_check;"
  ```
- **Breakdown.** Python 3.12's stdlib sqlite3 CLI: file then SQL.
- **Expected output.** `ok`.
- **Terminal UI.**
  ```console
  $ python -m sqlite3 data/cocoon.db "PRAGMA integrity_check;"
  ok
  ```
- **Generates / Exit codes.** Nothing / 0; non-`ok` output = corruption.
- **Verify.** Output is exactly `ok`.
- **Failures.** Corruption → restore from backup (12.3); the audit JSONL
  remains the authoritative order history.
- **Best practices.** Run before backups and after crashes.
- **Related / Order.** 12.2 / maintenance.

## 12.2 Back up the database

- **Purpose.** Point-in-time copy of the operational DB.
- **Prerequisites.** Stop the session first (`cocoon trade stop`) — SQLite
  files must not be copied mid-write.
- **Command.**
  ```powershell
  cocoon trade stop
  Copy-Item data\cocoon.db "backups\cocoon-$(Get-Date -Format yyyyMMdd-HHmmss).db"
  ```
  ```bash
  cocoon trade stop
  mkdir -p backups && cp data/cocoon.db "backups/cocoon-$(date +%Y%m%d-%H%M%S).db"
  ```
- **Expected output.** Silent copy.
- **Generates.** Timestamped file under `backups/`.
- **Exit codes.** 0.
- **Verify.** `python -m sqlite3 backups\cocoon-….db "PRAGMA integrity_check;"` → `ok`.
- **Failures.** Locked file → a session is still running → stop it.
- **Best practices.** Pair every DB backup with the matching
  `logs/audit.jsonl` copy — same truth, two forms.
- **Related / Order.** 12.1, 12.4 / before upgrades & regularly.

## 12.3 Restore the database

- **Purpose.** Roll the operational DB back to a backup.
- **Prerequisites.** Session stopped; backup verified (12.2).
- **Command.**
  ```powershell
  Copy-Item backups\cocoon-20260726-120000.db data\cocoon.db -Force
  ```
  ```bash
  cp backups/cocoon-20260726-120000.db data/cocoon.db
  ```
- **Expected output.** Silent.
- **Exit codes.** 0.
- **Verify.** 12.1 → `ok`; `cocoon positions list` / `cocoon model list`
  show expected state.
- **Failures.** Positions diverge from the broker after restore → the next
  live start reconciles (broker-only → imported `external`; local-only →
  conflict exit 21 you resolve deliberately).
- **Best practices.** Restore + immediately reconcile; never trade between.
- **Related / Order.** 12.2, 10.2 / recovery.

## 12.4 Full workspace backup / restore

- **Purpose.** Everything needed to reproduce the deployment: config,
  data artifacts, logs, environment snapshot.
- **Prerequisites.** Session stopped.
- **Command.**
  ```powershell
  Compress-Archive -Path config, data, logs, pip-freeze.txt -DestinationPath "backups\cocoon-full-$(Get-Date -Format yyyyMMdd).zip"
  Expand-Archive backups\cocoon-full-20260726.zip -DestinationPath .   # restore
  ```
  ```bash
  tar czf "backups/cocoon-full-$(date +%Y%m%d).tgz" config data logs pip-freeze.txt
  tar xzf backups/cocoon-full-20260726.tgz                              # restore
  ```
- **Expected output.** Archive created/extracted.
- **Generates.** One archive containing config profiles, parquet cache,
  datasets, model artifacts, backtests, runtime files, DB, both logs.
- **Exit codes.** 0.
- **Verify.** List the archive (`tar tzf …` / `Expand-Archive -WhatIf`);
  after restore run 2.2 and 12.1.
- **Failures.** Archive misses `data/models` → models are reproducible from
  datasets anyway (determinism), but back them up to skip retraining.
- **Best practices.** Code is in git; **this archive is state** — schedule
  it around trading hours.
- **Related / Order.** 1.9, 12.2 / regularly + before upgrades.

## 12.5 Migration & schema notes

- **Purpose.** Moving hosts / upgrading.
- **Command (move to a new host).**
  ```powershell
  # old host: 12.4 backup → copy archive
  # new host: Parts 1–2, then:
  Expand-Archive cocoon-full-20260726.zip -DestinationPath .
  cocoon config validate ; python -m sqlite3 data\cocoon.db "PRAGMA integrity_check;"
  ```
- **Breakdown.** There is **no separate migration tool**: SQLAlchemy creates
  missing tables on first use; datasets/models/backtests are content-hashed
  files that move as-is; determinism lets you rebuild any artifact from the
  cache if in doubt.
- **Exit codes.** Per constituent commands.
- **Verify.** `cocoon model list`, `cocoon dataset list`, `cocoon data
  status` all show the migrated state.
- **Failures.** Schema drift after a code upgrade adds columns → recreate
  the DB (delete `data/cocoon.db`) and let reconciliation + deterministic
  rebuilds repopulate; the audit JSONL preserves history.
- **Best practices.** Migrate during a halt; verify before resuming.
- **Related / Order.** 12.4, 14.5 / host changes.

---

# Part 13 — Development, Testing, Code Quality & CI/CD

## 13.1 Compile gate (the CI gate, locally)

- **Purpose.** Every module must compile — the repo's fast dependency-free
  check, identical to CI.
- **Command.**
  ```powershell
  python -m compileall -q src
  ```
- **Expected output.** Silent on success.
- **Terminal UI.**
  ```console
  $ python -m compileall -q src ; echo $?
  0
  ```
- **Generates.** `__pycache__` bytecode.
- **Exit codes.** 0; 1 with syntax errors (file:line printed).
- **Verify.** Exit 0.
- **Failures.** Syntax error listing → fix the named file.
- **Best practices.** Run before every commit.
- **Related.** 13.4.
- **Order.** Every change.

## 13.2 Lint (advisory, matches CI)

- **Purpose.** Style/bug lint; CI runs it as non-blocking.
- **Command.**
  ```powershell
  pip install ruff
  ruff check src
  ```
- **Expected output.** `All checks passed!` or a findings list.
- **Exit codes.** 0 clean; 1 findings (CI tolerates via `|| true`).
- **Verify.** Rerun after fixes.
- **Failures.** Findings are advisories — fix or consciously ignore.
- **Best practices.** Keep new code clean even though the gate is advisory.
- **Related / Order.** 13.4 / before PRs.

## 13.3 Functional smoke (CI parity)

- **Purpose.** The exact functional checks CI runs after install.
- **Command.**
  ```powershell
  cocoon --help ; cocoon init ; cocoon config validate
  ```
- **Expected output.** Help text; `created 0` (or scaffold); `valid ✓ True`.
- **Exit codes.** All 0.
- **Verify.** `$LASTEXITCODE`/`$?` chain is 0.
- **Failures.** Any non-zero → your change broke startup — fix before push.
- **Best practices.** This trio is the minimum bar for any PR.
- **Related / Order.** 13.4 / before push.

## 13.4 CI pipeline (GitHub Actions)

- **Purpose.** `.github/workflows/ci.yml` — on push/PR to `main`: matrix
  Python 3.11 + 3.12 → `compileall` → `pip install -e .` → `cocoon --help`
  → `cocoon init` + `config validate`; plus advisory ruff.
- **Command (trigger).**
  ```powershell
  git push origin <branch>          # or open a PR to main
  gh run watch                      # follow the run (GitHub CLI)
  ```
- **Expected output.** Green `Compile & import smoke` job.
- **Exit codes.** Per git/gh.
- **Verify.** `gh run list --limit 1` shows `completed success`.
- **Failures.** Matrix failure on one Python → reproduce locally with that
  interpreter (1.2–1.6).
- **Best practices.** Keep 13.1–13.3 green locally so CI never surprises you.
- **Related / Order.** 13.1–13.3 / every push.

## 13.5 Test suite — honest status

- **There is no test suite in this repository.** It is the roadmap's
  highest-priority item. The executable verification that exists today is:
  13.1–13.3, the deterministic-ID re-run checks (5.1, 6.1, 8.1 — same
  inputs must yield the same ids), and the machine-verified command outputs
  in `TERMINAL.md`. When tests land, they will run under `pytest` — until
  then this document lists no fictional test commands.

---

# Part 14 — Maintenance, Cleanup & Upgrades

## 14.1 Prune experiment artifacts

- **Purpose.** Remove abandoned datasets/backtests and unpromoted models.
- **Prerequisites.** Session stopped; 7.1 reviewed.
- **Command.**
  ```powershell
  cocoon model delete lightgbm_532c40238df8            # stage none only
  Remove-Item data\backtests\bt_<old>.json
  Remove-Item data\datasets\ds_<old>.parquet
  ```
  ```bash
  cocoon model delete lightgbm_532c40238df8
  rm data/backtests/bt_<old>.json data/datasets/ds_<old>.parquet
  ```
- **Expected output.** `deleted True`; silent removals.
- **Exit codes.** 0.
- **Verify.** `cocoon model list` / `cocoon dataset list`.
- **Failures.** Deleting a production/staging model → don't (7.4 needs it);
  determinism can rebuild, but retraining costs time.
- **Best practices.** Everything deleted here is reproducible from the cache
  + config (determinism) — the cache and audit trail are the only
  irreplaceable state.
- **Related / Order.** 7.5, 3.5 / periodic.

## 14.2 Log housekeeping

- **Purpose.** Rotation is automatic; prune old rotated files only.
- **Command.**
  ```powershell
  Get-ChildItem logs\app.log.* | Remove-Item
  ```
  ```bash
  rm -f logs/app.log.*
  ```
- **Exit codes.** 0.
- **Verify.** `logs/app.log` (live) untouched.
- **Failures / Best practices.** Never delete `logs/audit.jsonl` — archive it
  (12.4); it is the compliance record.
- **Related / Order.** 11.2 / periodic.

## 14.3 Reset runtime state (after crashes)

- **Purpose.** Clear stale session files so `trade status` and the next
  start see clean state.
- **Prerequisites.** Confirm nothing is running.
- **Command.**
  ```powershell
  Remove-Item data\runtime\state.json, data\runtime\control.json -ErrorAction SilentlyContinue
  ```
  ```bash
  rm -f data/runtime/state.json data/runtime/control.json
  ```
- **Expected output.** Silent.
- **Exit codes.** 0.
- **Verify.** `cocoon trade status` shows empty/UNKNOWN state.
- **Failures.** Removing while a session runs → it rewrites them each
  heartbeat — harmless but pointless.
- **Best practices.** Part of the crash-recovery sequence (15.2).
- **Related / Order.** 15.2 / recovery.

## 14.4 Upgrade Cocoon

- **Purpose.** Pull new code and re-resolve dependencies.
- **Prerequisites.** 12.4 backup; session stopped; 1.9 snapshot.
- **Command.**
  ```powershell
  cocoon trade stop
  git pull --ff-only
  pip install -e .
  cocoon config validate
  python -m compileall -q src
  ```
- **Expected output.** Fast-forward pull; reinstall; `valid ✓ True`; silent
  compile.
- **Exit codes.** All 0.
- **Verify.** 13.3 trio; then a paper session (9.1) before any live start.
- **Failures.** `config validate` exit 10 after upgrade → a config key
  changed shape → fix per the pydantic message; DB schema drift → 12.5.
- **Best practices.** Upgrade → validate → paper → live, in that order,
  always.
- **Related / Order.** 12.4, 13.x, 9.1 / releases.

## 14.5 Clean reinstall

- **Purpose.** Nuke and rebuild the environment (dependency corruption).
- **Command.**
  ```powershell
  deactivate ; Remove-Item -Recurse -Force .venv
  python -m venv .venv ; .\.venv\Scripts\Activate.ps1
  python -m pip install --upgrade pip ; pip install -e .
  ```
  ```bash
  deactivate; rm -rf .venv
  python3 -m venv .venv && source .venv/bin/activate
  python -m pip install --upgrade pip && pip install -e .
  ```
- **Expected output.** Fresh install ending `Successfully installed cocoon-0.1.0 …`.
- **Exit codes.** 0.
- **Verify.** 1.7 + 13.3.
- **Failures.** As Part 1.
- **Best practices.** Workspace state (`config/ data/ logs/`) is untouched by
  a venv rebuild — code and state are deliberately separate.
- **Related / Order.** Part 1 / when 1.9 reports conflicts.

---

# Part 15 — Diagnostics, Recovery & Troubleshooting

## 15.1 Read the exit code

- **Purpose.** Every failure maps to the catalogue (top of this file); the
  code alone routes you.
- **Command.**
  ```powershell
  cocoon <command> ; $LASTEXITCODE
  ```
  ```bash
  cocoon <command>; echo $?
  ```
- **Routing.** 10 → fix config (2.2) · 20 → bridge checklist (10.1/10.2) ·
  21 → reconciliation (15.3) · 30/31/32 → data/training/promotion inputs ·
  41 → broker rejected repeatedly, inspect audit ORDER records (11.2) ·
  50 → EA protocol version · 60 → plugin (4.3) · 130 → clean Ctrl-C, not an
  error.
- **Exit codes.** N/A (this *is* the exit-code step).
- **Best practices.** Scripts must branch on codes, never parse table text.

## 15.2 Crash recovery sequence

- **Purpose.** Recover after a killed session/host crash.
- **Command.**
  ```powershell
  cocoon trade status                                   # 1. what does state claim?
  Remove-Item data\runtime\*.json                       # 2. clear stale state (14.3)
  python -m sqlite3 data\cocoon.db "PRAGMA integrity_check;"   # 3. DB ok?
  cocoon positions list                                 # 4. local open positions?
  cocoon trade start --mode paper --speed 20            # 5. restart (paper auto-closes stale paper positions; live reconciles)
  ```
- **Expected output.** Steps 3 `ok`; step 5 reaches RUNNING.
- **Exit codes.** Per step; step 5 exit 21 → 15.3.
- **Verify.** `cocoon trade status` RUNNING; audit `seq` continued
  monotonically (11.2).
- **Failures.** DB not `ok` → 12.3 restore, then rerun sequence.
- **Best practices.** Never skip step 4 — know what the system thinks is
  open before reconnecting anything.

## 15.3 Reconciliation conflict (exit 21)

- **Purpose.** Resolve `Unresolved reconciliation conflict requires manual
  resolution`.
- **Meaning.** SQLite has an open position the broker doesn't recognize
  (`local_position_missing_at_broker`, tickets in the error context).
- **Command.**
  ```powershell
  cocoon positions list                     # identify the ticket(s)
  # if genuinely closed at the broker, clear the local record:
  python -m sqlite3 data\cocoon.db "UPDATE positions SET is_open = 0 WHERE broker_ticket_id = <ticket>;"
  cocoon trade start --mode live            # reconcile again
  ```
- **Expected output.** Second start passes STATE_RECONCILING.
- **Exit codes.** 0 after resolution.
- **Verify.** `cocoon positions list` matches broker reality.
- **Failures.** Broker-side positions unknown locally are **not** conflicts —
  they import as `origin=external` automatically and are never auto-closed.
- **Best practices.** Resolve deliberately; the conflict exists to stop you
  trading on a state mismatch. Paper mode never needs this (auto-close).

## 15.4 Walk-forward yields 0 folds

- **Symptom.** `n_folds = 0`, `walk_forward_auc_mean = 0` after training.
- **Cause.** Day-based windows assume dense bars; the cache is sparse.
- **Command.**
  ```powershell
  cocoon config set training.walk_forward.train_window_days 5
  cocoon config set training.walk_forward.test_window_days 1
  cocoon config set training.walk_forward.step_days 1
  cocoon train run --dataset <ds_id> --model lightgbm
  ```
- **Verify.** `n_folds ≥ 3` in the training output.
- **Best practices.** Scale windows to actual bar density, not calendar
  intuition.

## 15.5 Terminal glyphs corrupt (Windows mojibake)

- **Symptom.** `Γ£ô` instead of `✓`, broken box characters.
- **Command.**
  ```powershell
  $env:PYTHONIOENCODING = "utf-8" ; chcp 65001
  ```
- **Verify.** `cocoon config validate` renders `✓`.
- **Best practices.** Windows Terminal + UTF-8 code page; `TERM=dumb`
  switches Cocoon to ASCII glyph fallbacks by design.

## 15.6 Verbose debugging run

- **Purpose.** Maximum log detail for a misbehaving command.
- **Command.**
  ```powershell
  cocoon --log-level DEBUG trade start --mode paper --speed 20 2> debug.log
  ```
- **Expected output.** DEBUG-level JSON (including `signal_below_threshold`,
  portfolio resync events) captured to `debug.log`, dashboard unaffected.
- **Verify.** `Select-String debug.log -Pattern '"level": "debug"'` matches.
- **Best practices.** DEBUG is noisy — scope it to one session, attach the
  log to bug reports (`.github/ISSUE_TEMPLATE`).

## 15.7 Import/installation self-diagnosis

- **Command.**
  ```powershell
  python -c "import cocoon; print(cocoon.__file__)"
  python -c "from cocoon.cli.main import entrypoint; print('entrypoint ok')"
  ```
- **Expected output.** Path inside the repo's `src/` (editable install);
  `entrypoint ok`.
- **Failures.** Path in site-packages of another env → wrong venv active
  (1.4); ImportError with `LayeringViolationError` → a modified module broke
  the import-layering rule — undo the upward import.
- **Related.** 1.6, 13.1.

---

# Part 16 — Deployment, Docker, Kubernetes & External Services (honest status)

Per the "no placeholders, no assumptions" rule, the following are **stated
gaps, not commands**, because the repository ships no implementation for
them:

| Area | Status in this repository | The real operational answer today |
| --- | --- | --- |
| Docker | No `Dockerfile` / `docker-compose.yml` | Deploy = Parts 1–2 on the target host (venv + editable install) |
| Kubernetes | No manifests/Helm charts | Single-host by design: the loop is one foreground process with file-based control (§4 of `ARCHITECTURE.md`); MT5 EA requires a Windows host anyway |
| CD (deploy automation) | None; CI is verification-only (13.4) | 14.4 upgrade sequence is the release procedure |
| External message broker | None required — ZMQ is embedded (bridge L4), no server to provision beyond the two ports (10.1) | — |
| External database | None — SQLite file, no server | 12.x covers backup/restore/migration |
| Secrets manager | None integrated | Env vars / `.env` only; a secret in a config file exits 11 by design (1.10) |

When any of these gains a real implementation, its commands belong in this
file with the same 15-field treatment — until then, absence is documented
instead of faked.
