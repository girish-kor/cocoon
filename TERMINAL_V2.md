# Cocoon Terminal UI/UX Standard — v2.1 (modern minimal theme)

The definitive specification for how every `cocoon` command presents results in
the terminal. Where `TERMINAL.md` shows captured examples, this document is the
**contract**: the design language, every rule the CLI follows, and — per
command — the expected result rendered to this standard.

v2.1 restyles the presentation to the common modern CLI theme established by
`gh`, `docker`, `kubectl`, `npm`, and `cargo`: borderless tables, dim uppercase
headers, aligned key columns, outcome glyphs, rounded accent panels, and the
standard colour-control environment contract. **Data contracts are unchanged
from v2**: titles, key names, JSON output, status vocabulary, and exit codes
are byte-identical. The theme is implemented centrally — `output_obj` /
`output_rows` / `_emit_error` in `src/cocoon/cli/__init__.py` and the two
`src/cocoon/cli/dashboard/` views — so no command code carries styling.

---

## 1. Principles

1. **Results are structured output. Always.** A command's outcome renders as
   an aligned table or key-value block — never free prose, never bare
   `print`. No banners, greetings, hints, or decoration around a result.
2. **stdout is for results only.** Anything a human or script consumes as
   *the answer* goes to stdout. Diagnostics never contaminate it.
3. **Every surface has a machine twin.** The global `--output json` flag turns
   any result into raw JSON with identical keys and zero locale formatting.
4. **Negative outcomes are results, not errors.** "Not found", "already
   exists", "0 removed" render as normal results with exit code 0. Errors are
   reserved for failures, go to stderr, and carry a catalogued exit code.
5. **Preview before mutation.** Every mutating command honours global
   `--dry-run` and renders what *would* happen.
6. **Determinism shows.** Deterministic operations (dataset build, training)
   produce identical IDs on identical inputs; re-runs are idempotent
   successes, not conflicts.
7. **Degrade gracefully.** Colour, glyphs, and live rendering are progressive
   enhancements — every result survives `NO_COLOR`, a dumb terminal, and a
   pipe with nothing lost but style.

---

## 2. Design language

### 2.1 Colour tokens (ANSI-16 only, for universal terminal support)

Structural tokens:

| Token | ANSI | Used for |
| ----- | ---- | -------- |
| `title` | bold cyan | Block titles |
| `key` | dim cyan | S1 key columns, S2/table headers |
| `success` | green | Affirmative outcomes, profit, fills, BUY, ✓ |
| `error` | red | Losses, failures, SELL, ✗ |
| `warning` | yellow | `SAFE_HALT`, cautions, external origin, staging |
| `accent` | cyan | Active state, panel borders while running, progress text |
| `muted` | dim | Captions, neutral outcomes, empty states, rejected counts |
| `emphasis` | bold | Names the user came for (symbols, models, profiles) |

Semantic value colours (applied centrally by key/type — colour always means
the same thing, never decoration):

| Value | Colour |
| ----- | ------ |
| Numbers (int/float) | yellow (`EQUITY` bold yellow on dashboards) |
| PnL-like keys (`pnl`, `total_pnl`, `unrealized_pnl`, `expectancy`) | green ≥ 0, red < 0 — overrides the number rule |
| Identifiers (`*_id`, `hash`, `idempotency_key`, `ticket`) | magenta |
| Paths (`path`, `paths`, `root`, `file`) | blue |
| `BUY` / `SELL` | green / red |
| Order status lifecycle | `FILLED`/`ACKNOWLEDGED`/`PARTIALLY_FILLED` green; `*REJECT*`/`*FAILED*`/`*TIMEOUT*` red |
| `stage` | `production` green · `staging` yellow · `none` dim |
| `origin` | `internal` dim · `external` yellow |
| Booleans | `True` green · `False` dim |
| `WIN %` (dashboard) | green ≥ 50 · red < 50 |

No 256-colour or truecolour values anywhere — the theme must survive every
terminal palette. JSON mode carries none of this.

Colour controls (standard environment contract):

