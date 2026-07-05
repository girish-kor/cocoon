# Cocoon — Launch Playbook

This is the go-to-market kit for taking Cocoon public. The positioning is deliberate:
**a reference architecture, not a money-printer.** Engineers star clean architecture and
honest docs; they downvote hype. Every asset below leans into the engineering story and
stays scrupulously honest — that honesty *is* the differentiator that gets it shared.

---

## 1. Repository metadata (set these in GitHub Settings)

**Repo name:** `cocoon`

**Description (≤ 350 chars — this is the single most-read line):**
> A reference architecture for ML trading systems: point-in-time-safe features, content-hashed deterministic datasets, and backtest/live code parity — from raw OHLCV to a promoted model in one CLI. Educational, honest about what's proven. Not financial advice.

**Topics (add all — drives GitHub search & "Explore" discovery):**
```
machine-learning  algorithmic-trading  quantitative-finance  trading-bot
smart-money-concepts  lightgbm  xgboost  tabnet  mlops  mlflow  backtesting
metatrader5  forex  python  reference-architecture  feature-engineering
walk-forward-validation  optuna  event-driven  zeromq
```

**Enable:** Discussions, Issues, and the Sponsor button (`.github/FUNDING.yml`).
**Social preview:** add an Open Graph image (Settings → Social preview) — the 🐛 + tagline.
Repos with a social image get materially higher click-through when shared.

---

## 2. The one-liner (use everywhere, verbatim)

> **Cocoon — build ML trading systems the way you'd build production software.**

Backup variants:
- "The ML trading repo that tells you exactly how far to trust it."
- "Causal features, deterministic datasets, backtest/live parity. The boring parts, done right."

---

## 3. Show HN post

**Title:**
`Show HN: Cocoon – an ML trading system built like production software (no proven edge)`

**Body:**
```
I kept seeing open-source trading bots that were one giant script: features that
peek at the future, datasets you can't reproduce, and a backtest running different
code than live. They look like they work until real money shows up.

Cocoon is the opposite experiment — treat an ML trading pipeline like
safety-critical software. It's 105 Python files across six strictly-layered
modules (core → data → ml → trading → bridge → cli), and the design choices are
the point:

- Features are structurally point-in-time-safe: each feature only ever sees rows
  up to the current one, enforced by slicing, not discipline.
- Datasets are content-hashed and deterministic — rerun and you get byte-identical
  dataset and run IDs.
- The backtester runs the *exact* signal → risk → order code as live mode, with a
  simulated broker swapped in behind one interface. That's the only way a backtest
  is worth trusting.
- Models: LightGBM / XGBoost / TabNet / ensemble, walk-forward + Optuna, registered
  by content hash and promotable to production via MLflow.

The most unusual thing: the README has a whole section on what's *proven* vs. not.
I verified feature causality, determinism, the full train→promote→backtest chain,
idempotent order submission, and the bridge round-trip. I did NOT validate it
against a real MT5 terminal, and it demonstrates zero predictive edge on real data.
There are no tests yet — which is exactly the roadmap.

It's meant as a reference to read/fork, not a bot to point at your savings. Happy
to talk about the causal-feature enforcement, the backtest/live parity, or the
layering tripwire.

Repo: <link>
```

**Timing:** post Tue–Thu, ~8–10am ET. Be present in the thread for the first 3 hours —
answering technical questions well is what keeps it on the front page.

---

## 4. Reddit

**r/algotrading** — title:
`I built an open-source ML trading system focused on the engineering, not the returns (point-in-time-safe features, backtest/live parity)`

Lead with the causal-feature and backtest-parity story; be explicit it has no proven edge.
This subreddit punishes hype and rewards rigor — the honesty section is your credibility.

**r/MachineLearning** (`[P]` Project) — title:
`[P] Cocoon: a reference architecture for ML trading — deterministic datasets, walk-forward + Optuna, hash-based model registry`

Frame it as an MLOps/feature-engineering case study. The point-in-time-safety and
content-hashed reproducibility are the ML-crowd hooks.

**r/Python** — angle: clean layered architecture, Typer CLI with meaningful exit codes and
JSON output, plugin system. Lead with code quality, not trading.

---

## 5. X / LinkedIn thread (skeleton)

1. Most open-source trading bots leak future data into their features and don't know it.
   I built Cocoon to show what it looks like to do it right. 🧵
2. Rule 1: features must be point-in-time-safe. In Cocoon each feature only ever sees rows
   up to *now* — enforced by slicing, not by hoping. [code snippet]
3. Rule 2: reproducibility. Datasets are content-hashed. Rerun the pipeline → byte-identical
   IDs. You can always answer "which data made this model?"
4. Rule 3: your backtest must run the same code as live. Cocoon's backtester reuses the exact
   signal→risk→order path, swapping only the broker. [diagram]
5. Models: LightGBM/XGBoost/TabNet/ensemble, walk-forward + Optuna, hash-registered, promote
   to prod via MLflow.
6. The honest part: no tests yet, never touched a real terminal, zero proven edge. It's a
   reference architecture to learn from and harden — not a bot for your savings.
7. MIT licensed, contributions welcome (tests are issue #1). ⭐ if useful: <link>

Attach the architecture diagram from the README as the thread's image.

---

## 6. First-week checklist

- [ ] Set description + all topics + social preview image.
- [ ] Enable Discussions; open 5–8 `good first issue`s from the README roadmap (tests first).
- [ ] Pin a "Start here / Is this for me?" Discussion.
- [ ] Add an Open Graph social image (🐛 Cocoon + one-liner).
- [ ] Confirm CI is green (badge in README) before posting anywhere.
- [ ] Post Show HN (Tue–Thu am ET) → same day cross-post r/algotrading & r/MachineLearning.
- [ ] Reply to every substantive comment in the first 24h.
- [ ] Submit to newsletters/lists: Python Weekly, Awesome-Quant, Awesome-MLOps (PR the list).
- [ ] Tag a v0.1.0 GitHub Release with the CHANGELOG notes.

## 7. What NOT to do

- Don't post fabricated returns, equity curves, or "profit factor" screenshots. On synthetic
  data those numbers are noise, and quant communities will find that out and torch the launch.
- Don't call it a "bot you can run to make money." That invites the exact scrutiny that
  sinks trading repos — and it isn't true.
- Don't hide the limitations. The "what's proven vs. not" section is the reason serious
  people will trust and share it.
