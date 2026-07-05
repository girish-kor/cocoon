<div align="center">

<img src="assets/LOGO/logo.png" alt="Cocoon logo" width="80%" />

### Build ML trading systems the way you'd build production software.

A reference architecture for machine-learning trading systems — with the engineering
discipline the field usually skips: **point-in-time-safe features**, **content-hashed
deterministic datasets**, **backtest/live code parity**, and enforced layering. One CLI
takes you from raw OHLCV to a promoted model to an event-driven backtest that runs the
*exact same code path* as live.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
[![Status: reference architecture](https://img.shields.io/badge/status-reference%20architecture-blue.svg)](#status-what-is-proven-vs-not)
[![Not financial advice](https://img.shields.io/badge/⚠️-not%20financial%20advice-red.svg)](#a-warning-worth-repeating)

[Quickstart](#quickstart) · [Why it exists](#why-cocoon-exists) · [What makes it different](#what-makes-it-different) · [Architecture](#architecture) · [Status](#status-what-is-proven-vs-not) · [Contributing](CONTRIBUTING.md)

</div>

---

> **What this is (and isn't).** Cocoon is a *studyable, runnable reference implementation*
> of a production-grade ML trading pipeline. It is **not** a get-rich bot and ships with
> **no proven predictive edge**. Star it to learn how these systems are built correctly —
> not to point it at a funded account. See [the warning](#a-warning-worth-repeating).

## Why Cocoon exists

Most open-source trading bots are one 2,000-line script. They leak future data into
features, can't reproduce a dataset from last week, run different code in backtest than
in live, and quietly size a position that would blow up an account. They look like they
work — right up until real money is involved.

Cocoon is the opposite bet: **treat an ML trading system like the safety-critical
software it is.** It's 105 Python files across six strictly-layered modules, built so that
the parts that *can lose money* are isolated, deterministic, and auditable. It's the
codebase you'd want to read before writing your own — or the skeleton you'd fork and
harden.

## What makes it different

| Most trading repos | Cocoon |
|---|---|
| Features silently peek at the future | **Structurally causal features** — each feature only ever sees rows up to the current one, enforced by slicing, not discipline |
| "Which data made this model?" 🤷 | **Content-hashed, versioned datasets** — reruns produce byte-identical dataset & run IDs |
| Backtest ≠ live behavior | **Backtest/live parity** — same signal → risk → order code, with a simulated broker swapped in behind one interface |
| Spaghetti imports | **Six enforced layers** (core → data → ml → trading → bridge → cli); imports only go downward |
| `print()` and hope | **Meaningful exit codes** + `--output json` on every command, MLflow model registry with staging/production promotion |
| Marketing gloss numbers | **Radical honesty** — a whole section on [what is proven vs. not](#status-what-is-proven-vs-not) |

### The features (25, point-in-time-safe)

- **6 Smart-Money-Concepts features:** Break of Structure (BOS), Change of Character
  (CHoCH), Fair Value Gaps (FVG), Liquidity Sweeps, Order Blocks, Premium/Discount zones.
- **Technical analysis:** moving averages, oscillators.
- **Context flags:** trading-session and day-of-week markers.

### The models

LightGBM · XGBoost · TabNet · weighted ensemble — each registered by content hash,
trained with walk-forward validation and Optuna HPO, promotable to `staging`/`production`.

## Architecture

```
                 ┌─────────────────────────────────────────────────────────┐
   raw OHLCV ───▶│  data    ingest → causal features → labels → dataset    │  L1
                 └───────────────────────────┬─────────────────────────────┘
                                             ▼
                 ┌─────────────────────────────────────────────────────────┐
                 │  ml      walk-forward train + Optuna → hash-registry    │  L2
                 │          → promote → inference                          │
                 └───────────────────────────┬─────────────────────────────┘
                                             ▼
                 ┌─────────────────────────────────────────────────────────┐
                 │  trading   signal → risk → portfolio → order            │  L3
                 │            └── backtest reuses this exact path ──┐      │
                 └───────────────────────────┬──────────────────────┼──────┘
                                             ▼                      ▼
                 ┌───────────────────────────────────┐   ┌──────────────────┐
                 │  bridge  ZMQ + msgpack protocol   │   │ simulated broker │  L4
                 │          ↔ MQL5 EA (MetaTrader 5) │   │  (backtest only) │
                 └───────────────────────────────────┘   └──────────────────┘

   core (L0): config · logging · errors · state machine · interfaces  ← everything imports down into this
   cli  (L5): typer commands · questionary menu · dashboard           ← the single entry point
```

Layers only import downward, enforced at runtime as a best-effort tripwire on the
immediate caller. The backtester and the live loop share the **same** signal, risk, and
order code — only the broker behind the interface changes. That single design choice is
what makes a backtest worth trusting.

```
src/cocoon/
  core/        config, logging, errors, state machine, interfaces   (L0)
  data/        market data, feature_eng (smc/ta), labeling, dataset (L1)
  ml/          models, training (walk-forward + optuna), registry   (L2)
  trading/     signal, risk, portfolio, order, backtest             (L3)
  bridge/      protocol, zmq_endpoint, heartbeat, broker_adapter    (L4)
  cli/         main, commands/, menu, dashboard                     (L5)
  persistence/ sqlalchemy models + repositories
  plugins/     entry-point + local-file feature plugins
mql5/          CocoonEA.mq5 + Include/ (reference skeleton)
```

## Quickstart

Python 3.11 is the supported target (3.12 also works).

```bash
pip install -e .
```

Then run the full pipeline — every command below is real and machine-verified:

```bash
cocoon init                                                   # scaffold config/, data/, logs/
cocoon config validate                                        # → "config for profile 'default' is valid"
cocoon data import --symbol EURUSD --tf M5 --file bars.csv    # seed the parquet cache from CSV/Parquet
cocoon features list                                          # the 25 point-in-time-safe features
cocoon dataset build --symbols EURUSD --tf M5 --label-horizon 5
cocoon train run --dataset ds_xxxx --model lightgbm
cocoon model promote lightgbm_xxxx --stage production
cocoon backtest run --model-version lightgbm_xxxx --symbols EURUSD --tf M5
cocoon backtest report bt_xxxx --export csv
```

- `cocoon menu` opens an interactive menu that re-invokes the same commands, so the UI
  can't drift from the CLI.
- Add `--output json` for machine-readable output. **Global flags go *before* the
  subcommand:** `cocoon --output json model list` ✅ · `cocoon model list --output json` ❌.
- No MetaTrader 5 terminal? `data import` seeds the same cache `data fetch` would, so the
  entire pipeline runs offline on CSV/Parquet.

See [`USECASE.md`](USECASE.md) for a full hands-on walkthrough and a reference for every
command, [`DOCUMENT.md`](DOCUMENT.md) for the design specification, and [`TABLE.md`](TABLE.md)
for the module-by-module map.

## Status: what is proven vs. not

Cocoon's headline feature is that it tells you exactly how far to trust it.

**✅ Verified by running it:**
- Feature causality, dataset versioning, and end-to-end determinism (byte-identical IDs).
- Train / register / promote / load / infer for all three models and the ensemble.
- Risk-check sequencing and short-circuit; idempotent order submission (a duplicate key
  hits the broker once); startup reconciliation importing an external position.
- The full bridge protocol round-trip (Python ↔ Python over ZMQ + msgpack).
- Every CLI command's exit code and output shape.

**❌ Not validated (could not be tested without a live terminal):**
- Anything touching a real MT5 terminal: live fetch, real fills, partial fills, requotes,
  the production EA.
- **That any of this makes money.** It demonstrates *no* predictive edge on real data and
  was never validated on real data.

**Known sharp edges** (documented, not hidden): backtest numbers on synthetic data are
meaningless noise; default walk-forward windows assume months of data (small caches yield
0 folds); DB-backed reports read a table the current flow doesn't fill (the `logs/audit.jsonl`
sink is the real audit trail); the MQL5 EA is a reference skeleton, not byte-compatible
with the Python msgpack frames as written; `libzmq.dll` is a binary you supply. Each of
these is explained in [`USECASE.md`](USECASE.md).

## Roadmap

Cocoon is a deliberately honest skeleton. The path from "reference architecture" to
"validated system" is exactly the work that was scoped out — and it's where contributions
matter most:

- [ ] **Test suite** — unit + integration + replay tests against historical tick data,
      especially around risk, order, and bridge code. *(Highest priority — see [issue templates](.github/ISSUE_TEMPLATE).)*
- [ ] **Real-data validation** — a documented study with proper train/validation/test
      splits and honest metrics on genuine market data.
- [ ] **msgpack-compatible MQL5 EA** — replace the hand-rolled JSON in `CocoonEA.mq5`.
- [ ] **Bridge the audit sink** — feed `logs/audit.jsonl` into the DB so reports fill.
- [ ] **Risk-aware position sizing** — the current fixed-fractional sizing is deliberately naive.
- [ ] **Static layer-import checker** — replace the runtime tripwire with a full import-graph gate.

## Contributing

Contributions are very welcome — this project is most valuable as something the community
hardens together. Start with [`CONTRIBUTING.md`](CONTRIBUTING.md) and the
[good-first-issue roadmap](#roadmap). Please read [`SECURITY.md`](SECURITY.md) before
reporting anything credential- or capital-related.

## A warning worth repeating

Cocoon is an educational reference architecture. It has **no tests**, has **never touched
a real terminal or real capital**, and demonstrates **no predictive edge**. The risk,
order, and bridge code — the parts that can lose real money — are untested against
historical tick data. Treat it as a skeleton you validate before it goes anywhere near a
funded account. **Nothing here is financial advice.** Trading leveraged FX carries a high
risk of losing money.

## License

[MIT](LICENSE) © Cocoon contributors.