| Control | Behaviour |
| ------- | --------- |
| stdout not a TTY | Colour off, glyphs keep UTF-8, live surfaces print final frame only |
| `NO_COLOR` set | Colour off (https://no-color.org) |
| `CLICOLOR_FORCE=1` / `FORCE_COLOR` | Colour on even when piped |
| `TERM=dumb` | Colour off **and** ASCII fallback glyphs |

### 2.2 Glyphs (with ASCII fallback under `TERM=dumb`)

| Glyph | Fallback | Meaning |
| ----- | -------- | ------- |
| `✓` | `OK` | Affirmative outcome (created, deleted, valid, sent, filled) |
| `–` | `-` | Neutral / no-op outcome (not found, already exists, none) |
| `✗` | `X` | Failure — stderr error blocks only, never in a result |
| `▸` | `>` | Progress/current-item marker |
| `━ ╸ ─` | `= > -` | Progress bar: done / head / remaining |
| `▁▂▃▄▅▆▇█` | omitted | Sparkline ramp |
| `·` | `.` | Caption separator |

Information is never glyph-only or colour-only: every glyph rides next to a
§6.7 vocabulary word, every coloured number is signed.

### 2.3 Tables — borderless, aligned, quiet

Box-drawing grids are reserved for panels (§9–§10). Data tables use the
`gh`/`docker` convention:

- **Title**: bold lowercase line, flush left, directly above the block.
- **Row tables (S2)**: dim UPPERCASE headers (key name uppercased,
  underscores → spaces), columns separated by a 2-space gutter, rows indented
  two spaces, no rules or borders. Numeric columns right-aligned.
- **Key-value blocks (S1)**: two aligned columns indented two spaces — dim
  key, plain value — no borders, no header row.
- **Empty state**: title line plus a dim `– none` marker on one line.

```
datasets                                  ← bold title
  DATASET ID           SYMBOLS  TF  ROWS  ← dim uppercase header
  ds_782987baf2387d02  EURUSD   M5  2,990
```

### 2.4 Panels — rounded, accent-bordered

Live surfaces (S3/S4) draw a rounded panel `╭─ TITLE ─╮ … ╰─╯` whose border
colour tracks the state token. Panels are the only boxed element in the theme.

### 2.5 Spacing

One blank line between a command and unrelated following output; none between
a title and its block; two-space indent for all data lines; no trailing
whitespace. Tables target an 80-column width; wide detail moves to transposed
tables or exports rather than wrapping.

---

## 3. Output streams

| Stream               | Contents                                                                      |
| -------------------- | ----------------------------------------------------------------------------- |
| **stdout**           | Result blocks / JSON / raw CSV exports. Pipe-safe.                            |
| **stderr**           | Structured JSON log lines (structlog) and error blocks.                       |
| `logs/app.log`       | Same structured logs, rotating file (`logging.rotate_max_mb`, `rotate_backups`). |
| `logs/audit.jsonl`   | Append-only audit trail (ORDER / SIGNAL / STATE_TRANSITION / CONFIG_SNAPSHOT / ERROR records with monotonic `seq`). |
| SQLite `audit_events`| DB mirror of the audit trail (same `seq` series) — what `cocoon report` queries. Best-effort: a failed mirror write logs a warning, never breaks the loop. |

While a live dashboard owns the terminal, the stderr handler is dropped
(`quiet_console_logging()`); logs continue to the file and audit sinks.

---

## 4. Global presentation flags

| Flag              | Default   | Effect on presentation                                          |
| ----------------- | --------- | --------------------------------------------------------------- |
| `--output`        | `table`   | `table` renders themed blocks; `json` prints raw JSON to stdout. |
| `--dry-run`       | off       | Mutating commands render a preview block and exit 0.             |
| `--yes`           | off       | Skips confirmation prompts (currently only `trade halt`).        |
| `--profile`       | `default` | Shown in headers of live surfaces.                               |
| `--log-level`     | config    | Verbosity of the stderr/file log stream (`DEBUG|INFO|WARN|ERROR`).|
| `--config-file`   | —         | No presentation effect; changes config resolution.               |

---

## 5. Result surfaces

Every command output uses exactly one of five surfaces:

| Surface | Helper | Shape | Used for |
| ------- | ------ | ----- | -------- |
| **S1 Key-value block** | `output_obj(ctx, dict, title=…)` | Aligned dim-key/value pairs under a bold title | Single-entity results: a build, a promotion, a status, a dry-run preview |
| **S2 Row table** | `output_rows(ctx, list[dict], title=…)` | Dim uppercase header + aligned rows under a bold title | Collections: lists, coverage, registries, order reports |
| **S3 Live panel** | `dashboard/live_view.py` | Rounded `Panel`, border colour-coded by state | `trade status` (one-shot and `--watch`) |
| **S4 Paper dashboard** | `dashboard/paper_view.py` | Rounded `Panel` refreshed live | `trade start --mode paper` on a terminal |
| **S5 Raw export** | plain `print` / file write | Unwrapped text or file artifact | `backtest report --export csv` when piped; `report export` files |

S5 exists because any width-aware renderer wraps at terminal width, which
corrupts CSV when redirected — raw exports bypass the theme entirely.

---

## 6. Block standard (S1/S2)

### 6.1 Titles
- Bold, lowercase, terse, `<noun/group> <verb-or-state>`: `dataset built`,
  `config validate`, `profile create`, `backtest complete`,
  `paper session summary`, `close requested`.
- Row tables use a plural noun: `datasets`, `plugins`, `open positions`,
  `data coverage`, `model registry`, `orders for <date>`.

### 6.2 Keys and columns
- Data keys are `snake_case` (`dataset_id`, `bars_replayed`, `files_removed`);
  S2 headers display them uppercased with underscores as spaces
  (`DATASET ID`). JSON keys never change.
- Curated row tables may use symbols (`#`, `WIN %`, `DD %`, `PF`) when the
  table must fit 80 columns.
- Column order is meaning order (identity → activity → result → risk), never
  alphabetical. Catalogue-ordered lists (features) preserve registration order
  and expose the ordinal as a `#` column.

### 6.3 Alignment
- A column is **right-aligned** iff every row's value is `int` or `float`
  (`bool` excluded). Everything else is left-aligned.
- S1 key column is dim; value column plain (IDs and totals may be bold).

### 6.4 Value formatting (`_fmt_scalar` / `_render_value`)
| Value type | Rendering rule |
| ---------- | -------------- |
| `int` | Thousands separators **only when abs ≥ 10 000** (`110,125,169` but port `5555` stays ungrouped) |
| `float` | `{:,.6g}` — 6 significant digits, grouped |
| `bool` / `None` | Literal `True` / `False` / `None` |
| `Enum` | Its `.value` |
| `list` of scalars | Comma-joined: `EURUSD, GBPUSD` |
| `list` of dicts | Compact JSON |
| nested `dict` | Flattened to `parent.child = value` lines inside the value cell (`config show`, `train` metrics) |
| `NaN` / null | Coerced to `0.0` at the feature layer; never rendered as `nan` |

### 6.5 Domain units
| Quantity | Format |
| -------- | ------ |
| Prices (FX) | 5 decimals (`1.10271`) |
| Lots | 2 decimals (`0.05`, `6.52`) |
| Money / equity / PnL | 2 decimals, thousands-grouped; deltas signed (`+1,555,900.71`, `-255.85`) |
| Percentages | `WIN %` 1 dp, `DD %` 2 dp, progress 1 dp |
| Pips | 1 pip = 0.0001; spread/slippage in pips |
| Timestamps | `ts_unix_ms` integers in data; ISO-8601 UTC in logs; `YYYY-MM-DD` for report dates |
| Contract size | 100 000 per lot |

### 6.6 Empty state
Zero rows render the title plus a dim marker on one line:
`open positions  – none`. No empty header skeleton, no error.

### 6.7 Status vocabulary (with glyphs)
Fixed words, used consistently as values, prefixed by their outcome glyph:

| Situation | Rendered value |
| --------- | -------------- |
| Created / deleted / installed / removed | `✓ created` / `✓ deleted` / `✓ installed` (green) |
| Missing entity (exit 0) | `– not found` **or** `found  False` (dim) |
| Duplicate (exit 0) | `– already exists` (dim) |
| Boolean outcome | `deleted  True/False`, `removed  True/False`, `valid  ✓ True` |
| Control signals | `signal  stop|halt|resume` + `status  ✓ sent` |
| Long-running start | `status  ✓ started` + `stop  Ctrl-C` |

JSON mode strips glyphs — machine output carries the bare vocabulary word.

### 6.8 Dry-run shape
Always S1 with these keys first: `dry_run  True`, `action  <verb>`, then the
command's parameters. Title is the command name (`data fetch`, `trade start`,
`positions close`).

