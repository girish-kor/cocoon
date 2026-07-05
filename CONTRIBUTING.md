# Contributing to Cocoon

Thank you for considering a contribution. Cocoon is most valuable as a reference
architecture that the community hardens together — the gap between "runnable skeleton"
and "validated system" is exactly where your help matters.

## Ground rules (the things that make this project what it is)

Cocoon has a few non-negotiable design principles. PRs that violate them will be asked to
change, no matter how useful the feature:

1. **Features must be point-in-time-safe.** A feature may only ever read rows up to the
   current one. If you add a feature, enforce causality structurally (by slicing), and say
   in the PR how you verified no future leakage.
2. **Layers import downward only** (`core → data → ml → trading → bridge → cli`). Never
   import upward or sideways across a boundary.
3. **Backtest and live share one code path.** The only thing that may differ between
   backtest and live is the broker behind the interface. Don't fork signal, risk, or order logic.
4. **Determinism is a feature.** The same inputs must produce byte-identical dataset and
   run IDs. If your change touches dataset building or training, confirm reruns still match.
5. **Be honest in the docs.** If something is untested or unproven, say so. The project's
   credibility comes from not overclaiming.

## Where to start

The [roadmap in the README](README.md#roadmap) lists the highest-impact work. The single
most valuable contribution is **tests** — there are none today, and the risk/order/bridge
code that can lose money is untested. Replay tests against historical tick data are gold.

Look for issues labeled `good first issue` and `help wanted`.

## Development setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
pip install -e .
cocoon --help          # sanity check the entry point
```

Python 3.11 is the supported target (3.12 works too).

## Making a change

1. Fork and branch from `main` (`git checkout -b feat/your-thing`).
2. Keep changes focused; match the surrounding code's style and idioms.
3. If you add a CLI command, add `--output json` support and a meaningful exit code, and
   document it in `USECASE.md`.
4. Run the smoke checks locally before pushing:
   ```bash
   python -m compileall src        # everything must compile
   cocoon --help                   # entry point must load
   ```
5. Open a PR using the template. Describe **what you verified and how** — especially for
   anything touching features, risk, orders, or the bridge.

## Reporting bugs & requesting features

Use the [issue templates](.github/ISSUE_TEMPLATE). For anything involving credentials or
capital risk, read [`SECURITY.md`](SECURITY.md) first and report privately.

## Code of Conduct

By participating you agree to uphold our [Code of Conduct](CODE_OF_CONDUCT.md).