### 6.9 Confirmation prompts
Only destructive-to-a-live-session actions prompt: `trade halt` asks
`Halt trading (SAFE_HALT)? [y/N]`, aborting on no. `--yes` (command or
global) bypasses. No other command prompts.

---

## 7. Errors and exit codes

### 7.1 Error surface (stderr)
```
✗ DataError: human message           ← red glyph + bold type, plain message
  context: {"key": "value", …}       ← dim, compact JSON, only when present
```
The same record is logged as `cli_error` (JSON) with `error_type`, `message`,
`exit_code`, `context`. stdout stays clean.

### 7.2 Exit code catalogue (single-sourced; no literal codes elsewhere)
| Code | Meaning |
| ---- | ------- |
| 0    | Success (including "not found" lookups) |
| 1    | Generic unhandled error |
| 10   | Config validation failure |
| 11   | Secret found in config file |
| 20   | MT5 connect timeout (INIT_FAILED) |
| 21   | Reconciliation conflict requiring manual resolution |
| 30   | Dataset build failure (integrity check failed) |
| 31   | Training failure (HPO exhausted without valid trial) |
| 32   | Model promotion failure (metrics below threshold) |
| 40   | Risk engine hard-stop (daily loss limit hit mid-session) |
| 41   | Order submission permanently failed after retry exhaustion |
| 50   | Bridge protocol version mismatch (Python vs EA schema) |
| 60   | Plugin load failure (invalid entry point / non-conformance) |
| 130  | SIGINT received, clean shutdown completed |

Paper-mode softening: a reconciliation conflict against the simulated broker
auto-closes stale local paper positions instead of exiting 21 (paper positions
are simulations, not money).

---

## 8. State theme

State → token map (borders, state words, live headers):

| State | Token |
| ----- | ----- |
| `RUNNING`, `STATE_RECONCILING` | accent (cyan) |
| `SAFE_HALT` | warning (yellow bold) |
| `SHUTTING_DOWN`, `TERMINATED` | muted (dim) |
| anything else | plain |

---

## 9. Live surface: `trade status` (S3)

One-shot and `--watch` (2 Hz) render the same rounded panel. Header:
`Cocoon · <MODE↑> · profile default · RUNNING` with mode bold and state in its
token colour. Summary: open count vs `risk.max_open_positions`, unrealized
P&L signed green/red, daily-loss budget dim. Positions table per §2.3.
Footer: bridge connectivity (`CONNECTED` while RUNNING/RECONCILING, `–`
otherwise) and the configured ensemble, dim. State and control are file-backed
(`data/runtime/state.json`, `data/runtime/control.json`), so status works from
any terminal on the host. Expected rendering: §12.10.

---

## 10. Live surface: paper trading dashboard (S4)

Activation: `trade start --mode paper` when stdout is a TTY and
`--output json` is not set. Force with `--dashboard`, suppress with
`--no-dashboard`. Non-TTY renders the final frame only. While active, stderr
logging is quieted (file/audit sinks unaffected).

Refresh: 5 Hz; the dashboard thread reads a lock-free snapshot the feed thread
publishes each bar (`runtime.stats` swapped wholesale; `runtime.equity_curve`
append-only).

Anatomy, top to bottom (rounded panel titled `PAPER TRADING`, border = state
token):

1. **Header** — `Cocoon · PAPER · EURUSD M5 · RUNNING`.
2. **Progress row** — `━━━╸──` bar (width 44) + `d,ddd/t,ttt bars  pp.p%`.
3. **Stat row** — one-line table, dim uppercase headers, all right-aligned:

   | Column | Definition |
   | ------ | ---------- |
   | `EQUITY` | realized equity + open unrealized, 2 dp grouped |
   | `P&L` | equity − starting equity, signed, green/red |
   | `TRADES` | closed trades count |
   | `WIN %` | wins/trades, 0 dp; `–` when no trades |
   | `OPEN` | open position count |
   | `SIGNALS` | signals generated (post threshold/regime filter) |
   | `REJECTED` | signals rejected by the risk engine |

4. **Equity sparkline** — dim caption `equity · max 10,436 · min 9,931`, then
   a 64-glyph `▁▂▃▄▅▆▇█` line: stride-sampled (`len//width`), min-max
   normalised, coloured by overall P&L sign.
5. **Open positions table** — only when OPEN > 0: `SYMBOL DIR LOTS ENTRY
   UNREAL P&L` (§6.5 unit rules).

After the loop ends (replay exhausted, Ctrl-C, or `trade stop` from another
terminal), the final frame persists and the S1 `paper session summary` block
prints beneath it (leftover positions force-closed at last price and
included). Replay semantics surfaced in the UI: bars feed strictly
chronologically from an empty window (no cache seed → no lookahead); the feed
pauses while `SAFE_HALT` and resumes on `trade resume`. Expected rendering:
§12.10.

---

## 11. JSON mode contract

- S1 → single JSON object, S2 → JSON array of objects; pretty-printed; values
  raw (no separators, full float precision, no glyphs), non-JSON types
  stringified.
- The keys are **identical** to the table keys — scripting names never drift
  from display names.
- S3 one-shot honours it (raw state object). S4 is disabled under JSON mode.
- `backtest report --export json` prints the complete stored payload including
  `per_symbol` (full precision).
- CSV exports: 6 significant digits for floats; header row always present;
  written raw (S5) so redirection is byte-safe.

---

## 12. Per-command catalogue with expected results

Every command: surface, exact fields, and the expected result rendered to this
theme. Values are representative; structure, titles, keys, alignment, and
formatting are normative. Colour can't print in Markdown; tokens are annotated
`← green` etc. where semantics apply. Long dumps are elided with `…`.

### 12.1 Global flags

```console
$ cocoon --output json data cache stats
{
  "files": 3,
  "total_bytes": 148847,
  "root": "data\\raw"
}

$ cocoon --dry-run trade start --mode paper
trade start
  dry_run  True
  action   start
  mode     paper
```

### 12.2 `cocoon init`

S1 · `cocoon initialised` · `created` (count), `paths` (comma list; empty on
an idempotent re-run):

```console
$ cocoon init
cocoon initialised
  created  11
  paths    config, config/profiles, data, data/raw, data/features,
           data/datasets, data/models, data/plugins, logs,
           config/base.yaml, config/profiles/default.yaml

$ cocoon init
cocoon initialised
  created  0
  paths
```

### 12.3 `cocoon config`

```console
$ cocoon config show
resolved config
  runtime              mode = paper
                       log_level = INFO
                       data_dir = ./data
                       mt5_connect_timeout_ms = 5000
                       …
  risk                 max_daily_loss_pct = 2
                       min_confidence = 0.55
                       min_rr_ratio = 1.5
                       …
  …
```
*(all eight sections — `runtime mt5 feature_engineering model training risk
order logging` — render this way; nested keys flatten to `key = value` lines)*

```console
$ cocoon config validate
config validate
  profile  default
  valid    ✓ True                              ← green

$ cocoon config set risk.min_confidence 0.6
config set
  profile  default
  key      risk.min_confidence
  value    0.6

$ cocoon config profile create demo
profile create
  profile  demo
  status   ✓ created                           ← green
  path     config\profiles\demo.yaml

$ cocoon config profile create demo
profile create
  profile  demo
  status   – already exists                    ← dim

$ cocoon config profile list
profiles
  profiles  default, demo

$ cocoon config profile delete demo
profile delete
  profile  demo
  status   ✓ deleted                           ← green
```

Validation failure → stderr `✗ ConfigError: …`, exit 10.

### 12.4 `cocoon data`

```console
$ cocoon data fetch --symbol EURUSD --tf M5 --from 2024-01-01 --to 2024-06-01
fetched
  symbol  EURUSD
  tf      M5
  bars    42,816
  path    data\raw\EURUSD\M5.parquet
```

Without MT5 — stderr, exit 1:

```console
$ cocoon data fetch --symbol EURUSD --tf M5 --from 2024-01-01 --to 2024-01-02
✗ DataError: MetaTrader5 package not available
  context: {"hint": "cocoon data import seeds the cache from CSV/Parquet"}
```

```console
$ cocoon --dry-run data fetch --symbol EURUSD --tf M5 --from 2024-01-01 --to 2024-06-01
data fetch
  dry_run  True
  action   fetch
  symbol   EURUSD
  tf       M5
  from     2024-01-01
  to       2024-06-01

$ cocoon data import --symbol EURUSD --tf M5 --file .\bars.csv
imported
  symbol  EURUSD
  tf      M5
  bars    3002
  path    data\raw\EURUSD\M5.parquet

$ cocoon --dry-run data import --symbol EURUSD --tf M5 --file .\bars.csv
data import
  dry_run  True
  action   import
  symbol   EURUSD
  tf       M5
  bars     3002

$ cocoon data status
data coverage
  SYMBOL  TF   BARS  FIRST                      LAST
  EURUSD  M5   3002  2024-01-01T00:00:00+00:00  2025-03-21T07:35:00+00:00
  EURUSD  M15  3000  2024-01-01T00:00:00+00:00  2024-01-11T09:55:00+00:00
  GBPUSD  H1   3000  2024-01-01T00:00:00+00:00  2024-01-11T09:55:00+00:00

$ cocoon data cache stats
cache stats
  files        3
  total_bytes  148,847
  root         data\raw

$ cocoon data cache clear --symbol GBPUSD
cache clear
  symbol         GBPUSD
  files_removed  1
```

*(`import` accepts `ts_unix_ms` / `timestamp` / MT5 `<DATE>+<TIME>` layouts;
`status` orders symbol then timeframe chronologically M1 < M5 < … < H1;
unscoped `cache clear` shows `symbol  all`.)*

### 12.5 `cocoon dataset`

```console
$ cocoon dataset build --symbols EURUSD --tf M5 --label-horizon 12 --deadband-bps 2
dataset built
  dataset_id  ds_782987baf2387d02              ← bold (deterministic id)
  rows        2990
  features    25
  path        data\datasets\ds_782987baf2387d02.parquet

$ cocoon dataset list
datasets
  DATASET ID           SYMBOLS  TF  ROWS  HORIZON
  ds_782987baf2387d02  EURUSD   M5  2990       12
  ds_8e8832903f6561ae  EURUSD   M5  2997        5

$ cocoon dataset describe ds_782987baf2387d02
dataset ds_782987baf2387d02
  dataset_id     ds_782987baf2387d02
  symbols        EURUSD
  timeframe      M5
  label_horizon  12
  deadband_bps   2
  n_rows         2990
  feature_names  bos, choch, order_block, fvg, liquidity_sweep, …
  path           data\datasets\ds_782987baf2387d02.parquet
```

### 12.6 `cocoon features`

`#` is the registration ordinal — the exact column position in every dataset
and model feature vector; never re-sorted:

```console
$ cocoon features list
registered FeatureFn catalogue
   #  NAME         CATEGORY
   1  bos          smart money concepts
   2  choch        smart money concepts
   3  order_block  smart money concepts
   …  …            …
  11  rsi_14       oscillator
  12  atr_14_rel   oscillator
   …  …            …
  25  dow_6        day-of-week flag

$ cocoon features build --symbol EURUSD --tf M5
features built
  symbol    EURUSD
  tf        M5
  rows      3002
  features  25
  path      data\features\EURUSD\M5.parquet

$ cocoon features build --symbol USDJPY --tf M5
features build
  symbol       USDJPY
  tf           M5
  cached_bars  0                               ← result, exit 0
```

### 12.7 `cocoon train`

```console
$ cocoon train run --dataset ds_782987baf2387d02 --model lightgbm
training complete
  run_id         lightgbm_cda10e48681a         ← bold
  model          lightgbm
  metrics        walk_forward_auc_mean = 0.99176
                 walk_forward_auc_std = 0.00520865
                 n_folds = 4
                 n_samples = 2,752
  artifact_hash  cda10e48681a097b3f500ddfe4a1d38ec5…

$ cocoon train walk-forward --dataset ds_782987baf2387d02 --model lightgbm
walk-forward complete
  run_id       lightgbm_cda10e48681a
  fold_scores  0.985437, 0.994192, 0.99479, 0.992619
  metrics      walk_forward_auc_mean = 0.99176
               …

$ cocoon train status lightgbm_cda10e48681a
run status
  run_id      lightgbm_cda10e48681a
  model       lightgbm
  dataset_id  ds_782987baf2387d02
  stage       none
  metrics     walk_forward_auc_mean = 0.99176
              …

$ cocoon train status no_such_run
run status
  run_id  no_such_run
  found   False                                ← dim
```

### 12.8 `cocoon model`

Registry ordered production → staging → none; hash truncated to 12 chars:

```console
$ cocoon model list
model registry
  RUN ID                 MODEL     STAGE       DATASET ID           HASH
  xgboost_994b45ad8576   xgboost   production  ds_782987baf2387d02  994b45ad8576
  lightgbm_d652fbfd8c79  lightgbm  staging     ds_8e8832903f6561ae  d652fbfd8c79
  lightgbm_cda10e48681a  lightgbm  none        ds_782987baf2387d02  cda10e48681a

$ cocoon model inspect xgboost_994b45ad8576
model xgboost_994b45ad8576
  run_id         xgboost_994b45ad8576
  model_name     xgboost
  stage          production
  dataset_id     ds_782987baf2387d02
  artifact_hash  994b45ad8576800cbd6c903b6bc9853ca…
  params         n_estimators = 300
                 …
  metrics        walk_forward_auc_mean = 0.990456
                 …

$ cocoon model promote xgboost_994b45ad8576 --stage production
model promote
  run_id  xgboost_994b45ad8576
  stage   ✓ production                         ← green; previous holder demoted

$ cocoon model delete lightgbm_532c40238df8
model delete
  run_id   lightgbm_532c40238df8
  deleted  True
```

### 12.9 `cocoon backtest`

`bt_*` id is content-hashed (same inputs → same id); skipped symbols surface
in the result, not as warnings:

```console
$ cocoon backtest run --model-version xgboost_994b45ad8576 --symbols EURUSD,USDJPY --tf M5
backtest complete
  backtest_id             bt_f134011ec58bc1be  ← bold
  total_trades            907
  total_pnl               1.10354e+06          ← green when ≥ 0
  skipped (too few bars)  USDJPY               ← dim

$ cocoon backtest report bt_f134011ec58bc1be
backtest bt_f134011ec58bc1be
  model_version  xgboost_994b45ad8576
  symbols        EURUSD
  timeframe      M5
  total_trades   907
  total_pnl      1.10354e+06

per-symbol metrics
  SYMBOL  TRADES  WIN %    PF          PNL  DD %  SHARPE   SIG   REJ
  EURUSD     907   91.8  30.5  1,103,535.4  1.14    0.61  2745  1838
```

TTY `--export csv` — transposed full detail (14 metric rows × one column per
symbol); piped, the same command emits raw CSV (S5, floats at 6 sig digits):

```console
$ cocoon backtest report bt_f134011ec58bc1be --export csv
backtest metrics — full detail
  METRIC              EURUSD
  trades              907
  win rate            91.8%
  profit factor       30.53
  avg win             1,342.10
  avg loss            -486.55
  gross profit        1,140,785.0
  gross loss          -37,249.60
  expectancy / trade  1,216.69
  total pnl           1,103,535.4
  final equity        1,113,535.4
  max drawdown        1.14%
  sharpe              0.61
  signals             2745
  rejected by risk    1838

$ cocoon backtest report bt_f134011ec58bc1be --export csv > report.csv
(raw CSV on stdout — no theme, no wrapping)

$ cocoon backtest report bt_0000000000000000
backtest report
  backtest_id  bt_0000000000000000
  found        False                           ← dim
```

### 12.10 `cocoon trade`

Paper on a TTY → S4 dashboard. Mid-replay expected frame (border cyan while
RUNNING; P&L green; stat-row ints unformatted):

```console
$ cocoon trade start --mode paper --speed 20
╭─ PAPER TRADING ─────────────────────────────────────────────────────────╮
│ Cocoon · PAPER · EURUSD M5 · RUNNING                                    │
│ ━━━━━━━━━━━━━━━━━━━━━╸──────────────────────  1,472/3,002 bars   49.0%  │
│                                                                         │
│     EQUITY      P&L  TRADES  WIN %  OPEN  SIGNALS  REJECTED             │
│  10,412.87  +412.87     118    64%     2     1391       944             │
│                                                                         │
│  equity · max 10,436 · min 9,931                                        │
│  ▁▂▂▃▂▃▃▄▃▄▄▅▄▅▅▅▆▅▆▆▅▆▆▇▆▇▇▆▇▇█▇██▇█                                   │
│                                                                         │
│  SYMBOL  DIR   LOTS  ENTRY    UNREAL P&L                                │
│  EURUSD  BUY   0.62  1.09214      +14.20                                │
│  EURUSD  SELL  0.58  1.09876       -3.75                                │
╰─────────────────────────────────────────────────────────────────────────╯
```

On completion the final frame persists (state `TERMINATED`, border dim) and
the summary prints beneath:

```console
paper session summary
  symbol           EURUSD
  tf               M5
  bars_replayed    3002
  trades           965
  starting_equity  10,000
  final_equity     1.56577e+06
  total_pnl        1.55577e+06                 ← green
```

Piped / `--no-dashboard` / JSON mode — S1 start block instead of the panel:

```console
$ cocoon trade start --mode paper --no-dashboard
trade start
  mode    paper
  status  ✓ started                            ← green
  stop    Ctrl-C
```

Live mode without a reachable EA — stderr, exit 20:

```console
$ cocoon trade start --mode live
✗ MT5ConnectTimeoutError: MT5 EA did not ACK HELLO within timeout
  context: {"timeout_ms": 5000, "error": "Resource temporarily unavailable"}
```

Status panel and controls:

```console
$ cocoon trade status
╭─ LIVE ──────────────────────────────────────────────────────────╮
│ Cocoon · PAPER · profile default · RUNNING                      │
│ open 1/5 · unrealized +14.20 · daily loss budget 2.0%           │
│                                                                 │
│  SYMBOL  DIR  LOTS  ENTRY    SL       TP       P&L     ORIGIN   │
│  EURUSD  BUY  0.62  1.09214  1.09135  1.09333  +14.20  internal │
│                                                                 │
│ bridge CONNECTED · model lightgbm, xgboost, tabnet              │
╰─────────────────────────────────────────────────────────────────╯

$ cocoon --output json trade status
{
  "state": "RUNNING",
  "mode": "paper",
  "started_ms": 1784719853170
}

$ cocoon trade halt
Halt trading (SAFE_HALT)? [y/N]: y
trade halt
  signal  halt
  status  ✓ sent                               ← green

$ cocoon trade resume
trade resume
  signal  resume
  status  ✓ sent

$ cocoon trade stop
trade stop
  signal  stop
  status  ✓ sent
```

Paper options: `--symbol/--tf` choose the replayed cache (default: largest);
`--speed` bars/second (default 20; `0` = unpaced); `--equity` starting account
(default 10 000); `--dashboard/--no-dashboard` overrides TTY autodetection.

### 12.11 `cocoon positions`

```console
$ cocoon positions list
open positions
  TICKET  SYMBOL  DIR  LOTS  ENTRY    PNL     ORIGIN
       7  EURUSD  BUY  0.62  1.09214  +14.20  internal

$ cocoon positions list        # nothing open
open positions  – none                         ← dim

$ cocoon positions close 7
close requested
  ticket  7
  status  ✓ FILLED                             ← green

$ cocoon --dry-run positions close 7 --partial 0.30
positions close
  dry_run  True
  action   close
  ticket   7
  partial  0.3
```

Real `close` requires the bridge; without an EA it errors with exit 20.

### 12.12 `cocoon report`

```console
$ cocoon report daily --date 2026-07-26
orders for 2026-07-26
  IDEMPOTENCY KEY  SYMBOL  DIRECTION  VOLUME LOTS  STATUS  BROKER TICKET ID  …
  69ae9c31…        EURUSD  BUY               0.62  FILLED                 7  …
  fbae1d02…        EURUSD  SELL              0.58  FILLED                 8  …
  …                …       …                    …  …                      …  …
```
*(ORDER audit payloads filtered to the UTC day, capped at 100 rows; trailing
columns: `FILLED VOLUME LOTS`, `FILLED PRICE`, `REJECT REASON`, `ATTEMPT`.)*

```console
$ cocoon report session cocoon-ea
session cocoon-ea
  session_id  cocoon-ea
  events      0
  orders      0
```
*(Known gap: audit payloads carry no session id yet, so counts are always 0.)*

```console
$ cocoon report export --format csv --out ./out/audit.csv
report export
  events  3011
  format  csv
  path    out\audit.csv

$ cocoon report export --format xml --out ./out/audit.xml
report export
  format  xml
  status  – unknown format (use csv|json)      ← dim; exit 1
```

### 12.13 `cocoon plugin`

```console
$ cocoon plugin list
plugins
  NAME          KIND   SOURCE
  my_indicator  local  data\plugins\my_indicator.py

$ cocoon plugin install .\my_indicator.py
plugin install
  name    my_indicator
  source  data\plugins\my_indicator.py
  status  ✓ installed                          ← green

$ cocoon plugin remove my_indicator
plugin remove
  name     my_indicator
  removed  True
```

Non-conforming plugin → stderr `✗ PluginError: …`, exit 60.

---

## 13. Terminal compatibility

- **Encoding**: UTF-8 output (glyphs §2.2, sparkline ramp, `·`, `—`). On
  Windows consoles set `PYTHONIOENCODING=utf-8` / code page 65001 if glyphs
  corrupt; `TERM=dumb` switches to the ASCII fallbacks.
- **Width**: blocks target 80 columns; wide detail goes to transposed tables
  or exports. Cells truncate with `…` rather than wrapping keys.
- **Non-TTY**: colour off, live surfaces print a final frame only, CSV export
  switches to raw mode automatically (`sys.stdout.isatty()`).
- **Colour/glyph loss**: information is never colour-only or glyph-only —
  every coloured value is signed or worded, every glyph rides a vocabulary
  word.

---

## 14. Compliance checklist for a new command

- [ ] Result rendered via `output_obj`/`output_rows` (or a documented S3–S5
      surface) — no bare prints, no prose.
- [ ] Title follows §6.1; keys follow §6.2; status words + glyphs from §6.7.
- [ ] Negative outcomes are results with exit 0; failures raise a
      `CocoonError` with a catalogued exit code (§7.2) — never a hardcoded
      integer.
- [ ] `--output json` verified to emit the same keys, glyph-free.
- [ ] Mutating? Implements the §6.8 dry-run shape.
- [ ] Destructive to a live session? Prompts with `--yes` bypass (§6.9).
- [ ] Numbers follow §6.4/§6.5; colours/glyphs follow §2 tokens only.
- [ ] Long-running? Progress on a Live surface, logs quieted to file, final
      summary block on completion.
- [ ] Empty collections render the `– none` empty state, not an error.
- [ ] Renders correctly under `NO_COLOR`, piped, and `TERM=dumb`.
- [ ] Expected-result block added to §12 of this document.
